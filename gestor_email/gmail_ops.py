"""
Operações sobre a API do Gmail: leitura, envio, encaminhamento,
etiquetas e assinaturas.

Regra de ouro: nenhuma função deste módulo remove a etiqueta UNREAD nem
retira mensagens da caixa de entrada. Abrir uma mensagem pelo Gestor não
a marca como lida no Gmail, preservando a leitura pela controladoria.
"""
import base64
import html
import io
import mimetypes
import re
from email.message import EmailMessage
from email.utils import formataddr, getaddresses, make_msgid, parseaddr, formatdate
from typing import Any, Dict, Iterable, List, Optional, Tuple

from googleapiclient.http import MediaIoBaseUpload

from . import config, db

METADATA_HEADERS = ["From", "To", "Cc", "Subject", "Date", "Message-ID", "References", "In-Reply-To"]


# ─── Utilidades ───────────────────────────────────────────────────────────────

def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _decode_text(raw: bytes, charset: Optional[str]) -> str:
    # Tenta UTF-8 estrito primeiro; se falhar, usa o charset declarado.
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode(charset or "latin-1", errors="replace")
        except LookupError:
            return raw.decode("latin-1", errors="replace")


def _headers(payload: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for h in payload.get("headers", []) or []:
        out.setdefault(h.get("name", "").lower(), h.get("value", ""))
    return out


def _charset(part: Dict[str, Any]) -> Optional[str]:
    ctype = _headers(part).get("content-type", "")
    m = re.search(r'charset="?([\w\-]+)"?', ctype, re.I)
    return m.group(1) if m else None


def _has_attachment(payload: Dict[str, Any]) -> bool:
    if payload.get("filename") and payload.get("body", {}).get("attachmentId"):
        return True
    return any(_has_attachment(p) for p in payload.get("parts", []) or [])


def protected_filter(label_ids: Iterable[str]) -> List[str]:
    return [l for l in (label_ids or []) if l and l not in config.PROTECTED_LABELS]


# ─── Leitura ──────────────────────────────────────────────────────────────────

def parse_metadata(msg: Dict[str, Any]) -> Dict[str, Any]:
    payload = msg.get("payload", {}) or {}
    h = _headers(payload)
    from_name, from_email = parseaddr(h.get("from", ""))
    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId", msg["id"]),
        "internal_date": int(msg.get("internalDate", "0")),
        "from_raw": h.get("from", ""),
        "from_name": from_name or from_email,
        "from_email": from_email.lower(),
        "to_raw": h.get("to", ""),
        "cc_raw": h.get("cc", ""),
        "subject": h.get("subject", "") or "(sem assunto)",
        "snippet": html.unescape(msg.get("snippet", "")),
        "label_ids": msg.get("labelIds", []) or [],
        "message_id_header": h.get("message-id", ""),
        "references_header": (h.get("references", "") + " " + h.get("in-reply-to", "")).strip(),
        "has_attachments": _has_attachment(payload),
    }


def get_metadata(service, message_id: str) -> Dict[str, Any]:
    return service.users().messages().get(
        userId="me", id=message_id, format="metadata", metadataHeaders=METADATA_HEADERS
    ).execute()


