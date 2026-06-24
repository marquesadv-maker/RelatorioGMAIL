import re
from typing import Dict, Any, List, Tuple

# ─── DISSATISFAÇÃO ────────────────────────────────────────────────────────────
DISSATISFACTION_PHRASES = [
    "ainda aguardo retorno", "continuo aguardando", "sem resposta",
    "preciso de uma posição", "não tive retorno", "gostaria de uma atualização",
    "não resolveram", "estou insatisfeito", "já faz alguns dias",
    "aguardando retorno", "sem posição", "não recebi resposta",
]

# ─── URGÊNCIA ─────────────────────────────────────────────────────────────────
URGENCY_KEYWORDS = [
    "urgente", "prazo", "vencimento", "audiência", "audiencia",
    "hoje", "imediato", "pagamento", "penhora", "liminar",
    "decisão", "decisao", "sentença", "sentenca", "recurso", "prazo fatal",
]

URGENCY_SUBJECTS = [
    "prazo", "audiência", "audiencia", "vencimento", "pagamento",
    "notificação", "notificacao", "penhora", "liminar", "sentença", "sentenca",
]

# ─── TRIBUNAL / PUSH DE PROCESSO ─────────────────────────────────────────────
TRIBUNAL_SENDERS = [
    "pje", "esaj", "projudi", "eproc", "e-proc", "tjsp", "tjrj", "tjmg",
    "trt", "tst", "stj", "stf", "carf", "cnj", "jusbrasil", "dje",
    "diario", "tribunal", "vara", "justica", "justiça", "jfsp", "trf",
    "noreply@", "no-reply@", "donotreply@",
]

TRIBUNAL_SUBJECTS = [
    "citação", "citacao", "intimação", "intimacao", "decisão judicial",
    "decisao judicial", "despacho", "sentença", "sentenca", "acórdão",
    "acordao", "publicação", "publicacao", "diário oficial", "diario oficial",
    "dje", "movimentação", "movimentacao", "ato ordinatório", "ato ordinatorio",
    "mandado", "ofício", "oficio", "notificação judicial", "notificacao judicial",
    "cumprimento de sentença", "auto de penhora", "certidão", "certidao",
]

# ─── DÚVIDA DE PROCESSO ───────────────────────────────────────────────────────
DUVIDA_SUBJECTS = [
    "qual o status", "como está", "como esta", "atualização do processo",
    "atualizacao do processo", "o que aconteceu", "quando vai", "qual a previsão",
    "qual a previsao", "andamento", "o que houve", "me informe", "como fica",
    "pergunta", "dúvida", "duvida", "quero saber", "preciso saber",
    "situação do processo", "situacao do processo",
]

DUVIDA_SNIPPETS = [
    "qual o status", "como está meu processo", "como esta meu processo",
    "tem novidade", "alguma novidade", "o que aconteceu com", "quando sai",
    "quando será", "quando sera", "o processo está", "o processo esta",
    "me diz", "me fala", "pode me informar", "gostaria de saber",
]

# ─── DOCUMENTOS DE DEFESA ─────────────────────────────────────────────────────
DEFESA_KEYWORDS = [
    "contestação", "contestacao", "petição", "peticao", "recurso ordinário",
    "recurso ordinario", "apelação", "apelacao", "defesa prévia", "defesa previa",
    "contrarrazões", "contrarrazoes", "embargos", "agravo", "habeas corpus",
    "mandado de segurança", "mandado de seguranca", "impugnação", "impugnacao",
    "protocolo de defesa", "documento de defesa", "procuração", "procuracao",
    "contrato de honorários", "contrato de honorarios", "substabelecimento",
]

# ─── COMERCIAL (filtrar do painel) ────────────────────────────────────────────
COMERCIAL_SENDERS = [
    "marketing@", "newsletter@", "noreply@mailchimp", "noreply@sendgrid",
    "contato@rdstation", "info@", "vendas@", "comercial@", "promocao@",
    "promoção@", "noticias@", "nuvemshop", "hotmart", "kiwify", "monetizze",
    "eduzz", "braip",
]

COMERCIAL_SUBJECTS = [
    "promoção", "promocao", "oferta", "desconto", "newsletter", "liquidação",
    "liquidacao", "black friday", "cyber monday", "compre agora", "adquira",
    "exclusivo para você", "não perca", "nao perca", "última chance",
    "ultima chance", "frete grátis", "frete gratis", "cupom", "assine",
    "cadastre-se", "unsubscribe", "cancelar inscrição",
]

COMERCIAL_SNIPPET_CLUES = [
    "unsubscribe", "cancelar inscrição", "remover da lista",
    "não quer mais receber", "nao quer mais receber",
]


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _text(t: Dict[str, Any]) -> str:
    return (t["subject"] + " " + t["snippet"] + " " + t.get("sender_raw", "")).lower()

def _subject(t: Dict[str, Any]) -> str:
    return t["subject"].lower()

def _sender(t: Dict[str, Any]) -> str:
    return (t.get("sender_raw", "") + " " + t.get("sender", "")).lower()

def _snippet(t: Dict[str, Any]) -> str:
    return t.get("snippet", "").lower()


# ─── DETECÇÃO DE TIPO ─────────────────────────────────────────────────────────

