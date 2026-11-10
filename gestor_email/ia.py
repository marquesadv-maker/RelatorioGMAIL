"""
Preenchimento de modelos de e-mail com IA (Claude, da Anthropic), feito para gastar poucos tokens.

Ordem de trabalho (o que for possível é resolvido no próprio computador):
 1. Lê o texto dos PDFs localmente (sem IA).
 2. Extrai por regras: nº do processo, data, horário, modalidade, link, partes.
 3. Escolhe o modelo por regras (seção "Seleção automática" da skill).
 4. Só chama a IA se faltar dado, houver dúvida entre modelos ou trechos opcionais a decidir.
    A chamada leva um prompt mínimo (regras curtas + trechos do modelo candidato + só o que falta
    + recorte do documento) e a IA devolve apenas os campos, não o e-mail inteiro. O e-mail é
    montado aqui, com as listas e textos fixos do escritório, sem passar pela IA.
 5. PDF escaneado/imagem só vai à IA se o usuário confirmar (custa mais tokens).

O usuário sempre confere os dados na tela antes de inserir o texto no e-mail.
A chave da API fica só neste computador (dados/ia.json ou ANTHROPIC_API_KEY).
"""
import base64
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import config, extrator, modelos

MODELO_IA = os.environ.get("GESTOR_IA_MODELO", "claude-opus-5-5")
ARQ_CONFIG = os.path.join(config.DATA_DIR, "ia.json")

TIPOS_ACEITOS = {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp"}
LIMITE_BYTES = 25 * 1024 * 1024
# Campos que só o advogado define (a IA não tem como saber)
SO_USUARIO = {"PRAZO_INTERNO"}

REGRAS = (
    "Você preenche campos de e-mails do escritório Marques Advogados S/S a partir de documentos processuais.\n"
    "Regras: (1) use SOMENTE o que estiver escrito no texto fornecido; nunca invente nem deduza nº de processo, "
    "partes, órgão, datas, horários, prazos, valores, links, nomes, modalidade ou resultado de decisão. "
    "(2) Dado ausente ou ilegível: valor vazio e inclua o campo em \"pendencias\". "
    "(3) Datas em dd/mm/aaaa; horário no formato 14h30. "
    "(4) Em cada campo, \"trecho\" é a cópia literal e curta (até 120 caracteres) do documento que sustenta o valor. "
    "(5) Blocos opcionais: \"incluir\" conforme a condição de uso; só escreva \"texto\" quando o bloco não tiver texto-base. "
    "(6) Responda apenas o JSON pedido, sem comentários."
)

SCHEMA_PREENCHER = {
    "type": "object",
    "properties": {
        "codigo": {"type": "string"},
        "campos": {"type": "array", "items": {"type": "object", "properties": {
            "nome": {"type": "string"}, "valor": {"type": "string"}, "trecho": {"type": "string"}},
            "required": ["nome", "valor", "trecho"], "additionalProperties": False}},
        "blocos": {"type": "array", "items": {"type": "object", "properties": {
            "nome": {"type": "string"}, "incluir": {"type": "boolean"}, "texto": {"type": "string"}},
            "required": ["nome", "incluir", "texto"], "additionalProperties": False}},
        "pendencias": {"type": "array", "items": {"type": "string"}},
        "observacoes": {"type": "string"},
    },
    "required": ["codigo", "campos", "blocos", "pendencias", "observacoes"],
    "additionalProperties": False,
}
SCHEMA_ESCOLHER = {
    "type": "object",
    "properties": {"codigo": {"type": "string"}, "motivo": {"type": "string"}},
    "required": ["codigo", "motivo"], "additionalProperties": False,
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


# ─── Chamadas à API ──────────────────────────────────────────────────────────

def _cliente():
    key = chave()
    if not key:
        raise RuntimeError("IA não configurada: informe a chave da API (ícone de brilho na janela de escrita).")
    import anthropic
    return anthropic.Anthropic(api_key=key)


def _chamar(client, conteudo: List[Dict[str, Any]], schema: Dict[str, Any], max_tokens: int,
            uso: Dict[str, int]) -> Dict[str, Any]:
    resp = client.beta.messages.create(
        model=MODELO_IA,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": REGRAS, "cache_control": {"type": "ephemeral"}}],
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": conteudo}],
    )
    u = getattr(resp, "usage", None)
    if u is not None:
        uso["chamadas"] += 1
        uso["entrada"] += getattr(u, "input_tokens", 0) or 0
        uso["saida"] += getattr(u, "output_tokens", 0) or 0
        uso["cache"] += getattr(u, "cache_read_input_tokens", 0) or 0
    if resp.stop_reason == "refusal":
        raise RuntimeError("A IA não processou este pedido. Preencha o modelo manualmente.")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("A resposta da IA ficou incompleta. Tente novamente com menos documentos.")
    texto = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
    try:
        return json.loads(texto)
    except ValueError:
        raise RuntimeError("A IA devolveu uma resposta em formato inesperado. Tente novamente.")


def _bloco_arquivo(nome: str, mime: str, dados: bytes) -> Dict[str, Any]:
    b64 = base64.standard_b64encode(dados).decode("ascii")
    if mime == "application/pdf":
        return {"type": "document", "title": nome[:200], "source": {"type": "base64", "media_type": mime, "data": b64}}
    return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}}


