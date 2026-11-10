"""
Servidor local (Flask) do Gestor de E-mail.

Acessível apenas em 127.0.0.1. Todas as rotas /api exigem o token de sessão
gerado na inicialização (proteção contra requisições de outros sites).
"""
import html
import json
import re
import secrets
import sqlite3
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Flask, Response, abort, jsonify, request, send_from_directory
from googleapiclient.errors import HttpError

from . import auth, config, db, gmail_ops, ia, modelos, sync, triagem

INLINE_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}

SYSTEM_LABEL_NAMES = {
    "INBOX": "Caixa de entrada", "STARRED": "Com estrela", "IMPORTANT": "Importante",
    "SENT": "Enviados", "ALL": "Todos os e-mails",
}


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    db.backfill_tipos()
    triagem.reprocessar()
    app.config["SESSION_TOKEN"] = secrets.token_urlsafe(32)
    app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024  # anexos até ~25 MB

    allowed_hosts = {f"127.0.0.1:{config.PORT}", f"localhost:{config.PORT}"}

    @app.before_request
    def _guard():
        # Impede DNS rebinding e acesso por outros sites
        if not app.testing and request.host not in allowed_hosts:
            abort(403)
        if request.path.startswith("/api/"):
            tok = request.headers.get("X-Gestor-Token") or request.args.get("t")
            if not tok or not secrets.compare_digest(tok, app.config["SESSION_TOKEN"]):
                abort(403)

    @app.after_request
    def _headers(resp):
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    @app.errorhandler(HttpError)
    def _http_error(e):
        return jsonify({"erro": f"Gmail: {e.reason if hasattr(e, 'reason') else e}"}), 502

    @app.errorhandler(RuntimeError)
    def _runtime_error(e):
        return jsonify({"erro": str(e)}), 400

    # ─── Página ───────────────────────────────────────────────────────────

    @app.get("/")
    def index():
        nonce = secrets.token_urlsafe(16)
        with open(f"{app.static_folder}/index.html", encoding="utf-8") as f:
            page = (f.read().replace("__TOKEN__", app.config["SESSION_TOKEN"])
                    .replace("<script>", f'<script nonce="{nonce}">')
                    .replace('<script src=', f'<script nonce="{nonce}" src='))
        resp = Response(page, mimetype="text/html")
        # Scripts só com nonce: atributos on* em HTML de e-mails nunca executam
        resp.headers["Content-Security-Policy"] = (
            f"default-src 'self'; script-src 'nonce-{nonce}'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: https: http:; font-src 'self' data: https://fonts.gstatic.com; connect-src 'self'; "
            "frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'"
        )
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # ─── Contas ───────────────────────────────────────────────────────────

    @app.get("/api/accounts")
    def accounts():
        out = []
        for email in auth.list_accounts():
            st = db.account_state(email) or {}
            out.append({"email": email, "last_sync": st.get("last_sync"), "last_error": st.get("last_error")})
        return jsonify(out)

    @app.post("/api/accounts/connect")
    def connect():
        hint = (request.json or {}).get("email") or None
        email = auth.connect_account(hint)
        sync.sync_account(email)
        return jsonify({"email": email})

    @app.post("/api/accounts/<email>/disconnect")
    def disconnect(email):
        auth.disconnect_account(email)
        return jsonify({"ok": True})

    @app.post("/api/sync")
    def sync_now():
        return jsonify(sync.sync_all())

    # ─── Etiquetas ────────────────────────────────────────────────────────

    @app.get("/api/labels")
    def labels():
        account = _account_param(required=False)
        sql = "SELECT * FROM labels"
        params: List[Any] = []
        if account:
            sql += " WHERE account=?"
            params.append(account)
        out = []
        for l in db.rows(sql + " ORDER BY name COLLATE NOCASE", params):
            l["display"] = SYSTEM_LABEL_NAMES.get(l["id"], l["name"])
            out.append(l)
        return jsonify(out)

    @app.post("/api/labels")
    def new_label():
        data = request.json or {}
        account = _require_account(data.get("account"))
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"erro": "Informe o nome da etiqueta"}), 400
        label = gmail_ops.create_label(auth.get_service(account), account, name)
        return jsonify(label)

    @app.post("/api/threads/labels")
    def thread_labels():
        """Adiciona/remove etiquetas de conversas (replicado no Gmail)."""
        data = request.json or {}
        account = _require_account(data.get("account"))
        svc = auth.get_service(account)
        for tid in data.get("thread_ids", []):
            gmail_ops.modify_thread_labels(svc, account, tid, data.get("add", []), data.get("remove", []))
        return jsonify({"ok": True})

    # ─── Lista e leitura ──────────────────────────────────────────────────

    @app.get("/api/threads")
    def threads():
        account = _account_param(required=False)
        label = request.args.get("label", "INBOX")
        unread_local = request.args.get("nao_lidas") == "1"
        q = (request.args.get("q") or "").strip()
        limit = min(int(request.args.get("limit", 100)), 500)
        offset = int(request.args.get("offset", 0))

        where = ["1=1"]
        params: List[Any] = []
        if account:
            where.append("m.account=?")
            params.append(account)
        tipo = request.args.get("tipo")
        if tipo:
            where.append("m.tipo=?")
            params.append(tipo)
        label_name = request.args.get("label_nome")
        if label_name:
            # Etiqueta de usuário pelo nome (os IDs diferem entre contas)
            where.append("EXISTS (SELECT 1 FROM message_labels x JOIN labels l ON l.account=x.account "
                         "AND l.id=x.label_id WHERE x.account=m.account AND x.message_id=m.id AND l.name=?)")
            params.append(label_name)
        elif label == "ALL":
            where.append("NOT EXISTS (SELECT 1 FROM message_labels x WHERE x.account=m.account "
                         "AND x.message_id=m.id AND x.label_id='TRASH') AND (NOT EXISTS (SELECT 1 FROM message_labels xp "
                         "WHERE xp.account=m.account AND xp.message_id=m.id AND xp.label_id='SPAM') "
                         "OR COALESCE(m.triagem,'') LIKE 'resgatado%')")
        elif label == "ANUNCIOS":
            where.append("m.triagem='anuncio'")
        elif label == "INBOX":
            where.append(_caixa_sql())
        else:
            where.append("EXISTS (SELECT 1 FROM message_labels x WHERE x.account=m.account "
                         "AND x.message_id=m.id AND x.label_id=?)")
            params.append(label)
        categoria = request.args.get("categoria")
        if categoria:
            where.append(_category_sql(categoria))
        grupo = request.args.get("grupo")
        if grupo in GRUPOS_NOTIF:
            where.append(GRUPOS_NOTIF[grupo])
        if q:
            for term in q.split():
                like = f"%{term}%"
                where.append("(m.subject LIKE ? OR m.from_raw LIKE ? OR m.to_raw LIKE ? OR m.snippet LIKE ?)")
                params.extend([like] * 4)

        read = _read_sql("t.account", "t.thread_id")
        ordem = "t.last_date DESC"
        if request.args.get("prioridade") == "1":
            # Prioridade: intimação/citação não aberta > outra notificação não aberta > não lidas > lidas; depois, mais recentes
            trib = ("EXISTS (SELECT 1 FROM messages mp WHERE mp.account=t.account AND mp.thread_id=t.thread_id "
                    "AND mp.tipo='TRIBUNAL'{})")
            ordem = (f"CASE WHEN {read} THEN 3 WHEN {trib.format(' AND mp.subtipo IN (' + chr(39) + 'Intimação' + chr(39) + ',' + chr(39) + 'Citação' + chr(39) + ')')} "
                     f"THEN 0 WHEN {trib.format('')} THEN 1 ELSE 2 END, t.last_date DESC")
        base = f"""
            WITH matched AS (
                SELECT m.account, m.thread_id, MAX(m.internal_date) AS last_date
                FROM messages m WHERE {' AND '.join(where)}
                GROUP BY m.account, m.thread_id
            )"""
        conds = []
        if unread_local:
            conds.append(f"NOT {read}")
        # Destaques = janela de período (padrão: hoje); "anteriores" = antes do início da janela
        destaque = request.args.get("destaque")
        if destaque in ("1", "0"):
            hoje_ms = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
            desde = _int_arg("desde", hoje_ms)
            ate = _int_arg("ate", None)
            if destaque == "1":
                conds.append(f"t.last_date >= {desde}")
                if ate is not None:
                    conds.append(f"t.last_date <= {ate}")
            else:
                conds.append(f"t.last_date < {desde}")
        flt = ("WHERE " + " AND ".join(conds)) if conds else ""
        total = db.one(f"{base} SELECT COUNT(*) AS n FROM matched t {flt}", params)["n"]
        sql = f"""{base}
            SELECT t.account, t.thread_id, t.last_date,
                   (SELECT COUNT(*) FROM messages c WHERE c.account=t.account AND c.thread_id=t.thread_id) AS count,
                   {read} AS read_local
            FROM matched t {flt}
            ORDER BY {ordem} LIMIT ? OFFSET ?
        """
        result = [_thread_summary(t) for t in db.rows(sql, params + [limit, offset])]
        resp = jsonify(result)
        resp.headers["X-Total-Count"] = str(total)
        return resp

    @app.get("/api/threads/<account>/<thread_id>")
    def thread(account, thread_id):
        account = _require_account(account)
        msgs = [db.decode_message(r) for r in db.rows(
            "SELECT * FROM messages WHERE account=? AND thread_id=? ORDER BY internal_date", (account, thread_id))]
        if not msgs:
            abort(404)
        svc = None
        for m in msgs:
            if m["body"] is None:
                svc = svc or auth.get_service(account)
                full = gmail_ops.get_full(svc, m["id"])
                m["body"] = gmail_ops.parse_body(full)
                db.save_body(account, m["id"], m["body"])
            m["unread_gmail"] = "UNREAD" in m["label_ids"]
        # Leitura apenas local: não altera UNREAD no Gmail.
        db.execute("INSERT OR IGNORE INTO local_read (account, thread_id) VALUES (?,?)", (account, thread_id))
        labels = sorted({l for m in msgs for l in m["label_ids"]})
        return jsonify({"account": account, "thread_id": thread_id, "messages": msgs, "label_ids": labels,
                        "sem_envio": bool(_sem_envio(account, thread_id))})

    @app.post("/api/threads/<account>/<thread_id>/lida")
    def mark_read_local(account, thread_id):
        # Somente no MarquesPro; o Gmail não é alterado.
        db.execute("INSERT OR IGNORE INTO local_read (account, thread_id) VALUES (?,?)", (account, thread_id))
        return jsonify({"ok": True})

    @app.post("/api/threads/<account>/<thread_id>/nao-spam")
    def nao_spam(account, thread_id):
        """Ação explícita do usuário: devolve a conversa à caixa de entrada também no Gmail."""
        account = _require_account(account)
        gmail_ops.mover_para_caixa(auth.get_service(account), account, thread_id)
        for r in db.rows("SELECT * FROM messages WHERE account=? AND thread_id=?", (account, thread_id)):
            m = db.decode_message(r); m["thread_id"] = thread_id
            triagem.aplicar(account, m)
        return jsonify({"ok": True})

    @app.post("/api/threads/<account>/<thread_id>/triagem")
    def triagem_manual(account, thread_id):
        """Corrige a triagem local: 'inbox' (não é anúncio) ou 'anuncio'. O Gmail não é alterado."""
        valor = (request.json or {}).get("valor")
        if valor not in ("inbox", "anuncio"):
            return jsonify({"erro": "Valor inválido"}), 400
        triagem.alterar_conversa(_require_account(account), thread_id, valor)
        return jsonify({"ok": True})

    @app.post("/api/threads/<account>/<thread_id>/nao-lida")
    def mark_unread_local(account, thread_id):
        db.execute("DELETE FROM local_read WHERE account=? AND thread_id=?", (account, thread_id))
        return jsonify({"ok": True})

    @app.get("/api/attachment/<account>/<message_id>/<attachment_id>")
    def attachment(account, message_id, attachment_id):
        account = _require_account(account)
        data = gmail_ops.get_attachment(auth.get_service(account), message_id, attachment_id)
        filename = request.args.get("nome", "anexo")
        mime = request.args.get("tipo", "application/octet-stream")
        # Exibição inline só para imagens raster (SVG pode conter scripts)
        inline = request.args.get("inline") == "1" and mime in INLINE_IMAGE_TYPES
        disp = "inline" if inline else "attachment"
        safe = re.sub(r'[\r\n"\\]', "_", filename)
        return Response(data, mimetype=mime if inline else "application/octet-stream",
                        headers={"Content-Disposition": f'{disp}; filename="{safe}"',
                                 "Content-Security-Policy": "default-src 'none'; sandbox"})

    @app.get("/api/search")
    def search_gmail():
        """Busca diretamente no Gmail (aceita operadores do Gmail) e traz ao cache."""
        account = _require_account(request.args.get("account"))
        q = request.args.get("q", "")
        svc = auth.get_service(account)
        resp = svc.users().messages().list(userId="me", q=q, maxResults=100).execute()
        ids = [m["id"] for m in resp.get("messages", [])]
        found, _ = gmail_ops.get_metadata_batch(svc, [i for i in ids if not db.message_exists(account, i)])
        for raw in found:
            db.upsert_message(account, gmail_ops.parse_metadata(raw))
        tids = []
        seen = set()
        for i in ids:
            r = db.one("SELECT thread_id FROM messages WHERE account=? AND id=?", (account, i))
            if r and r["thread_id"] not in seen:
                seen.add(r["thread_id"])
                tids.append(r["thread_id"])
        out = []
        for tid in tids:
            t = db.one(
                "SELECT account, thread_id, MAX(internal_date) AS last_date, COUNT(*) AS count "
                "FROM messages WHERE account=? AND thread_id=? GROUP BY account, thread_id", (account, tid))
            t["read_local"] = db.one(
                f"SELECT {_read_sql('t.account', 't.thread_id')} AS r FROM (SELECT ? AS account, ? AS thread_id) t",
                (account, tid))["r"]
            out.append(_thread_summary(t))
        return jsonify(out)

    # ─── Contador e notificações ──────────────────────────────────────────

    @app.get("/api/status")
    def status():
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        ms = int(midnight.timestamp() * 1000)
        account = _account_param(required=False)
        acc_sql, acc_params = ("AND m.account=?", [account]) if account else ("", [])
        today = db.one(
            f"""SELECT COUNT(*) AS n FROM messages m WHERE m.internal_date>=? {acc_sql}
                AND {_caixa_sql()}""",
            [ms] + acc_params)["n"]
        def unread_threads(extra: str, extra_params=()) -> int:
            return db.one(
                f"""SELECT COUNT(*) AS n FROM (SELECT DISTINCT m.account, m.thread_id FROM messages m
                    WHERE 1=1 {acc_sql} AND {extra}) t WHERE NOT {_read_sql('t.account', 't.thread_id')}""",
                list(acc_params) + list(extra_params))["n"]

        inbox_sql = _caixa_sql()
        unread_local = unread_threads(inbox_sql)
        por_categoria = {c: unread_threads(f"{inbox_sql} AND {_category_sql(c)}")
                         for c in ("principal", "promocoes", "social", "atualizacoes", "foruns")}
        por_etiqueta = db.rows(
            f"""SELECT name, COUNT(*) AS n FROM (
                    SELECT DISTINCT m.account, m.thread_id, l.name FROM messages m
                    JOIN message_labels x ON x.account=m.account AND x.message_id=m.id
                    JOIN labels l ON l.account=x.account AND l.id=x.label_id AND l.type='user'
                    WHERE 1=1 {acc_sql}) t
                WHERE NOT {_read_sql('t.account', 't.thread_id')} GROUP BY name""", acc_params)
        by_label = db.rows(
            f"""SELECT x.label_id, l.name, COUNT(*) AS n FROM messages m
                JOIN message_labels x ON x.account=m.account AND x.message_id=m.id
                JOIN labels l ON l.account=m.account AND l.id=x.label_id AND l.type='user'
                WHERE m.internal_date>=? {acc_sql}
                GROUP BY x.label_id, l.name ORDER BY n DESC""",
            [ms] + acc_params)
        since = int(request.args.get("desde", 0))
        nacc_sql = "AND account=?" if account else ""
        new = db.rows(
            f"SELECT * FROM notifications WHERE id>? {nacc_sql} ORDER BY id DESC LIMIT 20",
            [since] + acc_params)
        last = db.one("SELECT MAX(id) AS id FROM notifications")["id"] or 0
        notif_today = db.one(
            f"SELECT COUNT(*) AS n FROM notifications WHERE created_at>=? {nacc_sql}",
            [midnight.strftime("%Y-%m-%d %H:%M:%S")] + acc_params)["n"]
        notif_where = f"""FROM messages m WHERE m.tipo='TRIBUNAL' {acc_sql} AND {_FORA_SPAM_SQL}"""
        notif_hoje = db.one(f"SELECT COUNT(*) AS n {notif_where} AND m.internal_date>=?", acc_params + [ms])["n"]
        notif_pend = db.one(
            f"""SELECT COUNT(*) AS n FROM (SELECT DISTINCT m.account, m.thread_id {notif_where}) t
                WHERE NOT {_read_sql('t.account', 't.thread_id')}""", acc_params)["n"]
        grupos = {}
        for g, cond in GRUPOS_NOTIF.items():
            grupos[g] = db.one(
                f"""SELECT COUNT(*) AS n FROM (SELECT DISTINCT m.account, m.thread_id FROM messages m
                    WHERE {cond} {acc_sql} AND {_FORA_SPAM_SQL}) t
                    WHERE NOT {_read_sql('t.account', 't.thread_id')}""", acc_params)["n"]
        notif_tipos = db.rows(
            f"SELECT COALESCE(m.subtipo,'Outras') AS nome, COUNT(*) AS n {notif_where} AND m.internal_date>=? "
            "GROUP BY nome ORDER BY n DESC", acc_params + [ms])
        return jsonify({
            "notificacoes": {"hoje": notif_hoje, "pendentes": notif_pend, "por_tipo": notif_tipos,
                             "pendentes_por_grupo": grupos},
            "recebidas_hoje": today,
            "notificacoes_hoje": notif_today,
            "nao_lidas_local": unread_local,
            "nao_lidas_categoria": por_categoria,
            "nao_lidas_etiqueta": {r["name"]: r["n"] for r in por_etiqueta},
            "hoje_por_etiqueta": by_label,
            "novas": new,
            "ultimo_id": last,
            "contas": db.rows("SELECT email, last_sync, last_error FROM accounts"),
        })

    # ─── Remetentes, assinaturas e contatos ───────────────────────────────

    @app.get("/api/send-as")
    def send_as():
        out = []
        for r in db.rows("SELECT * FROM send_as ORDER BY account, is_default DESC, email"):
            if r["account"] not in auth.list_accounts():
                continue
            r["signature"] = gmail_ops.signature_for(r["account"], r["email"])
            out.append(r)
        return jsonify(out)

    @app.post("/api/send-as/refresh")
    def send_as_refresh():
        for a in auth.list_accounts():
            gmail_ops.sync_send_as(auth.get_service(a), a)
        return send_as()

    @app.post("/api/send-as/signature")
    def save_signature():
        data = request.json or {}
        account = _require_account(data.get("account"))
        db.execute(
            "UPDATE send_as SET local_signature=?, use_local=? WHERE account=? AND email=?",
            (data.get("local_signature", ""), 1 if data.get("use_local") else 0,
             account, (data.get("email") or "").lower()))
        return jsonify({"ok": True})

    @app.get("/api/contacts")
    def contacts():
        q = (request.args.get("q") or "").strip().lower()
        if len(q) < 2:
            return jsonify([])
        like = f"%{q}%"
        cands = db.rows(
            "SELECT from_raw AS v FROM messages WHERE lower(from_raw) LIKE ? "
            "UNION ALL SELECT to_raw FROM messages WHERE lower(to_raw) LIKE ? "
            "UNION ALL SELECT cc_raw FROM messages WHERE lower(cc_raw) LIKE ? LIMIT 2000",
            (like, like, like))
        from email.utils import getaddresses
        counts: Dict[str, Dict[str, Any]] = {}
        for c in cands:
            for name, email in getaddresses([c["v"] or ""]):
                email = email.lower()
                if "@" not in email or (q not in email and q not in name.lower()):
                    continue
                e = counts.setdefault(email, {"email": email, "name": "", "n": 0})
                e["n"] += 1
                if name and not e["name"]:
                    e["name"] = name
        achados = sorted(counts.values(), key=lambda x: -x["n"])[:8]
        grupos = [{"grupo": True, "name": f"{e['nome']} › {sg['nome']}", "email": f"{len((sg['para'] + ',' + sg['cc'] + ',' + sg['cco']).strip(',').split(','))} e-mail(s) padrão",
                   "para": sg["para"], "cc": sg["cc"], "cco": sg["cco"]}
                  for e in _grupos() for sg in e["subgrupos"]
                  if _sem_acento(q) in _sem_acento(f"{e['nome']} {sg['nome']}")][:5]
        return jsonify(grupos + achados)

    # ─── Envio, resposta e encaminhamento ─────────────────────────────────

    @app.post("/api/send")
    def send():
        f = request.form
        account = _require_account(f.get("account"))
        from_email = (f.get("from_email") or account).lower()
        sa = db.one("SELECT * FROM send_as WHERE account=? AND email=?", (account, from_email))
        if not sa and from_email != account:
            return jsonify({"erro": "Remetente não autorizado para esta conta"}), 400
        from_name = (sa or {}).get("display_name") or ""
        mode = f.get("mode", "novo")  # novo | responder | responder_todos | encaminhar
        ref_id = f.get("ref_message_id")
        thread_id = None
        in_reply_to = references = ""
        attachments = [(fs.filename, fs.mimetype, fs.read()) for fs in request.files.getlist("anexos") if fs.filename]

        svc = auth.get_service(account)
        if ref_id:
            ref = db.one("SELECT * FROM messages WHERE account=? AND id=?", (account, ref_id))
            if not ref:
                return jsonify({"erro": "Mensagem original não encontrada"}), 404
            if mode in ("responder", "responder_todos"):
                thread_id = ref["thread_id"]
                in_reply_to = ref["message_id_header"] or ""
                references = ref["references_header"] or ""
            if mode == "encaminhar" and f.get("incluir_anexos", "1") == "1":
                body = db.decode_message(ref)["body"] or gmail_ops.parse_body(gmail_ops.get_full(svc, ref_id))
                for a in body.get("attachments", []):
                    data = gmail_ops.get_attachment(svc, ref_id, a["attachment_id"])
                    attachments.append((a["filename"], a["mime_type"], data))

        to = f.get("to", "")
        if not (to.strip() or f.get("cc", "").strip() or f.get("bcc", "").strip()):
            return jsonify({"erro": "Informe ao menos um destinatário"}), 400
        msg = gmail_ops.build_mime(
            from_email=from_email, from_name=from_name, to=to, cc=f.get("cc", ""), bcc=f.get("bcc", ""),
            subject=f.get("subject", ""), html_body=f.get("html", ""),
            in_reply_to=in_reply_to, references=references, attachments=attachments,
        )
        sent = gmail_ops.send_mime(svc, msg, thread_id)

        # Grava no cache e aplica regras "enviado por" + etiquetas escolhidas
        raw = gmail_ops.get_metadata(svc, sent["id"])
        m = gmail_ops.parse_metadata(raw)
        db.upsert_message(account, m)
        db.execute("INSERT OR IGNORE INTO local_read (account, thread_id) VALUES (?,?)", (account, m["thread_id"]))
        sync.apply_rules(svc, account, [m])
        if ref_id:
            ref_row = db.one("SELECT thread_id FROM messages WHERE account=? AND id=?", (account, ref_id))
            if ref_row:
                db.execute("INSERT OR IGNORE INTO envios (account, thread_id, message_id) VALUES (?,?,?)",
                           (account, ref_row["thread_id"], sent["id"]))
        extra = json.loads(f.get("labels", "[]") or "[]")
        if extra:
            gmail_ops.add_message_labels(svc, account, sent["id"], extra)
        return jsonify({"id": sent["id"], "thread_id": sent.get("threadId")})

    @app.get("/api/compose-context/<account>/<message_id>")
    def compose_context(account, message_id):
        """Dados pré-preenchidos para responder/encaminhar."""
        account = _require_account(account)
        mode = request.args.get("mode", "responder")
        r = db.one("SELECT * FROM messages WHERE account=? AND id=?", (account, message_id))
        if not r:
            abort(404)
        m = db.decode_message(r)
        if m["body"] is None:
            m["body"] = gmail_ops.parse_body(gmail_ops.get_full(auth.get_service(account), message_id))
            db.save_body(account, message_id, m["body"])
        me = {e["email"] for e in db.rows("SELECT email FROM send_as WHERE account=?", (account,))} | {account}
        from email.utils import getaddresses, formataddr
        is_sent = "SENT" in m["label_ids"]
        if mode == "encaminhar":
            to, cc = "", ""
            subject = gmail_ops.forward_subject(m["subject"])
            quoted = gmail_ops.forward_block(m, m["body"])
        else:
            to = m["to_raw"] if is_sent else m["from_raw"]
            cc = ""
            if mode == "responder_todos":
                others = [(n, e) for n, e in getaddresses([m["to_raw"], m["cc_raw"]])
                          if e and e.lower() not in me and e.lower() not in to.lower()]
                cc = ", ".join(formataddr(p) for p in others)
            subject = gmail_ops.reply_subject(m["subject"])
            quoted = gmail_ops.quote_block(m, m["body"])
        # Remetente sugerido: o endereço da conta para o qual a mensagem foi enviada
        rcpts = {e.lower() for _, e in getaddresses([m["to_raw"], m["cc_raw"]])}
        suggested = next((e for e in me if e in rcpts), None) or (m["from_email"] if is_sent else None)
        return jsonify({
            "to": to, "cc": cc, "subject": subject, "quoted": quoted,
            "from_email": suggested, "attachments": m["body"].get("attachments", []),
            "label_ids": gmail_ops.protected_filter(m["label_ids"]),
        })

    # ─── Modelos de e-mail do escritório e preenchimento por IA ───────────

    @app.get("/api/modelos")
    def modelos_lista():
        return jsonify(modelos.carregar())

    @app.get("/api/ia/status")
    def ia_status():
        return jsonify(ia.status())

    @app.post("/api/ia/config")
    def ia_config():
        ia.salvar_chave((request.json or {}).get("api_key", ""))
        return jsonify(ia.status())

    @app.post("/api/ia/preencher")
    def ia_preencher():
        """Envia o documento/e-mail para a IA e devolve o e-mail preenchido (somente a pedido do usuário)."""
        f = request.form
        arquivos = [(fs.filename, fs.mimetype, fs.read()) for fs in request.files.getlist("arquivos") if fs.filename]
        email_ref = None
        account, ref_id = (f.get("account") or "").lower(), f.get("ref_message_id")
        if ref_id and f.get("usar_email", "1") == "1":
            account = _require_account(account)
            r = db.one("SELECT * FROM messages WHERE account=? AND id=?", (account, ref_id))
            if not r:
                return jsonify({"erro": "Mensagem de referência não encontrada"}), 404
            svc = auth.get_service(account)
            m = db.decode_message(r)
            if m["body"] is None:
                m["body"] = gmail_ops.parse_body(gmail_ops.get_full(svc, ref_id))
                db.save_body(account, ref_id, m["body"])
            body = m["body"]
            texto = body.get("text") or gmail_ops.html_to_text(body.get("html", ""))
            email_ref = {"de": m["from_raw"], "para": m["to_raw"], "assunto": m["subject"], "texto": texto}
            if f.get("usar_anexos", "1") == "1":
                for a in body.get("attachments", []):
                    if a["mime_type"] in ia.TIPOS_ACEITOS and a.get("size", 0) <= 15 * 1024 * 1024:
                        arquivos.append((a["filename"], a["mime_type"], gmail_ops.get_attachment(svc, ref_id, a["attachment_id"])))
        if not arquivos and not email_ref and not (f.get("instrucoes") or "").strip():
            return jsonify({"erro": "Anexe um documento (PDF/imagem), use o e-mail aberto ou escreva as informações."}), 400
        try:
            out = ia.preencher_auto(f.get("codigo", ""), f.get("instrucoes", ""), email_ref, arquivos,
                                    aceitar_visao=f.get("aceitar_visao") == "1")
        except ValueError as e:
            return jsonify({"erro": str(e)}), 400
        except RuntimeError as e:
            return jsonify({"erro": str(e)}), 400
        except Exception as e:  # erros da API (chave inválida, limite etc.)
            return jsonify({"erro": f"Falha ao consultar a IA: {getattr(e, 'message', None) or e}"}), 502
        return jsonify(out)

    # ─── Grupos de empresas e subgrupos de destinatários ──────────────────

    @app.get("/api/grupos")
    def grupos_lista():
        return jsonify(_grupos())

    @app.post("/api/grupos")
    def grupos_salvar():
        d = request.json or {}
        nome = (d.get("nome") or "").strip()
        if not nome:
            return jsonify({"erro": "Informe o nome da empresa/grupo"}), 400
        try:
            if d.get("id"):
                db.execute("UPDATE grupos_empresas SET nome=?, observacao=? WHERE id=?",
                           (nome, (d.get("observacao") or "").strip(), d["id"]))
                gid = d["id"]
            else:
                gid = db.execute("INSERT INTO grupos_empresas (nome, observacao) VALUES (?,?)",
                                 (nome, (d.get("observacao") or "").strip()))
        except sqlite3.IntegrityError:
            return jsonify({"erro": "Já existe uma empresa/grupo com esse nome"}), 400
        return jsonify({"id": gid})

    @app.delete("/api/grupos/<int:gid>")
    def grupos_excluir(gid):
        db.execute("DELETE FROM subgrupos WHERE empresa_id=?", (gid,))
        db.execute("DELETE FROM grupos_empresas WHERE id=?", (gid,))
        return jsonify({"ok": True})

    @app.post("/api/grupos/<int:gid>/subgrupos")
    def subgrupos_salvar(gid):
        d = request.json or {}
        nome = (d.get("nome") or "").strip()
        if not nome:
            return jsonify({"erro": "Informe o nome do subgrupo (ex.: RH, Jurídico, Diretoria)"}), 400
        try:
            para, cc, cco = (_emails(d.get(k)) for k in ("para", "cc", "cco"))
        except ValueError as e:
            return jsonify({"erro": str(e)}), 400
        if not (para or cc or cco):
            return jsonify({"erro": "Informe ao menos um e-mail padrão"}), 400
        try:
            if d.get("id"):
                db.execute("UPDATE subgrupos SET nome=?, para=?, cc=?, cco=? WHERE id=? AND empresa_id=?",
                           (nome, para, cc, cco, d["id"], gid))
                sid = d["id"]
            else:
                sid = db.execute("INSERT INTO subgrupos (empresa_id, nome, para, cc, cco) VALUES (?,?,?,?,?)",
                                 (gid, nome, para, cc, cco))
        except sqlite3.IntegrityError:
            return jsonify({"erro": "Já existe um subgrupo com esse nome nesta empresa"}), 400
        return jsonify({"id": sid})

    @app.delete("/api/subgrupos/<int:sid>")
    def subgrupos_excluir(sid):
        db.execute("DELETE FROM subgrupos WHERE id=?", (sid,))
        return jsonify({"ok": True})

    # ─── Preferências ─────────────────────────────────────────────────────

    @app.get("/api/settings")
    def settings_get():
        return jsonify(db.all_settings())

    @app.post("/api/settings")
    def settings_set():
        for k, v in (request.json or {}).items():
            try:
                db.set_setting(k, "1" if v in (True, "1", 1) else "0")
            except ValueError:
                return jsonify({"erro": f"Preferência desconhecida: {k}"}), 400
        return jsonify(db.all_settings())

    # ─── Regras de etiquetas automáticas ──────────────────────────────────

    @app.get("/api/rules")
    def rules():
        out = []
        for r in db.rows("SELECT * FROM rules ORDER BY account, id"):
            r["label_ids"] = json.loads(r["label_ids"])
            out.append(r)
        return jsonify(out)

    @app.post("/api/rules")
    def new_rule():
        data = request.json or {}
        account = _require_account(data.get("account"))
        direction = data.get("direction")
        pattern = (data.get("pattern") or "").strip()
        labels = gmail_ops.protected_filter(data.get("label_ids") or [])
        if direction not in ("recebido", "enviado") or not pattern or not labels:
            return jsonify({"erro": "Preencha direção, remetente e ao menos uma etiqueta"}), 400
        rid = db.execute("INSERT INTO rules (account, direction, pattern, label_ids) VALUES (?,?,?,?)",
                         (account, direction, pattern, json.dumps(labels)))
        n = sync.apply_rule_to_existing(account, rid) if data.get("aplicar_existentes") else 0
        return jsonify({"id": rid, "aplicadas": n})

    @app.post("/api/rules/<int:rid>/aplicar")
    def apply_rule(rid):
        r = db.one("SELECT * FROM rules WHERE id=?", (rid,))
        if not r:
            abort(404)
        return jsonify({"aplicadas": sync.apply_rule_to_existing(r["account"], rid)})

    @app.post("/api/rules/<int:rid>/ativo")
    def toggle_rule(rid):
        db.execute("UPDATE rules SET active=? WHERE id=?", (1 if (request.json or {}).get("active") else 0, rid))
        return jsonify({"ok": True})

    @app.delete("/api/rules/<int:rid>")
    def delete_rule(rid):
        db.execute("DELETE FROM rules WHERE id=?", (rid,))
        db.execute("DELETE FROM rule_applied WHERE rule_id=?", (rid,))
        return jsonify({"ok": True})

    return app


