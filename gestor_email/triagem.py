"""
Triagem local da caixa de entrada.

1) Resgate do spam: mensagens que o Gmail mandou para o spam mas que são
   (a) de um remetente conhecido (cliente: já recebemos mensagem dele ou já
   escrevemos para ele) ou (b) notificações/intimações/citações de tribunais
   aparecem na caixa de entrada do MarquesPro, com aviso "veio do spam".
   Anúncios, promoções e qualquer outra coisa ficam de fora.
2) Anúncios: promoções e newsletters saem da caixa de entrada e vão para a
   pasta "Anúncios e promoções" (nada é apagado).

Tudo é feito só no MarquesPro: o Gmail só muda quando o usuário clica em
"Não é spam".
"""
import re
from typing import Any, Dict, List, Optional

from . import classify, db

DOMINIOS_OFICIAIS = (".jus.br", ".gov.br", ".mp.br", ".leg.br", ".def.br", ".oab.org.br")
CATEGORIAS_ANUNCIO = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_FORUMS"}
PALAVRAS_ANUNCIO = re.compile(
    r"promo[çc][ãa]o|oferta|desconto|liquida[çc][ãa]o|black friday|cupom|frete gr[áa]tis|compre|% off|"
    r"imperd[íi]vel|aproveite|sorteio|cashback|newsletter|webinar|inscreva-se|assine|cadastre-se|"
    r"lan[çc]amento|ganhe|gr[áa]tis|cancelar inscri[çc][ãa]o|descadastr|unsubscribe|e-?book|curso online",
    re.I,
)


def _dominio_oficial(email: str) -> bool:
    return any(email.endswith(d) for d in DOMINIOS_OFICIAIS)


def _notificacao_forte(m: Dict[str, Any], tipo: str, subtipo: Optional[str]) -> bool:
    """Notificação judicial de verdade: remetente oficial ou assunto de intimação/citação etc.
    (um simples "noreply@" não basta)."""
    return _dominio_oficial(m.get("from_email", "")) or (tipo == "TRIBUNAL" and subtipo not in (None, "Outras"))


def _comercial(m: Dict[str, Any], tipo: str) -> bool:
    labels = set(m.get("label_ids") or [])
    return bool(
        tipo == "COMERCIAL"
        or m.get("bulk")
        or labels & CATEGORIAS_ANUNCIO
        or PALAVRAS_ANUNCIO.search(f"{m.get('subject', '')} {m.get('snippet', '')[:160]}")
    )


def remetente_conhecido(account: str, m: Dict[str, Any]) -> bool:
    """Já escrevemos para ele, ele respondeu uma conversa nossa, ou já nos enviou mensagem não comercial."""
    email = (m.get("from_email") or "").lower()
    if not email:
        return False
    if db.one(
        "SELECT 1 AS x FROM messages x JOIN message_labels l ON l.account=x.account AND l.message_id=x.id AND l.label_id='SENT' "
        "WHERE x.account=? AND (x.thread_id=? OR lower(x.to_raw) LIKE ? OR lower(x.cc_raw) LIKE ?) LIMIT 1",
        (account, m["thread_id"], f"%{email}%", f"%{email}%"),
    ):
        return True
    return db.one(
        "SELECT 1 AS x FROM messages x WHERE x.account=? AND x.from_email=? AND x.id<>? AND x.bulk=0 "
        "AND COALESCE(x.tipo,'')<>'COMERCIAL' AND COALESCE(x.triagem,'') NOT IN ('anuncio') "
        "AND NOT EXISTS (SELECT 1 FROM message_labels l WHERE l.account=x.account AND l.message_id=x.id "
        "AND l.label_id IN ('SPAM','TRASH','CATEGORY_PROMOTIONS','CATEGORY_SOCIAL','CATEGORY_FORUMS')) LIMIT 1",
        (account, email, m["id"]),
    ) is not None


def classificar(account: str, m: Dict[str, Any]) -> Optional[str]:
    """Retorna 'resgatado:notificacao', 'resgatado:cliente', 'anuncio' ou None."""
    labels = set(m.get("label_ids") or [])
    if labels & {"TRASH", "SENT", "DRAFT"}:
        return None
    manual = db.triagem_manual(account, m["thread_id"])
    tipo, subtipo = classify.classify(m.get("from_raw", ""), m.get("subject", ""), m.get("snippet", ""))
    forte = _notificacao_forte(m, tipo, subtipo)
    if "SPAM" in labels:
        if forte:
            return "resgatado:notificacao"
        if remetente_conhecido(account, m) and not _comercial(m, tipo):
            return "resgatado:cliente"
        return None  # continua no spam
    if "INBOX" in labels:
        if manual == "inbox":
            return None
        if manual == "anuncio":
            return "anuncio"
        if _comercial(m, tipo) and not forte and not remetente_conhecido(account, m):
            return "anuncio"
    return None


def aplicar(account: str, m: Dict[str, Any]) -> Optional[str]:
    valor = classificar(account, m)
    db.set_triagem(account, m["id"], valor)
    return valor


def reprocessar(lote: int = 500) -> int:
    """Classifica mensagens do cache anteriores a esta função (triagem_v=0)."""
    total = 0
    while True:
        rows = db.rows("SELECT * FROM messages WHERE triagem_v=0 LIMIT ?", (lote,))
        if not rows:
            return total
        for r in rows:
            m = db.decode_message(r)
            m["thread_id"] = r["thread_id"]
            aplicar(r["account"], m)
            total += 1


def alterar_conversa(account: str, thread_id: str, valor: str) -> None:
    """Override manual ('inbox' ou 'anuncio') para a conversa inteira."""
    db.execute(
        "INSERT INTO triagem_manual (account, thread_id, valor) VALUES (?,?,?) "
        "ON CONFLICT(account, thread_id) DO UPDATE SET valor=excluded.valor", (account, thread_id, valor))
    for r in db.rows("SELECT * FROM messages WHERE account=? AND thread_id=?", (account, thread_id)):
        m = db.decode_message(r)
        m["thread_id"] = thread_id
        aplicar(account, m)


def revisar_spam(account: str) -> int:
    """Reclassifica o spam do cache (ex.: depois que mensagens do cliente foram sincronizadas)."""
    n = 0
    for r in db.rows(
        "SELECT m.* FROM messages m JOIN message_labels l ON l.account=m.account AND l.message_id=m.id "
        "WHERE m.account=? AND l.label_id='SPAM'", (account,)):
        m = db.decode_message(r)
        m["thread_id"] = r["thread_id"]
        aplicar(account, m)
        n += 1
    return n
