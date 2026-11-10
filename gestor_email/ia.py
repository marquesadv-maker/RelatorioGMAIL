"""
Preenchimento de modelos de e-mail com IA (Claude, da Anthropic).

Recebe o documento processual (PDF/imagem) e/ou o e-mail de referência e
devolve o e-mail preenchido conforme os modelos do escritório, seguindo as
regras da skill "modelos-de-e-mails-marques" (sem inventar dados; o que não
constar do documento fica marcado como pendência).

A chave da API fica só neste computador (dados/ia.json ou a variável de
ambiente ANTHROPIC_API_KEY) e nunca é enviada ao navegador.
"""
import base64
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from . import config, modelos

MODELO_IA = os.environ.get("GESTOR_IA_MODELO", "claude-opus-5-5")
ARQ_CONFIG = os.path.join(config.DATA_DIR, "ia.json")

TIPOS_ACEITOS = {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp"}
LIMITE_BYTES = 25 * 1024 * 1024

INSTRUCOES_SAIDA = """
# MODO DE OPERAÇÃO NO MARQUESPRO MAIL

Você está integrado ao MarquesPro Mail, a caixa de e-mails do escritório. Aplique
integralmente as regras e os modelos acima. Responda SOMENTE com o JSON pedido:

- "codigo": código do modelo utilizado (ex.: "AUD-02"). Se o usuário indicou um
  código, use-o; se indicou "automático", escolha pela seção SELEÇÃO AUTOMÁTICA.
- "assunto": assunto do e-mail conforme o modelo (vazio se o modelo não tiver).
- "corpo": texto final do e-mail, em texto simples, com quebras de linha "\\n" e
  linha em branco entre parágrafos. Não inclua a assinatura pessoal do remetente
  (ela é inserida pelo sistema). Mantenha o fecho do modelo
  ("Atenciosamente,\\nMarques Advogados S/S") quando ele existir.
- Dado ausente, ilegível ou não confirmado no documento: NÃO invente. Escreva no
  corpo "[PREENCHER: NOME DO CAMPO]" e liste-o em "pendencias".
- "pendencias": lista de dados que o advogado precisa completar ou conferir.
- "observacoes": avisos curtos (ex.: documento parcialmente ilegível, prazo que
  depende de conferência). Vazio se não houver.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "codigo": {"type": "string"},
        "assunto": {"type": "string"},
        "corpo": {"type": "string"},
        "pendencias": {"type": "array", "items": {"type": "string"}},
        "observacoes": {"type": "string"},
    },
    "required": ["codigo", "assunto", "corpo", "pendencias", "observacoes"],
    "additionalProperties": False,
}


# ─── Configuração da chave ───────────────────────────────────────────────────

def _ler_config() -> Dict[str, Any]:
    try:
        with open(ARQ_CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def chave() -> Optional[str]:
    return _ler_config().get("api_key") or os.environ.get("ANTHROPIC_API_KEY") or None


def status() -> Dict[str, Any]:
    cfg = _ler_config()
    origem = "arquivo local" if cfg.get("api_key") else ("variável de ambiente" if os.environ.get("ANTHROPIC_API_KEY") else None)
    return {"configurada": bool(origem), "origem": origem, "modelo": MODELO_IA}


def salvar_chave(api_key: str):
    api_key = (api_key or "").strip()
    os.makedirs(config.DATA_DIR, exist_ok=True)
    cfg = _ler_config()
    if api_key:
        cfg["api_key"] = api_key
    else:
        cfg.pop("api_key", None)
    with open(ARQ_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    try:
        os.chmod(ARQ_CONFIG, 0o600)
    except OSError:
        pass


# ─── Chamada à API ───────────────────────────────────────────────────────────

def _bloco_arquivo(nome: str, mime: str, dados: bytes) -> Dict[str, Any]:
    b64 = base64.standard_b64encode(dados).decode("ascii")
    if mime == "application/pdf":
        return {"type": "document", "title": nome[:200],
                "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}}


def montar_conteudo(codigo: str, instrucoes: str, email_ref: Optional[Dict[str, str]],
                    arquivos: List[Tuple[str, str, bytes]]) -> List[Dict[str, Any]]:
    conteudo: List[Dict[str, Any]] = []
    for nome, mime, dados in arquivos:
        if mime not in TIPOS_ACEITOS:
            raise ValueError(f"Formato não aceito para a IA: {nome} ({mime}). Use PDF, PNG ou JPG.")
        conteudo.append(_bloco_arquivo(nome, mime, dados))
    partes = []
    if codigo:
        m = modelos.por_codigo(codigo)
        partes.append(f"Modelo escolhido pelo usuário: {codigo}" + (f" — {m['titulo']}" if m else ""))
    else:
        partes.append("Modelo: automático (escolha o modelo adequado conforme a SELEÇÃO AUTOMÁTICA).")
    if email_ref:
        partes.append(
            "E-mail de referência (recebido/selecionado no sistema):\n"
            f"De: {email_ref.get('de', '')}\nPara: {email_ref.get('para', '')}\n"
            f"Assunto: {email_ref.get('assunto', '')}\n\n{email_ref.get('texto', '')[:20000]}"
        )
    if instrucoes.strip():
        partes.append(f"Instruções adicionais do advogado:\n{instrucoes.strip()}")
    if not arquivos and not email_ref:
        partes.append("Não há documento anexado: preencha apenas o que constar das instruções e marque o restante como [PREENCHER].")
    conteudo.append({"type": "text", "text": "\n\n".join(partes)})
    return conteudo


def preencher(codigo: str, instrucoes: str, email_ref: Optional[Dict[str, str]],
              arquivos: List[Tuple[str, str, bytes]], client=None) -> Dict[str, Any]:
    if sum(len(d) for _, _, d in arquivos) > LIMITE_BYTES:
        raise ValueError("Arquivos muito grandes para a IA (limite de 25 MB no total).")
    if client is None:
        key = chave()
        if not key:
            raise RuntimeError("IA não configurada: informe a chave da API em Configurações → IA.")
        import anthropic
        client = anthropic.Anthropic(api_key=key)

    system = [{"type": "text", "text": modelos.texto_skill() + "\n\n" + INSTRUCOES_SAIDA,
               "cache_control": {"type": "ephemeral"}}]
    resp = client.beta.messages.create(
        model=MODELO_IA,
        max_tokens=16000,
        system=system,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": montar_conteudo(codigo, instrucoes, email_ref, arquivos)}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("A IA não processou este pedido. Preencha o modelo manualmente.")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("A resposta da IA ficou incompleta. Tente novamente com menos documentos.")
    texto = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
    try:
        dados = json.loads(texto)
    except ValueError:
        raise RuntimeError("A IA devolveu uma resposta em formato inesperado. Tente novamente.")
    return {k: dados.get(k, [] if k == "pendencias" else "") for k in SCHEMA["properties"]}
