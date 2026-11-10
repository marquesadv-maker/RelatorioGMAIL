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
    "Você preenche campos de e-mails do escritório Marques Advogados S/S (advocacia trabalhista empresarial) a partir de "
    "documentos processuais. A empresa cliente é a RECLAMADA; o autor da ação é o RECLAMANTE.\n"
    "Regras: (1) use SOMENTE o que estiver escrito no texto fornecido; nunca invente nem deduza nº de processo, partes, "
    "órgão, datas, horários, prazos, valores, links, nomes, modalidade ou resultado de decisão. "
    "(2) Em cada campo, \"trecho\" é a cópia LITERAL e curta (até 120 caracteres) do documento que sustenta o valor; "
    "sem trecho literal, deixe o valor vazio. (3) Dado ausente, ilegível ou ambíguo: valor vazio e liste o campo em \"pendencias\". "
    "(4) Datas em dd/mm/aaaa; horário no formato 14h30; valores em R$ 0.000,00; listas com um item por linha iniciado por \"- \". "
    "(5) A data do ato (audiência/perícia/prazo) não é a data de publicação, de assinatura ou de distribuição do documento. "
    "(6) Prazo judicial é o fixado pelo juízo; nunca calcule nem converta prazo. "
    "(7) Resumos: no máximo 3 frases objetivas, só com fatos do documento, sem avaliação nem prognóstico. "
    "(8) Blocos opcionais: \"incluir\" conforme a condição de uso e a prova no documento; só escreva \"texto\" quando o bloco não tiver texto-base. "
    "(9) Responda apenas o JSON pedido, sem comentários."
)

DESCRICOES = {
    "PROCESSO": "número único do processo (padrão CNJ 0000000-00.0000.0.00.0000)",
    "RECLAMANTE": "nome completo do reclamante (autor da ação)",
    "RECLAMADA": "razão social da empresa reclamada (ré), como consta no documento",
    "PARTE_A": "reclamante", "PARTE_B": "reclamada (empresa ré)",
    "DATA": "data (dd/mm/aaaa) do ato principal: audiência, perícia ou vencimento designado; não a de publicação do documento",
    "DATA_AUDIENCIA": "data (dd/mm/aaaa) da audiência", "HORARIO": "horário do ato (ex.: 14h30)",
    "MODALIDADE": "presencial, telepresencial ou híbrida", "TIPO_AUDIENCIA": "tipo: conciliação, instrução, una, inaugural...",
    "LINK": "link da sala virtual da audiência", "LOCAL": "endereço/local onde o ato ocorrerá",
    "LOCAL_OU_LINK": "endereço ou link do ato", "LINK_OU_ENDERECO": "link ou endereço do ato",
    "VARA": "vara/órgão julgador (ex.: 2ª Vara do Trabalho de São Paulo)", "ORGAO": "órgão/vara responsável", "CIDADE_UF": "cidade/UF do órgão",
    "VALOR_CAUSA": "valor da causa (R$)", "PRAZO": "prazo judicial concedido (ex.: 5 dias úteis), exatamente como no documento",
    "PRAZO_QUESITOS": "prazo para apresentar quesitos", "DATA_LIMITE": "data-limite fixada no documento (dd/mm/aaaa)",
    "OBJETO_PERICIA": "tipo/objeto da perícia (insalubridade, periculosidade, médica, contábil...)",
    "PERITO": "nome do perito nomeado", "ASSISTENTE_TECNICO": "nome do assistente técnico, se indicado no documento",
    "PRINCIPAIS_PEDIDOS": "resumo dos principais pedidos da inicial, em lista", "LISTA_PEDIDOS": "pedidos formulados na inicial, um por linha",
    "LISTA_CONDENACOES": "parcelas/obrigações da condenação, uma por linha", "VALOR_CONDENACAO": "valor provisório da condenação (R$)",
    "RESUMO_RESULTADO": "resultado da decisão em até 3 frases", "RESUMO_PROCESSO": "resumo do processo em até 3 frases",
    "RESUMO_NOTIFICACAO": "resumo da notificação em até 3 frases", "RESULTADO_FINAL": "resultado final do processo",
    "TIPO_DECISAO": "tipo da decisão (sentença, acórdão, despacho, decisão interlocutória)",
    "QUANTIDADE_TESTEMUNHAS": "número de testemunhas que cada parte pode levar", "NOME_CLIENTE": "nome do cliente destinatário",
    "NUMERO_NOTIFICACAO": "número da notificação", "VALOR_ACORDO": "valor total do acordo (R$)", "VALOR_PARCELA": "valor de cada parcela (R$)",
    "VENCIMENTO": "data de vencimento (dd/mm/aaaa)", "DATA_PROTOCOLO": "data do protocolo (dd/mm/aaaa)",
}
SO_USUARIO = {"PRAZO_INTERNO"}   # preenchido só pela regra do escritório (configuração), nunca pela IA
COMPLEXOS = re.compile(r"^(LISTA_|RESUMO|FUNDAMENT|PONTO_|TEMA_|PRINCIPAIS|DESCRICAO|OBRIGACAO|CRONOGRAMA|RELATORIO|HA_OU_NAO|CONSEQUENCIA|PARCELA_|ITEM_|RESULTADO|MOTIVO|ORIENTACAO)")

