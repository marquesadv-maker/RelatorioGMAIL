"""
Pendências de tratativa, e-mails novos do dia e palavras em destaque.

- Pendência = o último e-mail do cliente na conversa contém uma pergunta/pedido e ninguém do
  escritório respondeu depois. Some sozinha quando uma resposta é enviada (pelo Gmail ou pela
  ferramenta) e também pode ser concluída ou colocada "em execução" manualmente.
- Novo do dia = conversa aberta hoje por um remetente externo (fora da cadeia), que não é
  notificação judicial nem anúncio.
- Palavras em destaque = termos (intimação, notificação...) procurados no assunto e no trecho.
"""
import json
import re
import time
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from . import db
from .triagem import DOMINIOS_OFICIAIS

JANELA_DIAS = 60  # só procura perguntas sem resposta nos últimos N dias
STATUS = ("pendente", "em_execucao", "concluida")

_AUTOMATICOS = re.compile(r"(no-?reply|noreply|do-?not-?reply|mailer-daemon|postmaster|notifications?@|newsletter)", re.I)
_PERGUNTA = re.compile(
    r"(\?|\bpoderia(?:m)?\b|\bgostaria\b|\bgostariamos\b|\bfavor\s+(?:informar|enviar|verificar|confirmar|retornar)\b|"
    r"\bpor\s+favor\b|\bpreciso\s+saber\b|\bprecisamos\s+saber\b|\bsolicito\b|\bsolicitamos\b|\baguardo\s+(?:retorno|resposta|posicionamento)\b|"
    r"\baguardamos\s+(?:retorno|resposta|posicionamento)\b|\bduvida\b|\b(?:me|nos)\s+(?:informe|avise|diga|retorne)\b|"
    r"\bqual\s+(?:o|a|e)\b|\bquando\s+(?:sera|vai|vamos|podemos)\b|\bcomo\s+(?:fica|proceder|devemos|faco)\b|\balguma\s+novidade\b|"
    r"\bpode(?:ria)?\s+(?:me|nos|verificar|informar|confirmar)\b)")


def remetente_oficial(email: str) -> bool:
    """Tribunal/órgão público (e não um cliente que apenas comenta uma intimação)."""
    return any((email or "").lower().endswith(d) for d in DOMINIOS_OFICIAIS)


def oficial_sql(alias: str = "m") -> str:
    return "(" + " OR ".join(f"lower({alias}.from_email) LIKE '%{d}'" for d in DOMINIOS_OFICIAIS) + ")"


def sem_acento(t: str) -> str:
    return unicodedata.normalize("NFD", (t or "").lower()).encode("ascii", "ignore").decode()


def palavras_configuradas() -> List[str]:
    return [p.strip() for p in re.split(r"[,;\n]+", db.get_setting("palavras_destaque") or "") if p.strip()]


def achar_palavras(texto: str, palavras: Optional[List[str]] = None) -> List[str]:
    """Palavras em destaque presentes no texto (sem diferenciar maiúsculas ou acentos)."""
    t = sem_acento(texto)
    return [p for p in (palavras if palavras is not None else palavras_configuradas()) if sem_acento(p) and sem_acento(p) in t]


def tem_pergunta(texto: str) -> bool:
    return bool(_PERGUNTA.search(sem_acento(texto)))


def trecho_pergunta(texto: str, limite: int = 220) -> str:
    """Frase que contém a pergunta (ou o começo do texto)."""
    limpo = re.sub(r"\s+", " ", texto or "").strip()
    frases = re.split(r"(?<=[.!?])\s+", limpo)
    achada = next((f for f in frases if "?" in f), None) or next((f for f in frases if tem_pergunta(f)), None) or limpo
    return achada[:limite] + ("…" if len(achada) > limite else "")


def _enderecos_proprios() -> Set[str]:
    r = {x["email"].lower() for x in db.rows("SELECT email FROM accounts")}
    r |= {x["email"].lower() for x in db.rows("SELECT email FROM send_as")}
    return r


def _texto(m: Dict[str, Any]) -> str:
    corpo = ""
    if m.get("body_json"):
        try:
            b = json.loads(m["body_json"])
            corpo = b.get("text") or re.sub(r"<[^>]+>", " ", b.get("html") or "")
        except ValueError:
            corpo = ""
    if corpo:
        # só o texto novo: corta a citação das mensagens anteriores
        corpo = re.split(r"\n\s*(?:Em .{5,80} escreveu:|On .{5,80} wrote:|-{3,}\s*Mensagem original)", corpo)[0]
    return f"{m.get('subject') or ''}. {corpo or m.get('snippet') or ''}"