# ─── Decisões locais ─────────────────────────────────────────────────────────

_NUM = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "três": 3, "quatro": 4, "cinco": 5, "seis": 6}


def _decidir_blocos_local(m: Dict, campos: Dict[str, Dict], texto: str) -> Tuple[Dict[str, Dict], List[str]]:
    """Decide por regras o que dá para decidir; devolve (blocos, nomes dos blocos que dependem da IA)."""
    blocos: Dict[str, Dict] = {}
    incertos: List[str] = []
    for nome, bl in m["blocos"].items():
        base = bl["texto"].strip()
        cond = (bl["condicao"] or "").lower()
        if nome.startswith("BLOCO_LINK"):
            blocos[nome] = {"incluir": "LINK" in campos, "texto": None}
        elif nome == "BLOCO_TESTEMUNHAS":
            q = re.search(r"\b(\d+|um|uma|dois|duas|tr[eê]s|quatro|cinco|seis)\s+testemunhas?\b", texto, re.I)
            if q:
                n = q.group(1).lower()
                campos["QUANTIDADE_TESTEMUNHAS"] = {"valor": str(_NUM.get(n, n)), "origem": "documento", "trecho": q.group(0)}
            blocos[nome] = {"incluir": bool(q), "texto": None}
        elif "anexad" in cond:
            blocos[nome] = {"incluir": False, "texto": None}   # o advogado marca se anexar
        elif not base or cond:
            blocos[nome] = {"incluir": False, "texto": None}
            incertos.append(nome)
        else:
            blocos[nome] = {"incluir": True, "texto": None}
    return blocos, incertos


def _confere(valor: str, trecho: str, texto_norm: str) -> bool:
    """O valor (ou o trecho citado pela IA) aparece mesmo no documento?"""
    simp = lambda t: re.sub(r"[^a-z0-9]", "", extrator._n(t))
    v, t = simp(valor), simp(trecho)
    return bool(v and v in texto_norm) or bool(t and len(t) >= 6 and t in texto_norm)


def _trechos_modelo(m: Dict) -> str:
    paras = [p for p in re.split(r"\n\s*\n", m["corpo"]) if "{{" in p]
    return "\n".join(p.replace("\n", " ") for p in paras)[:1500]