# ─── Auxiliares ───────────────────────────────────────────────────────────────

def _account_param(required: bool = True):
    acc = (request.args.get("account") or "").lower() or None
    if acc:
        return _require_account(acc)
    if required:
        abort(400)
    return None


def _require_account(acc) -> str:
    acc = (acc or "").lower()
    if acc not in auth.list_accounts():
        raise RuntimeError("Conta não conectada")
    return acc


# Destaques: intimações, citações e demais notificações judiciais
GRUPOS_NOTIF = {
    "intimacoes": "m.tipo='TRIBUNAL' AND m.subtipo='Intimação'",
    "citacoes": "m.tipo='TRIBUNAL' AND m.subtipo='Citação'",
    "notificacoes": "m.tipo='TRIBUNAL' AND COALESCE(m.subtipo,'') NOT IN ('Intimação','Citação')",
}

def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFD", t.lower()).encode("ascii", "ignore").decode()


_EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")


def _emails(valor) -> str:
    """Normaliza uma lista de e-mails (vírgula, ponto e vírgula ou linha) e rejeita endereços inválidos."""
    itens = [x.strip().lower() for x in re.split(r"[,;\n]+", valor or "") if x.strip()]
    for x in itens:
        if not _EMAIL_RE.match(x):
            raise ValueError(f"E-mail inválido: {x}")
    return ", ".join(dict.fromkeys(itens))