def _candidata(m: Dict[str, Any], proprios: Set[str], labels: List[str]) -> bool:
    if "SENT" in labels or "TRASH" in labels or "DRAFT" in labels:
        return False
    if (m["from_email"] or "").lower() in proprios or _AUTOMATICOS.search(m["from_email"] or ""):
        return False
    if m["bulk"] or m["triagem"] == "anuncio" or (m["tipo"] == "TRIBUNAL" and remetente_oficial(m["from_email"])):
        return False
    if "SPAM" in labels and not (m["triagem"] or "").startswith("resgatado"):
        return False
    return True


def detectar(account: Optional[str] = None) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Conversas com pergunta do cliente sem resposta: {(conta, conversa): dados}."""
    desde = int((time.time() - JANELA_DIAS * 86400) * 1000)
    sql = ("SELECT account, id, thread_id, internal_date, from_name, from_email, subject, snippet, label_ids, bulk, "
           "triagem, tipo, body_json FROM messages WHERE internal_date>=?" + (" AND account=?" if account else "") +
           " ORDER BY internal_date")
    proprios = _enderecos_proprios()
    por_conversa: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for m in db.rows(sql, [desde] + ([account] if account else [])):
        por_conversa.setdefault((m["account"], m["thread_id"]), []).append(m)
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for chave, ms in por_conversa.items():
        ultima_pergunta = None
        ultima_externa = None
        ultimo_envio = 0
        for m in ms:
            labels = json.loads(m["label_ids"])
            if "SENT" in labels:
                ultimo_envio = max(ultimo_envio, m["internal_date"])
            elif _candidata(m, proprios, labels):
                ultima_externa = m
        if ultima_externa and ultima_externa["internal_date"] > ultimo_envio:
            texto = _texto(ultima_externa)
            if tem_pergunta(texto):
                ultima_pergunta = (ultima_externa, texto)
        if ultima_pergunta:
            m, texto = ultima_pergunta
            out[chave] = {"message_id": m["id"], "recebido": m["internal_date"], "assunto": ms[0]["subject"],
                          "de_nome": m["from_name"] or m["from_email"], "de_email": m["from_email"],
                          "trecho": trecho_pergunta(texto.split(". ", 1)[1] if ". " in texto else texto)}
    return out


def _linhas_estado(account: Optional[str]) -> List[Dict[str, Any]]:
    return db.rows("SELECT * FROM pendencias" + (" WHERE account=?" if account else "") + " ORDER BY atualizado DESC",
                   [account] if account else [])


def _ultima_externa(account: str, thread_id: str) -> Optional[Dict[str, Any]]:
    proprios = _enderecos_proprios()
    achada = None
    for m in db.rows("SELECT id, internal_date, from_name, from_email, subject, snippet, label_ids, bulk, triagem, tipo, body_json "
                     "FROM messages WHERE account=? AND thread_id=? ORDER BY internal_date", (account, thread_id)):
        labels = json.loads(m["label_ids"])
        if "SENT" not in labels and (m["from_email"] or "").lower() not in proprios:
            achada = m
    return achada


def _dias(ms: int) -> int:
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return max(0, (hoje - datetime.fromtimestamp(ms / 1000).replace(hour=0, minute=0, second=0, microsecond=0)).days)


def _item(chave, d: Dict[str, Any], status: str, origem: str, nota: str, atualizado, por) -> Dict[str, Any]:
    return dict(d, account=chave[0], thread_id=chave[1], status=status, origem=origem, nota=nota or "",
                atualizado=atualizado, concluido_por=por,
                dias_espera=_dias(d["recebido"]) if d.get("recebido") else 0)


def _dados_da_linha(chave, e: Dict[str, Any]) -> Dict[str, Any]:
    m = _ultima_externa(*chave) or {}
    base = db.one("SELECT subject FROM messages WHERE account=? AND thread_id=? ORDER BY internal_date LIMIT 1", chave) or {}
    return {"message_id": e["message_id"], "recebido": m.get("internal_date") or 0, "assunto": base.get("subject") or "",
            "de_nome": m.get("from_name") or m.get("from_email") or "", "de_email": m.get("from_email") or "",
            "trecho": trecho_pergunta(_texto(m)) if m else ""}


def listar(account: Optional[str] = None) -> List[Dict[str, Any]]:
    """Todas as pendências (abertas, em execução e concluídas), já com o estado manual aplicado."""
    detectadas = detectar(account)
    estados: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]] = {}
    for e in _linhas_estado(account):
        estados.setdefault((e["account"], e["thread_id"]), {})[e["message_id"]] = e
    itens: List[Dict[str, Any]] = []
    for chave, d in detectadas.items():
        e = estados.get(chave, {}).get(d["message_id"])
        itens.append(_item(chave, d, e["status"] if e else "pendente", e["origem"] if e else "detectada",
                           e["nota"] if e else "", e["atualizado"] if e else None, e["concluido_por"] if e else None))
    for chave, linhas in estados.items():
        det = detectadas.get(chave)
        concluidas = [e for e in linhas.values() if e["status"] == "concluida" and not (det and det["message_id"] == e["message_id"])]
        if concluidas and not (det and det["message_id"] not in linhas):
            e = max(concluidas, key=lambda x: x["atualizado"])
            itens.append(_item(chave, _dados_da_linha(chave, e), "concluida", e["origem"], e["nota"], e["atualizado"], e["concluido_por"]))
        if det:
            continue  # pergunta nova detectada tem prioridade sobre marcações manuais antigas
        for e in linhas.values():
            if e["status"] != "concluida" and e["origem"] == "manual":
                itens.append(_item(chave, _dados_da_linha(chave, e), e["status"], "manual", e["nota"], e["atualizado"], None))
    ordem = {"pendente": 0, "em_execucao": 1, "concluida": 2}
    itens.sort(key=lambda i: (ordem[i["status"]], i["recebido"] if i["status"] != "concluida" else 0, ))
    concl = [i for i in itens if i["status"] == "concluida"]
    concl.sort(key=lambda i: i["atualizado"] or "", reverse=True)
    return [i for i in itens if i["status"] != "concluida"] + concl


def contar(account: Optional[str] = None) -> Dict[str, int]:
    its = listar(account)
    return {"abertas": sum(1 for i in its if i["status"] == "pendente"),
            "em_execucao": sum(1 for i in its if i["status"] == "em_execucao"),
            "concluidas": sum(1 for i in its if i["status"] == "concluida")}


def definir(account: str, thread_id: str, status: str, nota: str = "", message_id: Optional[str] = None, por: str = "manual"):
    """Marca a pendência da conversa: pendente, em_execucao ou concluida (sem apagar histórico)."""
    if status not in STATUS:
        raise ValueError("Situação inválida")
    atual = detectar(account).get((account, thread_id))
    ext = _ultima_externa(account, thread_id)
    mid = message_id or (atual or {}).get("message_id") or (ext or {}).get("id")
    if not mid:
        raise ValueError("Conversa sem mensagem de cliente para acompanhar")
    origem = "detectada" if atual and atual["message_id"] == mid else "manual"
    db.execute(
        "INSERT INTO pendencias (account, thread_id, message_id, status, origem, nota, concluido_por) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(account, thread_id, message_id) DO UPDATE SET status=excluded.status, nota=excluded.nota, "
        "origem=CASE WHEN pendencias.origem='manual' THEN 'manual' ELSE excluded.origem END, "
        "concluido_por=excluded.concluido_por, atualizado=datetime('now','localtime')",
        (account, thread_id, mid, status, origem, nota or "", por if status == "concluida" else None))


def concluir_por_resposta(account: str, thread_id: str):
    """Chamado ao enviar uma resposta pela ferramenta: encerra a pendência aberta dessa conversa."""
    abertas = [e for e in _linhas_estado(account) if e["thread_id"] == thread_id and e["status"] != "concluida"]
    det = detectar(account).get((account, thread_id))
    if det and not any(e["message_id"] == det["message_id"] for e in abertas):
        abertas.append({"message_id": det["message_id"], "nota": ""})
    for e in abertas:
        definir(account, thread_id, "concluida", e.get("nota") or "", e["message_id"], por="resposta")


# ─── Novos do dia (fora da cadeia) ──────────────────────────────────────────────

def novo_sql(alias: str = "m") -> str:
    """Condição SQL: primeira mensagem da conversa, de hoje, vinda de fora (não enviada, não notificação, não anúncio)."""
    return (f"({alias}.internal_date >= ? AND {alias}.internal_date = (SELECT MIN(g.internal_date) FROM messages g "
            f"WHERE g.account={alias}.account AND g.thread_id={alias}.thread_id) "
            f"AND NOT EXISTS (SELECT 1 FROM message_labels sx WHERE sx.account={alias}.account AND sx.message_id={alias}.id "
            f"AND sx.label_id IN ('SENT','DRAFT','TRASH')) AND NOT (COALESCE({alias}.tipo,'')='TRIBUNAL' AND {oficial_sql(alias)}) "
            f"AND COALESCE({alias}.triagem,'')<>'anuncio' AND {alias}.bulk=0)")


def inicio_do_dia_ms() -> int:
    return int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
