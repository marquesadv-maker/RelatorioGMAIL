"""Gmail simulado em memória para testes (não acessa a rede)."""
import base64
import email
import itertools
from email import policy

from googleapiclient.errors import HttpError


class _Resp(dict):
    def __init__(self, status):
        super().__init__(status=str(status))
        self.status = status
        self.reason = "erro"


def _err(status):
    return HttpError(_Resp(status), b"{}")


class _Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


def b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


class FakeGmail:
    def __init__(self, me="advogado@marquesss.com.br"):
        self.me = me
        self.history_id = 100
        self.msg_store = {}
        self.label_store = {
            "INBOX": {"id": "INBOX", "name": "INBOX", "type": "system"},
            "UNREAD": {"id": "UNREAD", "name": "UNREAD", "type": "system"},
            "SENT": {"id": "SENT", "name": "SENT", "type": "system"},
            "STARRED": {"id": "STARRED", "name": "STARRED", "type": "system"},
        }
        self.hist_store = []
        self.sent_raw = []
        self.modify_calls = []
        self._ids = itertools.count(1)
        self.send_as = [{"sendAsEmail": me, "displayName": "Dr. Advogado", "isDefault": True,
                         "isPrimary": True, "signature": "<b>Dr. Advogado</b><br>OAB/SP"},
                        {"sendAsEmail": "mariaelisa@marquesss.com.br", "displayName": "Maria Elisa",
                         "signature": "Maria Elisa — Marques Advogados"}]

    # ─── Helpers de teste ───────────────────────────────────────────────
    def add_message(self, frm, subject, body="Olá", labels=("INBOX", "UNREAD"), thread_id=None,
                    date_ms=None, to=None, attachment=None):
        mid = f"m{next(self._ids)}"
        parts = [{"mimeType": "text/plain", "body": {"data": b64(body)}, "headers": []},
                 {"mimeType": "text/html", "body": {"data": b64(f"<p>{body}</p>")}, "headers": []}]
        if attachment:
            parts.append({"mimeType": "application/pdf", "filename": attachment,
                          "body": {"attachmentId": f"att-{mid}", "size": 3}, "headers": []})
        import time
        self.msg_store[mid] = {
            "id": mid, "threadId": thread_id or f"t{mid}", "labelIds": list(labels),
            "snippet": body[:50], "internalDate": str(date_ms or int(time.time() * 1000)),
            "payload": {"mimeType": "multipart/mixed", "parts": parts, "headers": [
                {"name": "From", "value": frm}, {"name": "To", "value": to or self.me},
                {"name": "Subject", "value": subject}, {"name": "Message-ID", "value": f"<{mid}@x>"}]},
        }
        self.history_id += 1
        self.hist_store.append({"id": str(self.history_id), "messagesAdded": [{"message": {"id": mid}}]})
        return mid

    # ─── API ───────────────────────────────────────────────────────────
    def users(self):
        return self

    def getProfile(self, userId):
        return _Req(lambda: {"emailAddress": self.me, "historyId": str(self.history_id)})

    def settings(self):
        return self

    def sendAs(self):
        return _SendAs(self)

    def labels(self):
        return _Labels(self)

    def history(self):
        return _History(self)

    def new_batch_http_request(self, callback):
        return _Batch(callback)

    def threads(self):
        return _Threads(self)

    def messages(self):
        return _Messages(self)


class _Batch:
    def __init__(self, cb):
        self.cb, self.items = cb, []

    def add(self, req, request_id):
        self.items.append((req, request_id))

    def execute(self):
        for req, rid in self.items:
            try:
                self.cb(rid, req.execute(), None)
            except HttpError as e:
                self.cb(rid, None, e)


class _SendAs:
    def __init__(self, g):
        self.g = g

    def list(self, userId):
        return _Req(lambda: {"sendAs": self.g.send_as})


class _Labels:
    def __init__(self, g):
        self.g = g

    def list(self, userId):
        return _Req(lambda: {"labels": list(self.g.label_store.values())})

    def create(self, userId, body):
        def f():
            lid = f"Label_{len(self.g.label_store)}"
            self.g.label_store[lid] = {"id": lid, "name": body["name"], "type": "user"}
            return self.g.label_store[lid]
        return _Req(f)


class _History:
    def __init__(self, g):
        self.g = g

    def list(self, userId, startHistoryId, historyTypes=None, pageToken=None):
        def f():
            if int(startHistoryId) < 50:
                raise _err(404)
            h = [x for x in self.g.hist_store if int(x["id"]) > int(startHistoryId)]
            return {"history": h, "historyId": str(self.g.history_id)}
        return _Req(f)


class _Messages:
    def __init__(self, g):
        self.g = g

    def list(self, userId, q=None, maxResults=100, pageToken=None, **kw):
        return _Req(lambda: {"messages": [{"id": i} for i in self.g.msg_store]})

    def get(self, userId, id, format="full", metadataHeaders=None):
        def f():
            if id not in self.g.msg_store:
                raise _err(404)
            import copy
            m = copy.deepcopy(self.g.msg_store[id])
            if format == "metadata":
                m["payload"] = {"headers": m["payload"]["headers"],
                                "parts": [{"filename": p.get("filename", ""), "body": {k: v for k, v in p["body"].items() if k != "data"}}
                                          for p in m["payload"]["parts"]]}
            return m
        return _Req(f)

    def modify(self, userId, id, body):
        def f():
            self.g.modify_calls.append(("message", id, body))
            m = self.g.msg_store[id]
            for l in body.get("addLabelIds", []):
                if l not in m["labelIds"]:
                    m["labelIds"].append(l)
            m["labelIds"] = [l for l in m["labelIds"] if l not in body.get("removeLabelIds", [])]
            return {"id": id, "labelIds": m["labelIds"]}
        return _Req(f)

    def send(self, userId, body=None, media_body=None):
        def f():
            raw = media_body.getbytes(0, media_body.size())
            self.g.sent_raw.append(raw)
            parsed = email.message_from_bytes(raw, policy=policy.default)
            mid = self.g.add_message(parsed["From"], parsed["Subject"], "enviado", labels=("SENT",),
                                     thread_id=(body or {}).get("threadId"), to=parsed["To"])
            return {"id": mid, "threadId": self.g.msg_store[mid]["threadId"]}
        return _Req(f)

    def attachments(self):
        return _Attachments()


class _Attachments:
    def get(self, userId, messageId, id):
        return _Req(lambda: {"data": b64("PDF")})


class _Threads:
    def __init__(self, g):
        self.g = g

    def modify(self, userId, id, body):
        def f():
            self.g.modify_calls.append(("thread", id, body))
            out = []
            for m in self.g.msg_store.values():
                if m["threadId"] == id:
                    for l in body.get("addLabelIds", []):
                        if l not in m["labelIds"]:
                            m["labelIds"].append(l)
                    m["labelIds"] = [l for l in m["labelIds"] if l not in body.get("removeLabelIds", [])]
                    out.append({"id": m["id"], "labelIds": m["labelIds"]})
            return {"id": id, "messages": out}
        return _Req(f)