def _grupos() -> List[Dict[str, Any]]:
    out = []
    for e in db.rows("SELECT * FROM grupos_empresas ORDER BY nome COLLATE NOCASE"):
        e["subgrupos"] = db.rows("SELECT * FROM subgrupos WHERE empresa_id=? ORDER BY nome COLLATE NOCASE", (e["id"],))
        out.append(e)
    return out


_CNJ = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")


def _sem_envio(account: str, thread_id: str) -> Optional[bool]:
    """Notificação judicial sem nenhum e-mail enviado sobre ela?

    None = a conversa não é uma notificação. True = nenhum e-mail enviado (mostra alerta).
    Conta como enviado: resposta na própria conversa; envio feito pela ferramenta a partir dela;
    ou e-mail enviado depois (pelo Gmail ou pela ferramenta) com o mesmo assunto ou nº de processo.
    """
    ms = db.rows("SELECT subject, snippet, internal_date, tipo, label_ids FROM messages "
                 "WHERE account=? AND thread_id=? ORDER BY internal_date", (account, thread_id))
    if not any(m["tipo"] == "TRIBUNAL" for m in ms):
        return None
    if any("SENT" in json.loads(m["label_ids"]) for m in ms):
        return False
    if db.one("SELECT 1 AS x FROM envios WHERE account=? AND thread_id=? LIMIT 1", (account, thread_id)):
        return False
    texto = " ".join(f"{m['subject'] or ''} {m['snippet'] or ''}" for m in ms)
    chaves = []
    proc = _CNJ.search(texto)
    if proc:
        chaves.append(proc.group(0).lower())
    nucleo = re.sub(r"^(?:(?:re|res|enc|fwd?)\s*:\s*)+", "", (ms[0]["subject"] or "").strip(), flags=re.I).lower()
    if len(nucleo) >= 12:
        chaves.append(nucleo)
    if not chaves:
        return True
    cond = " OR ".join("instr(lower(x.subject || ' ' || x.snippet), ?) > 0" for _ in chaves)
    achou = db.one(
        "SELECT 1 AS x FROM messages x JOIN message_labels l ON l.account=x.account AND l.message_id=x.id AND l.label_id='SENT' "
        f"WHERE x.account=? AND x.internal_date>=? AND ({cond}) LIMIT 1",
        [account, ms[0]["internal_date"]] + chaves)
    return achou is None