def _pergunta_preencher(candidatos: List[Dict], campos_ok: Dict, faltam: List[str], blocos_ia: List[Dict[str, Any]],
                        texto: str, instrucoes: str) -> str:
    partes = []
    for m in candidatos:
        partes.append(f"MODELO {m['codigo']} — {m['titulo']}\nTrechos com campos: {_trechos_modelo(m)}")
    if len(candidatos) > 1:
        partes.append("Escolha UM dos modelos acima e informe o código em \"codigo\"; preencha só os campos dele.")
    else:
        partes.append(f"Use o modelo {candidatos[0]['codigo']} (informe-o em \"codigo\").")
    partes.append("Campos a preencher: " + (", ".join(faltam) if faltam else "(nenhum)"))
    if blocos_ia:
        partes.append("Blocos opcionais a decidir:\n" + "\n".join(
            f"- {b['nome']}: condição de uso = {b['condicao'] or '(nenhuma)'}; "
            f"{'tem texto-base (deixe texto vazio)' if b['tem_base'] else 'SEM texto-base: escreva o texto só se o documento trouxer a informação'}"
            for b in blocos_ia))
    if campos_ok:
        partes.append("Já extraído (não repita): " + "; ".join(f"{k}={v['valor']}" for k, v in campos_ok.items()))
    if instrucoes.strip():
        partes.append("Instruções do advogado: " + instrucoes.strip()[:1500])
    partes.append("Documento:\n<<<\n" + extrator.recorte(texto) + "\n>>>" if texto else "Não há texto de documento além das instruções.")
    return "\n\n".join(partes)


# ─── Fluxo principal ─────────────────────────────────────────────────────────