SCHEMA_PREENCHER = {
    "type": "object",
    "properties": {
        "codigo": {"type": "string"},
        "revisao": {"type": "array", "items": {"type": "object", "properties": {
            "nome": {"type": "string"}, "correto": {"type": "boolean"}, "valor": {"type": "string"}, "trecho": {"type": "string"}},
            "required": ["nome", "correto", "valor", "trecho"], "additionalProperties": False}},
        "campos": {"type": "array", "items": {"type": "object", "properties": {
            "nome": {"type": "string"}, "valor": {"type": "string"}, "trecho": {"type": "string"}},
            "required": ["nome", "valor", "trecho"], "additionalProperties": False}},
        "blocos": {"type": "array", "items": {"type": "object", "properties": {
            "nome": {"type": "string"}, "incluir": {"type": "boolean"}, "texto": {"type": "string"}},
            "required": ["nome", "incluir", "texto"], "additionalProperties": False}},
        "pendencias": {"type": "array", "items": {"type": "string"}},
        "observacoes": {"type": "string"},
    },
    "required": ["codigo", "revisao", "campos", "blocos", "pendencias", "observacoes"],
    "additionalProperties": False,
}
SCHEMA_VERIFICAR = {
    "type": "object",
    "properties": {"campos": {"type": "array", "items": {"type": "object", "properties": {
        "nome": {"type": "string"}, "valor": {"type": "string"}, "trecho": {"type": "string"}},
        "required": ["nome", "valor", "trecho"], "additionalProperties": False}}},
    "required": ["campos"], "additionalProperties": False,
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
            uso: Dict[str, int], esforco: str = "low") -> Dict[str, Any]:
    resp = client.beta.messages.create(
        model=MODELO_IA,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": REGRAS, "cache_control": {"type": "ephemeral"}}],
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": esforco, "format": {"type": "json_schema", "schema": schema}},
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
                campos["QUANTIDADE_TESTEMUNHAS"] = {"valor": str(_NUM.get(n, n)), "origem": "documento", "trecho": q.group(0), "confianca": "alta"}
            blocos[nome] = {"incluir": bool(q), "texto": None}
        elif "anexad" in cond:
            blocos[nome] = {"incluir": False, "texto": None}   # o advogado marca se for anexar
        elif not base or cond:
            blocos[nome] = {"incluir": False, "texto": None}
            incertos.append(nome)
        else:
            blocos[nome] = {"incluir": True, "texto": None}
    return blocos, incertos


def _normalizar(nome: str, valor: str) -> str:
    v = (valor or "").strip()
    if nome.startswith("DATA") or nome in ("VENCIMENTO", "ULTIMO_DIA"):
        mt = re.search(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", v)
        if mt:
            d, mo, a = mt.groups()
            return f"{int(d):02d}/{int(mo):02d}/{'20' + a if len(a) == 2 else a}"
    if nome.startswith("HORARIO"):
        mt = re.search(r"(\d{1,2})\s*(?:h|:|horas?)\s*(\d{2})?", v, re.I)
        if mt:
            h, mm = mt.groups()
            return f"{int(h)}h{mm}" if mm and mm != "00" else f"{int(h)}h"
    return v


class _Doc:
    """Texto do documento normalizado, para conferir se um valor citado pela IA realmente consta dele."""

    def __init__(self, texto: str):
        self.norm = re.sub(r"[^a-z0-9]", "", extrator._n(texto))
        self.datas = {d for _, d in extrator._datas(texto)}
        self.horas = set()
        for mt in extrator.HORA.finditer(texto):
            h = int(mt.group(1))
            if 0 <= h <= 23:
                mm = mt.group(2)
                self.horas.add(f"{h}h{mm}" if mm and mm != "00" else f"{h}h")

    def confere(self, nome: str, valor: str, trecho: str) -> bool:
        if nome.startswith("DATA") or nome in ("VENCIMENTO", "ULTIMO_DIA"):
            if valor in self.datas:
                return True
        if nome.startswith("HORARIO") and valor in self.horas:
            return True
        simp = lambda t: re.sub(r"[^a-z0-9]", "", extrator._n(t))
        v, t = simp(valor), simp(trecho)
        return bool(v and v in self.norm) or bool(t and len(t) >= 6 and t in self.norm)


def _trechos_modelo(m: Dict) -> str:
    paras = [p for p in re.split(r"\n\s*\n", m["corpo"]) if "{{" in p]
    return "\n".join(p.replace("\n", " ") for p in paras)[:1500]


def _descricao(c: str) -> str:
    return DESCRICOES.get(c) or (c.replace("_", " ").lower() + " (conforme o documento)")


def _pergunta_preencher(candidatos: List[Dict], faltam: List[str], revisar: Dict[str, Dict], confirmados: Dict[str, Dict],
                        blocos_ia: List[Dict[str, Any]], avisos: List[str], texto: str, instrucoes: str,
                        catalogo: Optional[str] = None) -> str:
    partes = []
    for m in candidatos:
        partes.append(f"MODELO {m['codigo']} — {m['titulo']}\nTrechos com campos: {_trechos_modelo(m)}")
    if len(candidatos) > 1:
        partes.append("Escolha UM dos modelos acima e informe o código em \"codigo\"; preencha só os campos dele.")
    else:
        partes.append(f"Use o modelo {candidatos[0]['codigo']} (informe-o em \"codigo\").")
    if catalogo:
        partes.append("Se NENHUM candidato servir, informe em \"codigo\" o código correto do catálogo abaixo e deixe campos/blocos vazios:\n" + catalogo)
    if faltam:
        partes.append("Campos a preencher (só com o que o documento traz):\n" + "\n".join(f"- {c}: {_descricao(c)}" for c in faltam))
    else:
        partes.append("Campos a preencher: (nenhum)")
    if revisar:
        partes.append("Valores lidos automaticamente que precisam de CONFERÊNCIA. Em \"revisao\", para cada um: correto=true se estiver certo; "
                      "se estiver errado, correto=false e o valor certo com trecho literal:\n" +
                      "\n".join(f"- {k} = \"{v['valor']}\" (trecho: \"{v['trecho']}\")" for k, v in revisar.items()))
    if confirmados:
        partes.append("Já confirmados (não repita): " + "; ".join(f"{k}={v['valor']}" for k, v in confirmados.items()))
    if blocos_ia:
        partes.append("Blocos opcionais a decidir (se incluir um bloco, preencha também os campos dele):\n" + "\n".join(
            f"- {b['nome']}: condição de uso = {b['condicao'] or '(nenhuma)'}; "
            f"{'tem texto-base (deixe texto vazio)' if b['tem_base'] else 'SEM texto-base: escreva o texto só se o documento trouxer a informação'}"
            + (f"; campos do bloco: {', '.join(b['campos'])}" if b["campos"] else "") for b in blocos_ia))
    if avisos:
        partes.append("Avisos da leitura automática: " + " ".join(avisos))
    if instrucoes.strip():
        partes.append("Instruções do advogado: " + instrucoes.strip()[:1500])
    partes.append("Documento:\n<<<\n" + extrator.recorte(texto, 12000) + "\n>>>" if texto else "Não há texto de documento além das instruções.")
    return "\n\n".join(partes)


def _guardar(campos: Dict[str, Dict], nome: str, valor: str, trecho: str, doc: _Doc, verificar_extra: bool = False) -> None:
    valor = _normalizar(nome, valor)
    ok = doc.confere(nome, valor, trecho)
    if nome == "PROCESSO" and not extrator.cnj_valido(valor):
        ok = False
    campos[nome] = {"valor": valor, "origem": "ia", "trecho": (trecho or "")[:160], "confianca": "alta" if ok else "media",
                    "verificar": (not ok) or verificar_extra}


# ─── Fluxo principal ─────────────────────────────────────────────────────────

def preencher_auto(codigo: str, instrucoes: str, email_ref: Optional[Dict[str, str]],
                   arquivos: List[Tuple[str, str, bytes]], aceitar_visao: bool = False,
                   client=None, agora=None, prazo_interno_dias: Optional[int] = None) -> Dict[str, Any]:
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
        if t:
            textos.append(t)
        else:
            sem_texto.append((nome, mime, dados))
    if email_ref:
        textos.insert(0, f"{email_ref.get('assunto', '')}\n{email_ref.get('texto', '')}")
    if instrucoes.strip():
        textos.append(instrucoes.strip())
    texto = "\n\n".join(textos)
    if not texto and not sem_texto:
        raise ValueError("Anexe um documento (PDF/imagem), use o e-mail aberto ou escreva as informações.")
    ia_disponivel = bool(chave()) or client is not None
    if sem_texto and not ia_disponivel and not texto:
        raise ValueError("Documento sem texto legível (PDF escaneado ou imagem): informe a chave da IA para que ela leia o arquivo.")

    def cli():
        return client if client is not None else _cliente()

    # 2) campos e modelo por regras
    campos, avisos = extrator.extrair(texto, agora) if texto else ({}, [])
    cls = {"codigo": codigo, "confianca": "alta", "candidatos": [codigo]} if codigo else extrator.classificar(texto, campos)
    candidatos = [modelos.por_codigo(c) for c in cls["candidatos"] if modelos.por_codigo(c)]
    catalogo = None
    if not candidatos or cls["confianca"] == "baixa":
        catalogo = "\n".join(f"{x['codigo']}|{x['titulo']}" for x in modelos.carregar())
    if not candidatos and texto and ia_disponivel:  # nenhum candidato: pede só o código (resposta minúscula)
        out = _chamar(cli(), [{"type": "text", "text": f"Modelos:\n{catalogo}\n\nDocumento:\n<<<\n{extrator.recorte(texto, 4000)}\n>>>\n"
                                                    "Qual modelo se aplica? Se nenhum, codigo vazio."}], SCHEMA_ESCOLHER, 300, uso)
        if modelos.por_codigo(out["codigo"]):
            candidatos = [modelos.por_codigo(out["codigo"])]
            cls = {"codigo": out["codigo"], "confianca": "media", "candidatos": [out["codigo"]]}
    if not candidatos:
        raise ValueError("Não consegui identificar o modelo. Escolha um modelo na lista e tente de novo."
                         if texto else "Documento sem texto legível: escolha o modelo para a IA ler o arquivo.")

    m = candidatos[0]
    ia_usada = False
    doc = _Doc(texto)
    aviso: List[str] = list(avisos)

    def preparar():
        bl, inc = _decidir_blocos_local(m, campos, texto)
        # prazo interno: só pela regra que o escritório configurou (nunca calculado por iniciativa própria)
        if "PRAZO_INTERNO" in (m["campos"]) and prazo_interno_dias and "DATA" in campos:
            d = extrator.dias_uteis_antes(campos["DATA"]["valor"], prazo_interno_dias)
            if d:
                campos["PRAZO_INTERNO"] = {"valor": d, "origem": "regra", "confianca": "media", "verificar": False,
                                           "trecho": f"{prazo_interno_dias} dia(s) útil(eis) antes de {campos['DATA']['valor']} (regra do escritório; feriados não considerados)"}
        necessarios = list(m["campos_corpo"]) + [c for n, b in bl.items() if b["incluir"] for c in m["blocos"][n]["campos"]]
        necessarios = list(dict.fromkeys(necessarios))
        return bl, inc, necessarios

    blocos, incertos, necessarios = preparar()
    faltam = [c for c in necessarios if c not in campos and c not in SO_USUARIO]
    revisar = {k: v for k, v in campos.items() if v.get("confianca") == "media" and v["origem"] in ("documento", "derivado") and k in m["campos"]}
    blocos_ia = [{"nome": n, "condicao": m["blocos"][n]["condicao"], "tem_base": bool(m["blocos"][n]["texto"].strip()),
                  "campos": [c for c in m["blocos"][n]["campos"] if c not in campos]} for n in incertos]
    precisa_ia = bool(faltam or revisar or (blocos_ia and texto) or cls["confianca"] != "alta" or sem_texto)

    # 3) IA: preenche automaticamente o que a leitura local não resolveu e confere o que ficou incerto
    ia_indisponivel = False
    if precisa_ia and ia_disponivel:
        if sem_texto and not aceitar_visao:
            return {"precisa_visao": [n for n, _m, _d in sem_texto], "modelo": m["codigo"]}
        imagens = [_bloco_arquivo(*a) for a in sem_texto]
        confirmados = {k: v for k, v in campos.items() if k not in revisar and k in m["campos"]}
        for rodada in range(2):  # a 2ª rodada só ocorre se a IA indicar outro modelo
            conteudo = list(imagens) + [{"type": "text", "text": _pergunta_preencher(
                candidatos[:3] if rodada == 0 else [m], faltam, revisar, confirmados, blocos_ia, avisos, texto, instrucoes,
                catalogo if rodada == 0 else None)}]
            esforco = "medium" if (faltam or blocos_ia or cls["confianca"] != "alta") else "low"
            out = _chamar(cli(), conteudo, SCHEMA_PREENCHER, 4000, uso, esforco)
            ia_usada = True
            novo = modelos.por_codigo(out.get("codigo") or "")
            if rodada == 0 and novo and novo["codigo"] != m["codigo"]:
                m = novo
                blocos, incertos, necessarios = preparar()
                faltam = [c for c in necessarios if c not in campos and c not in SO_USUARIO]
                revisar = {k: v for k, v in campos.items() if v.get("confianca") == "media" and v["origem"] in ("documento", "derivado") and k in m["campos"]}
                blocos_ia = [{"nome": n, "condicao": m["blocos"][n]["condicao"], "tem_base": bool(m["blocos"][n]["texto"].strip()),
                              "campos": [c for c in m["blocos"][n]["campos"] if c not in campos]} for n in incertos]
                catalogo = None
                continue
            break
        # conferência dos valores lidos localmente
        for r in out.get("revisao", []):
            atual = campos.get(r["nome"])
            if not atual or atual.get("confianca") != "media":
                continue
            if r["correto"]:
                atual["confianca"], atual["confirmado_ia"] = "alta", True
                if r["nome"] != "PROCESSO" or extrator.cnj_valido(atual["valor"]):
                    atual.pop("verificar", None)   # número com dígitos inválidos continua sinalizado
            elif (r["valor"] or "").strip():
                antigo = atual["valor"]
                _guardar(campos, r["nome"], r["valor"], r["trecho"], doc, verificar_extra=True)
                campos[r["nome"]]["corrigido_de"] = antigo
        # campos novos
        for c in out.get("campos", []):
            nome, valor = c["nome"], (c["valor"] or "").strip()
            if nome in m["campos"] and valor and nome not in SO_USUARIO and (nome not in campos or campos[nome].get("origem") == "pendente"):
                _guardar(campos, nome, valor, c["trecho"], doc)
        for b in out.get("blocos", []):
            if b["nome"] in m["blocos"]:
                base = m["blocos"][b["nome"]]["texto"].strip()
                blocos[b["nome"]] = {"incluir": bool(b["incluir"]), "texto": None if base else ((b["texto"] or "").strip() or None)}
        if out.get("observacoes"):
            aviso.append(out["observacoes"])
        blocos2, _inc2, necessarios = (blocos, None, list(dict.fromkeys(list(m["campos_corpo"]) + [c for n, b in blocos.items() if b["incluir"] for c in m["blocos"][n]["campos"]])))

        # 2ª passada: o que ficou vazio ou sem prova no documento é verificado (cita o trecho exato ou devolve vazio)
        suspeitos = [n for n in necessarios if n not in SO_USUARIO and (n not in campos or (campos[n]["origem"] == "ia" and campos[n].get("verificar")))]
        if suspeitos and uso["chamadas"] < 4:
            lista = "\n".join(f"- {n}: {_descricao(n)}" + (f" | valor proposto: \"{campos[n]['valor']}\"" if n in campos else " | ainda sem valor") for n in suspeitos)
            ver = _chamar(cli(), list(imagens) + [{"type": "text", "text":
                "Verifique no documento, campo a campo. Para cada campo devolva o valor CERTO com o trecho LITERAL do documento que o sustenta; "
                "se o documento não trouxer o dado (ou o valor proposto não constar), devolva valor vazio.\n" + lista +
                "\n\nDocumento:\n<<<\n" + extrator.recorte(texto, 12000) + "\n>>>"}], SCHEMA_VERIFICAR, 2000, uso, "medium")
            for c in ver.get("campos", []):
                nome, valor = c["nome"], (c["valor"] or "").strip()
                if nome not in suspeitos:
                    continue
                if valor and doc.confere(nome, _normalizar(nome, valor), c["trecho"]):
                    _guardar(campos, nome, valor, c["trecho"], doc)
                elif not valor and nome in campos and campos[nome]["origem"] == "ia":
                    campos.pop(nome)  # a IA não conseguiu sustentar o valor proposto: volta a pendente
    elif precisa_ia:
        ia_indisponivel = True
        aviso.append("IA não configurada: preenchi o que foi possível lendo o documento. Informe a chave da IA para ela completar e conferir o restante automaticamente.")

    # 4) monta o e-mail (listas e textos fixos do escritório, sem IA)
    valores = {k: v["valor"] for k, v in campos.items()}
    email = modelos.montar_email(m, valores, {n: {"incluir": b["incluir"], "texto": b["texto"]} for n, b in blocos.items()})
    necessarios = list(dict.fromkeys(list(m["campos_corpo"]) + [c for n, b in blocos.items() if b["incluir"] for c in m["blocos"][n]["campos"]]))
    saida_campos = {}
    for c in necessarios:
        v = campos.get(c)
        if v:
            saida_campos[c] = {k: v[k] for k in ("valor", "origem", "trecho", "verificar", "corrigido_de", "confirmado_ia") if k in v}
        else:
            saida_campos[c] = {"valor": "", "origem": "pendente", "trecho": ""}
    pendentes = [c for c, v in saida_campos.items() if not v["valor"]]
    return {
        "codigo": m["codigo"], "titulo": m["titulo"], "confianca": cls["confianca"],
        "assunto": email["assunto"], "corpo": email["corpo"],
        "campos": saida_campos,
        "blocos": {n: {"incluir": b["incluir"], "texto": b["texto"] if b["texto"] is not None else m["blocos"][n]["texto"],
                       "condicao": m["blocos"][n]["condicao"]} for n, b in blocos.items()},
        "pendencias": pendentes, "observacoes": " ".join(dict.fromkeys(aviso)), "ia_indisponivel": ia_indisponivel,
        "uso": {"ia": ia_usada,
                "campos_locais": sum(1 for v in saida_campos.values() if v["origem"] in ("documento", "automatico", "derivado", "regra")),
                "campos_ia": sum(1 for v in saida_campos.values() if v["origem"] == "ia"), **uso},
    }