def detect_tipo(thread: Dict[str, Any]) -> str:
    """
    Classifica o tipo do e-mail:
    TRIBUNAL   — notificações judiciais / pushes de processo
    DUVIDA     — cliente perguntando sobre processo
    DEFESA     — documentos de defesa / petições
    COMERCIAL  — marketing / newsletter (ocultar do painel)
    CLIENTE    — demais mensagens de clientes
    """
    sender  = _sender(thread)
    subject = _subject(thread)
    snippet = _snippet(thread)
    text    = subject + " " + snippet

    # Comercial tem prioridade para remover do painel
    if (any(s in sender for s in COMERCIAL_SENDERS) or
            any(k in subject for k in COMERCIAL_SUBJECTS) or
            any(k in snippet for k in COMERCIAL_SNIPPET_CLUES)):
        return "COMERCIAL"

    # Tribunal / push de processo
    if (any(s in sender for s in TRIBUNAL_SENDERS) or
            any(k in subject for k in TRIBUNAL_SUBJECTS)):
        return "TRIBUNAL"

    # Documentos de defesa
    if any(k in text for k in DEFESA_KEYWORDS):
        return "DEFESA"

    # Dúvida de processo
    if (any(k in subject for k in DUVIDA_SUBJECTS) or
            any(k in snippet for k in DUVIDA_SNIPPETS)):
        return "DUVIDA"

    return "CLIENTE"


def detect_dissatisfaction(thread: Dict[str, Any]) -> Tuple[str, List[str]]:
    text = _text(thread)
    matched = [p for p in DISSATISFACTION_PHRASES if p in text]
    if len(matched) >= 3:
        return "ALTO", matched
    if len(matched) >= 1:
        return "MÉDIO", matched
    return "BAIXO", matched


def detect_urgency(thread: Dict[str, Any]) -> Tuple[bool, List[str]]:
    text = _text(thread)
    matched = [k for k in URGENCY_KEYWORDS if k in text]
    return bool(matched), matched


def has_urgent_subject(thread: Dict[str, Any]) -> bool:
    return any(k in _subject(thread) for k in URGENCY_SUBJECTS)


def classify_priority(thread: Dict[str, Any], tipo: str) -> Tuple[str, str]:
    dissat_risk, dissat_phrases = detect_dissatisfaction(thread)
    is_urgent, urgency_words    = detect_urgency(thread)
    no_reply = not thread["we_replied"]
    hours    = thread["hours_since_last"]
    reasons  = []

    # Tribunal sempre Alta (pode ter prazo embutido)
    if tipo == "TRIBUNAL":
        return "ALTA", "notificação judicial"

    if dissat_risk == "ALTO":
        reasons.append(f"insatisfação: '{dissat_phrases[0]}'")
    if no_reply and hours > 48:
        reasons.append(f"sem resposta há {hours:.0f}h")
    if is_urgent:
        reasons.append(f"urgência: {', '.join(urgency_words[:3])}")
    if has_urgent_subject(thread):
        reasons.append("assunto urgente")

    if reasons:
        return "ALTA", "; ".join(reasons)

    if thread.get("unread"):
        reasons.append("não lido")
    if dissat_risk == "MÉDIO":
        reasons.append(f"aguarda resposta ({dissat_phrases[0]})")
    if no_reply and hours <= 48:
        reasons.append(f"aguardando resposta há {hours:.0f}h")

    if reasons:
        return "MÉDIA", "; ".join(reasons)

    return "BAIXA", "sem urgência detectada"


# ─── ANÁLISE PRINCIPAL ────────────────────────────────────────────────────────

def analyze_threads(threads_data: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
    high, medium, low = [], [], []
    dissatisfied   = []
    unanswered_48h = []
    tribunal_list  = []
    duvida_list    = []
    defesa_list    = []
    # comercial é descartado silenciosamente

    for t in threads_data:
        tipo                        = detect_tipo(t)
        dissat_risk, dissat_phrases = detect_dissatisfaction(t)
        is_urgent, urgency_words    = detect_urgency(t)
        priority, reason            = classify_priority(t, tipo)

        entry = {
            **t,
            "priority": priority,
            "reason": reason,
            "tipo": tipo,
            "dissatisfaction_risk": dissat_risk,
            "dissatisfaction_phrases": dissat_phrases,
            "urgency_keywords": urgency_words,
        }

        # Comercial: fora do painel
        if tipo == "COMERCIAL":
            continue

        # Listas por tipo
        if tipo == "TRIBUNAL":
            tribunal_list.append(entry)
        elif tipo == "DUVIDA":
            duvida_list.append(entry)
        elif tipo == "DEFESA":
            defesa_list.append(entry)

        # Listas por prioridade (incluem todos os tipos exceto COMERCIAL)
        if priority == "ALTA":
            high.append(entry)
        elif priority == "MÉDIA":
            medium.append(entry)
        else:
            low.append(entry)

        if dissat_risk in ("MÉDIO", "ALTO") and dissat_phrases:
            dissatisfied.append(entry)

        if not t["we_replied"] and t["hours_since_last"] > 48:
            unanswered_48h.append(entry)

    unanswered_48h.sort(key=lambda x: x["hours_since_last"], reverse=True)

    return {
        "ALTA":          sorted(high,   key=lambda x: x["hours_since_last"], reverse=True),
        "MÉDIA":         sorted(medium, key=lambda x: x["hours_since_last"], reverse=True),
        "BAIXA":         low,
        "dissatisfied":  dissatisfied,
        "unanswered_48h": unanswered_48h,
        "tribunal":      sorted(tribunal_list, key=lambda x: x["hours_since_last"]),
        "duvida":        sorted(duvida_list,   key=lambda x: x["hours_since_last"], reverse=True),
        "defesa":        sorted(defesa_list,   key=lambda x: x["hours_since_last"], reverse=True),
    }