def preencher_auto(codigo: str, instrucoes: str, email_ref: Optional[Dict[str, str]],
                   arquivos: List[Tuple[str, str, bytes]], aceitar_visao: bool = False,
                   client=None, agora=None) -> Dict[str, Any]:
    if sum(len(d) for _, _, d in arquivos) > LIMITE_BYTES:
        raise ValueError("Arquivos muito grandes para a IA (limite de 25 MB no total).")
    uso = {"chamadas": 0, "entrada": 0, "saida": 0, "cache": 0}
    for _, mime, _d in arquivos:
        if mime not in TIPOS_ACEITOS:
            raise ValueError("Formato não aceito. Use PDF, PNG ou JPG.")

    # 1) texto local
    textos, sem_texto = [], []
    for nome, mime, dados in arquivos:
        t = extrator.texto_do_arquivo(nome, mime, dados)
        (textos if t else sem_texto).append(t if t else (nome, mime, dados))
    if email_ref:
        textos.insert(0, f"{email_ref.get('assunto', '')}\n{email_ref.get('texto', '')}")
    if instrucoes.strip():
        textos.append(instrucoes.strip())
    texto = "\n\n".join(textos)
    if not texto and not sem_texto:
        raise ValueError("Anexe um documento (PDF/imagem), use o e-mail aberto ou escreva as informações.")

    # 2) campos e modelo por regras
    campos: Dict[str, Dict[str, Any]] = extrator.extrair_campos(texto, agora) if texto else {}
    cls = {"codigo": codigo, "confianca": "alta", "candidatos": [codigo]} if codigo else extrator.classificar(texto, campos)
    candidatos = [modelos.por_codigo(c) for c in cls["candidatos"] if modelos.por_codigo(c)]
    ia_disponivel = bool(chave()) or client is not None
    aviso: List[str] = []

    def cli():
        return client if client is not None else _cliente()

    # 2b) sem nenhum candidato: pede só o código à IA (resposta minúscula)
    if not candidatos and texto and ia_disponivel:
        catalogo = "\n".join(f"{x['codigo']}|{x['titulo']}" for x in modelos.carregar())
        out = _chamar(cli(), [{"type": "text", "text": f"Modelos:\n{catalogo}\n\nDocumento:\n<<<\n{extrator.recorte(texto, 3500)}\n>>>\n"
                                                    "Qual modelo se aplica? Se nenhum, codigo vazio."}], SCHEMA_ESCOLHER, 300, uso)
        if modelos.por_codigo(out["codigo"]):
            candidatos = [modelos.por_codigo(out["codigo"])]
            cls = {"codigo": out["codigo"], "confianca": "media", "candidatos": [out["codigo"]]}
    if not candidatos:
        raise ValueError("Não consegui identificar o modelo. Escolha um modelo na lista e tente de novo."
                         if texto else "Documento sem texto legível: escolha o modelo e confirme o envio à IA.")

    m = candidatos[0]
    blocos, incertos = _decidir_blocos_local(m, campos, texto)
    faltam = [c for c in m["campos_corpo"] if c not in campos and c not in SO_USUARIO]
    faltam += [c for b in m["blocos"].values() for c in b["campos"] if c not in campos and c not in faltam and c not in SO_USUARIO
               and blocos.get(next(k for k, v in m["blocos"].items() if v is b), {}).get("incluir")]
    blocos_ia = [{"nome": n, "condicao": m["blocos"][n]["condicao"], "tem_base": bool(m["blocos"][n]["texto"].strip())} for n in incertos]
    precisa_ia = bool(faltam or (blocos_ia and texto) or cls["confianca"] != "alta" or sem_texto)

    # 3) IA só se necessário
    ia_usada = False
    if precisa_ia and ia_disponivel:
        if sem_texto and not aceitar_visao:
            return {"precisa_visao": [n for n, _m, _d in sem_texto], "modelo": m["codigo"]}
        conteudo: List[Dict[str, Any]] = [_bloco_arquivo(*a) for a in sem_texto] if aceitar_visao else []
        conteudo.append({"type": "text", "text": _pergunta_preencher(candidatos[:3], campos, faltam, blocos_ia, texto, instrucoes)})
        out = _chamar(cli(), conteudo, SCHEMA_PREENCHER, 3000, uso)
        ia_usada = True
        if modelos.por_codigo(out["codigo"]) and out["codigo"] in {c["codigo"] for c in candidatos}:
            m = modelos.por_codigo(out["codigo"])
            blocos, _incertos = _decidir_blocos_local(m, campos, texto)
        texto_norm = re.sub(r"[^a-z0-9]", "", extrator._n(texto))
        for c in out["campos"]:
            nome, valor = c["nome"], (c["valor"] or "").strip()
            if nome in m["campos"] and valor and nome not in campos and nome not in SO_USUARIO:
                ok = nome in ("DATA", "HORARIO", "PERIODO") or _confere(valor, c["trecho"], texto_norm)
                campos[nome] = {"valor": valor, "origem": "ia", "trecho": c["trecho"][:160], "verificar": not ok}
        for b in out["blocos"]:
            if b["nome"] in m["blocos"]:
                blocos[b["nome"]] = {"incluir": bool(b["incluir"]), "texto": (b["texto"] or None) if not m["blocos"][b["nome"]]["texto"].strip() else None}
        if out["observacoes"]:
            aviso.append(out["observacoes"])
    elif precisa_ia:
        aviso.append("IA não configurada: preenchi o que foi possível lendo o documento. Complete os campos em amarelo ou informe a chave da IA.")

    # 4) monta o e-mail (listas e textos fixos do escritório, sem IA)
    valores = {k: v["valor"] for k, v in campos.items()}
    email = modelos.montar_email(m, valores, {n: {"incluir": b["incluir"], "texto": b["texto"]} for n, b in blocos.items()})
    necessarios = list(dict.fromkeys(m["campos_corpo"] + [c for n, b in blocos.items() if b["incluir"] for c in m["blocos"][n]["campos"]]))
    saida_campos = {}
    for c in necessarios:
        saida_campos[c] = campos.get(c) or {"valor": "", "origem": "pendente", "trecho": ""}
    pendentes = [c for c, v in saida_campos.items() if not v["valor"]]
    locais = sum(1 for v in saida_campos.values() if v["origem"] in ("documento", "automatico"))
    return {
        "codigo": m["codigo"], "titulo": m["titulo"], "confianca": cls["confianca"],
        "assunto": email["assunto"], "corpo": email["corpo"],
        "campos": saida_campos,
        "blocos": {n: {"incluir": b["incluir"], "texto": b["texto"] if b["texto"] is not None else m["blocos"][n]["texto"],
                       "condicao": m["blocos"][n]["condicao"]} for n, b in blocos.items()},
        "pendencias": pendentes, "observacoes": " ".join(aviso),
        "uso": {"ia": ia_usada, "campos_locais": locais, "campos_ia": sum(1 for v in saida_campos.values() if v["origem"] == "ia"), **uso},
    }