def _int_arg(nome: str, padrao):
    try:
        return int(request.args.get(nome))
    except (TypeError, ValueError):
        return padrao


def _sem_ads_sql() -> str:
    """Exclui anúncios quando a preferência "ocultar anúncios" está ativa."""
    return "COALESCE(m.triagem,'')<>'anuncio'" if db.get_setting("ocultar_anuncios") == "1" else "1=1"


def _caixa_sql() -> str:
    """Caixa de entrada: INBOX (sem anúncios) + mensagens resgatadas do spam."""
    return ("((EXISTS (SELECT 1 FROM message_labels xi WHERE xi.account=m.account AND xi.message_id=m.id "
            f"AND xi.label_id='INBOX') AND {_sem_ads_sql()}) OR COALESCE(m.triagem,'') LIKE 'resgatado%')")


# Fora da lixeira e do spam, exceto o que foi resgatado
_FORA_SPAM_SQL = ("NOT EXISTS (SELECT 1 FROM message_labels xs WHERE xs.account=m.account AND xs.message_id=m.id "
                  "AND xs.label_id IN ('SENT','TRASH')) AND (NOT EXISTS (SELECT 1 FROM message_labels xp "
                  "WHERE xp.account=m.account AND xp.message_id=m.id AND xp.label_id='SPAM') "
                  "OR COALESCE(m.triagem,'') LIKE 'resgatado%')")