def get_metadata_batch(service, ids: List[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Busca metadados em lotes de 50. Retorna (mensagens, ids não encontrados)."""
    found: List[Dict[str, Any]] = []
    missing: List[str] = []

    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]

        def cb(request_id, response, exception):
            if exception is not None:
                status = getattr(getattr(exception, "resp", None), "status", None)
                if status == 404:
                    missing.append(request_id)
                else:
                    raise exception
            else:
                found.append(response)

        batch = service.new_batch_http_request(callback=cb)
        for mid in chunk:
            batch.add(
                service.users().messages().get(
                    userId="me", id=mid, format="metadata", metadataHeaders=METADATA_HEADERS
                ),
                request_id=mid,
            )
        batch.execute()
    return found, missing


def parse_body(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Extrai HTML, texto, anexos e imagens inline (cid) de uma mensagem format=full."""
    html_parts: List[str] = []
    text_parts: List[str] = []
    attachments: List[Dict[str, Any]] = []
    inline: Dict[str, str] = {}

    def walk(part: Dict[str, Any]):
        mime = (part.get("mimeType") or "").lower()
        body = part.get("body", {}) or {}
        filename = part.get("filename") or ""
        hdrs = _headers(part)
        if body.get("attachmentId"):
            cid = hdrs.get("content-id", "").strip("<>")
            info = {
                "attachment_id": body["attachmentId"],
                "filename": filename or (cid or "anexo"),
                "mime_type": mime,
                "size": body.get("size", 0),
                "content_id": cid,
            }
            if cid:
                inline[cid] = body["attachmentId"]
            if filename or not cid:
                attachments.append(info)
        elif body.get("data") and not filename:
            text = _decode_text(_b64decode(body["data"]), _charset(part))
            if mime == "text/html":
                html_parts.append(text)
            elif mime == "text/plain":
                text_parts.append(text)
        for p in part.get("parts", []) or []:
            walk(p)

    walk(msg.get("payload", {}) or {})
    return {
        "html": "\n".join(html_parts),
        "text": "\n".join(text_parts),
        "attachments": attachments,
        "inline": inline,
    }


def get_full(service, message_id: str) -> Dict[str, Any]:
    # Observação: messages.get não altera a etiqueta UNREAD.
    return service.users().messages().get(userId="me", id=message_id, format="full").execute()


def get_attachment(service, message_id: str, attachment_id: str) -> bytes:
    resp = service.users().messages().attachments().get(
        userId="me", messageId=message_id, id=attachment_id
    ).execute()
    return _b64decode(resp["data"])


# ─── Etiquetas ────────────────────────────────────────────────────────────────

def sync_labels(service, account: str) -> List[Dict[str, Any]]:
    resp = service.users().labels().list(userId="me").execute()
    labels = resp.get("labels", [])
    with db.connection() as c:
        c.execute("DELETE FROM labels WHERE account=?", (account,))
        for l in labels:
            color = l.get("color") or {}
            c.execute(
                "INSERT INTO labels (account, id, name, type, bg_color, text_color) VALUES (?,?,?,?,?,?)",
                (account, l["id"], l["name"], l.get("type", "user"),
                 color.get("backgroundColor"), color.get("textColor")),
            )
    return labels


def create_label(service, account: str, name: str) -> Dict[str, Any]:
    label = service.users().labels().create(
        userId="me",
        body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
    ).execute()
    sync_labels(service, account)
    return label


def modify_thread_labels(service, account: str, thread_id: str,
                         add: Iterable[str] = (), remove: Iterable[str] = ()) -> None:
    """Altera etiquetas da conversa inteira no Gmail (replica para a controladoria).

    Etiquetas protegidas (UNREAD, INBOX etc.) são sempre ignoradas.
    """
    add_l, rem_l = protected_filter(add), protected_filter(remove)
    if not add_l and not rem_l:
        return
    resp = service.users().threads().modify(
        userId="me", id=thread_id, body={"addLabelIds": add_l, "removeLabelIds": rem_l}
    ).execute()
    for m in resp.get("messages", []) or []:
        if "labelIds" in m:
            db.update_message_labels(account, m["id"], m["labelIds"])


def add_message_labels(service, account: str, message_id: str, add: Iterable[str]) -> None:
    add_l = protected_filter(add)
    if not add_l:
        return
    resp = service.users().messages().modify(
        userId="me", id=message_id, body={"addLabelIds": add_l, "removeLabelIds": []}
    ).execute()
    if "labelIds" in resp:
        db.update_message_labels(account, message_id, resp["labelIds"])


# ─── Remetentes e assinaturas ─────────────────────────────────────────────────

def sync_send_as(service, account: str) -> List[Dict[str, Any]]:
    """Lê endereços de envio (inclui aliases) e assinaturas cadastradas no Gmail."""
    resp = service.users().settings().sendAs().list(userId="me").execute()
    items = resp.get("sendAs", [])
    with db.connection() as c:
        for s in items:
            c.execute(
                """
                INSERT INTO send_as (account, email, display_name, api_signature, is_default)
                VALUES (?,?,?,?,?)
                ON CONFLICT(account, email) DO UPDATE SET
                    display_name=excluded.display_name,
                    api_signature=excluded.api_signature,
                    is_default=excluded.is_default
                """,
                (account, s["sendAsEmail"].lower(), s.get("displayName", ""),
                 s.get("signature", ""), 1 if s.get("isDefault") else 0),
            )
    return items


def signature_for(account: str, send_as_email: str) -> str:
    r = db.one("SELECT * FROM send_as WHERE account=? AND email=?", (account, send_as_email.lower()))
    if not r:
        return ""
    if r["use_local"] and r["local_signature"]:
        return r["local_signature"]
    return r["api_signature"] or ""


# ─── Envio ────────────────────────────────────────────────────────────────────

def html_to_text(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|tr|li|h\d)>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def _clean_addresses(value: str) -> str:
    pairs = [(n, e) for n, e in getaddresses([value or ""]) if e and "@" in e]
    return ", ".join(formataddr((n, e)) for n, e in pairs)


def build_mime(
    from_email: str,
    from_name: str,
    to: str,
    subject: str,
    html_body: str,
    cc: str = "",
    bcc: str = "",
    in_reply_to: str = "",
    references: str = "",
    attachments: Iterable[Tuple[str, str, bytes]] = (),
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((from_name or "", from_email))
    msg["To"] = _clean_addresses(to)
    if cc.strip():
        msg["Cc"] = _clean_addresses(cc)
    if bcc.strip():
        msg["Bcc"] = _clean_addresses(bcc)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    domain = from_email.split("@", 1)[-1]
    msg["Message-ID"] = make_msgid(domain=domain)
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = (references + " " + in_reply_to).strip() if in_reply_to not in references else references
    msg.set_content(html_to_text(html_body) or " ")
    msg.add_alternative(
        f'<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;font-size:14px">{html_body}</body></html>',
        subtype="html",
    )
    for filename, mime_type, data in attachments:
        maintype, _, subtype = (mime_type or mimetypes.guess_type(filename)[0]
                                or "application/octet-stream").partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream", filename=filename)
    return msg


def send_mime(service, msg: EmailMessage, thread_id: Optional[str] = None) -> Dict[str, Any]:
    # Upload por mídia suporta mensagens grandes (com anexos).
    media = MediaIoBaseUpload(io.BytesIO(msg.as_bytes()), mimetype="message/rfc822", resumable=True)
    body = {"threadId": thread_id} if thread_id else {}
    return service.users().messages().send(userId="me", body=body, media_body=media).execute()


def reply_subject(subject: str) -> str:
    return subject if re.match(r"(?i)^\s*(re|res)\s*:", subject or "") else f"Re: {subject}"


def forward_subject(subject: str) -> str:
    return subject if re.match(r"(?i)^\s*(fwd?|enc)\s*:", subject or "") else f"Enc: {subject}"


def forward_block(original: Dict[str, Any], body: Dict[str, Any]) -> str:
    """Bloco "Mensagem encaminhada" no padrão do Gmail."""
    esc = html.escape
    from datetime import datetime
    dt = datetime.fromtimestamp(original["internal_date"] / 1000).strftime("%d/%m/%Y %H:%M")
    head = (
        "<br><div>---------- Mensagem encaminhada ---------<br>"
        f"De: {esc(original.get('from_raw', ''))}<br>"
        f"Data: {esc(dt)}<br>"
        f"Assunto: {esc(original.get('subject', ''))}<br>"
        f"Para: {esc(original.get('to_raw', ''))}<br>"
    )
    if original.get("cc_raw"):
        head += f"Cc: {esc(original['cc_raw'])}<br>"
    content = body.get("html") or "<pre>" + esc(body.get("text", "")) + "</pre>"
    content = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", content)
    return head + "<br></div>" + content


def quote_block(original: Dict[str, Any], body: Dict[str, Any]) -> str:
    """Citação da mensagem original nas respostas."""
    from datetime import datetime
    dt = datetime.fromtimestamp(original["internal_date"] / 1000).strftime("%d/%m/%Y %H:%M")
    content = body.get("html") or "<pre>" + html.escape(body.get("text", "")) + "</pre>"
    content = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", content)
    return (
        f'<br><div>Em {html.escape(dt)}, {html.escape(original.get("from_raw", ""))} escreveu:</div>'
        f'<blockquote style="margin:0 0 0 .8ex;border-left:1px solid #ccc;padding-left:1ex">{content}</blockquote>'
    )