CATEGORY_LABELS = {"promocoes": "CATEGORY_PROMOTIONS", "social": "CATEGORY_SOCIAL",
                   "atualizacoes": "CATEGORY_UPDATES", "foruns": "CATEGORY_FORUMS"}


def _category_sql(categoria: str) -> str:
    """Abas da caixa de entrada como no Gmail (Principal, Promoções, Social...)."""
    if categoria in CATEGORY_LABELS:
        return ("EXISTS (SELECT 1 FROM message_labels xc WHERE xc.account=m.account AND xc.message_id=m.id "
                f"AND xc.label_id='{CATEGORY_LABELS[categoria]}')")
    others = ",".join(f"'{v}'" for v in CATEGORY_LABELS.values())
    return ("NOT EXISTS (SELECT 1 FROM message_labels xc WHERE xc.account=m.account AND xc.message_id=m.id "
            f"AND xc.label_id IN ({others}))")


def _read_sql(acc: str, tid: str) -> str:
    """Expressão SQL: a conversa conta como lida no MarquesPro?

    Lida = aberta no MarquesPro; ou, se a preferência estiver ativa,
    nenhuma mensagem da conversa está marcada como não lida no Gmail.
    """
    gmail_conta = 1 if db.get_setting("lida_no_gmail_conta_como_lida") == "1" else 0
    local = f"EXISTS (SELECT 1 FROM local_read lr WHERE lr.account={acc} AND lr.thread_id={tid})"
    if not gmail_conta:
        return f"({local})"
    gm = ("NOT EXISTS (SELECT 1 FROM messages mu JOIN message_labels xu ON xu.account=mu.account "
          f"AND xu.message_id=mu.id AND xu.label_id='UNREAD' WHERE mu.account={acc} AND mu.thread_id={tid})")
    return f"({local} OR {gm})"


def _thread_summary(t: Dict[str, Any]) -> Dict[str, Any]:
    msgs = db.rows(
        "SELECT id, from_name, from_email, subject, snippet, label_ids, internal_date, has_attachments, tipo, subtipo, triagem, body_json "
        "FROM messages WHERE account=? AND thread_id=? ORDER BY internal_date",
        (t["account"], t["thread_id"]))
    last = msgs[-1]
    labels = sorted({l for m in msgs for l in json.loads(m["label_ids"])})
    senders: List[str] = []
    for m in msgs:
        n = (m["from_name"] or m["from_email"] or "").split(" ")[0] if len(msgs) > 1 else (m["from_name"] or m["from_email"])
        if "SENT" in json.loads(m["label_ids"]):
            n = "eu"
        if n not in senders:
            senders.append(n)
    return {
        "account": t["account"],
        "thread_id": t["thread_id"],
        "last_date": t["last_date"],
        "count": t["count"],
        "read_local": bool(t["read_local"]),
        "unread_gmail": "UNREAD" in labels,
        "subject": msgs[0]["subject"],
        "snippet": last["snippet"],
        "senders": ", ".join(senders[-3:]),
        "label_ids": labels,
        "has_attachments": any(m["has_attachments"] for m in msgs),
        "last_message_id": last["id"],
        "notificacao": next((m["subtipo"] or "Outras" for m in msgs if m["tipo"] == "TRIBUNAL"), None),
        "important": "IMPORTANT" in labels,
        "sem_envio": bool(_sem_envio(t["account"], t["thread_id"])),
        "resgatado": next((m["triagem"].split(":", 1)[1] for m in msgs
                           if (m.get("triagem") or "").startswith("resgatado") and "SPAM" in json.loads(m["label_ids"])), None),
        "anuncio": any(m.get("triagem") == "anuncio" for m in msgs),
        "anexos": _attachment_names(msgs),
    }


def _attachment_names(msgs: List[Dict[str, Any]]) -> List[str]:
    """Nomes de anexos já conhecidos (corpo em cache), para os chips sob a linha, como no Gmail."""
    names: List[str] = []
    for m in msgs:
        if m.get("body_json"):
            for a in json.loads(m["body_json"]).get("attachments", []):
                if a.get("filename") and a["filename"] not in names:
                    names.append(a["filename"])
    return names[:3]
