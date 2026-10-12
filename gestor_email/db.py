"""
Cache local (SQLite) das mensagens, etiquetas, regras e estado de leitura.

O estado "lido" do Gestor é exclusivamente local (tabela local_read):
abrir uma mensagem aqui não altera a etiqueta UNREAD no Gmail.
"""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional

from . import classify, config

_init_lock = threading.Lock()
_initialized_for: Optional[str] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    email        TEXT PRIMARY KEY,
    history_id   TEXT,
    last_sync    TEXT,
    last_error   TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id            TEXT NOT NULL,
    account       TEXT NOT NULL,
    thread_id     TEXT NOT NULL,
    internal_date INTEGER NOT NULL,
    from_raw      TEXT,
    from_name     TEXT,
    from_email    TEXT,
    to_raw        TEXT,
    cc_raw        TEXT,
    subject       TEXT,
    snippet       TEXT,
    label_ids     TEXT NOT NULL DEFAULT '[]',
    message_id_header TEXT,
    references_header TEXT,
    has_attachments INTEGER NOT NULL DEFAULT 0,
    body_json     TEXT,
    tipo          TEXT,
    subtipo       TEXT,
    first_seen    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (account, id)
);
CREATE INDEX IF NOT EXISTS ix_msg_thread ON messages(account, thread_id);
CREATE INDEX IF NOT EXISTS ix_msg_date ON messages(internal_date);

CREATE TABLE IF NOT EXISTS message_labels (
    account    TEXT NOT NULL,
    message_id TEXT NOT NULL,
    label_id   TEXT NOT NULL,
    PRIMARY KEY (account, message_id, label_id)
);
CREATE INDEX IF NOT EXISTS ix_ml_label ON message_labels(account, label_id);

CREATE TABLE IF NOT EXISTS labels (
    account    TEXT NOT NULL,
    id         TEXT NOT NULL,
    name       TEXT NOT NULL,
    type       TEXT NOT NULL,
    bg_color   TEXT,
    text_color TEXT,
    PRIMARY KEY (account, id)
);

CREATE TABLE IF NOT EXISTS local_read (
    account    TEXT NOT NULL,
    thread_id  TEXT NOT NULL,
    read_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (account, thread_id)
);

CREATE TABLE IF NOT EXISTS send_as (
    account        TEXT NOT NULL,
    email          TEXT NOT NULL,
    display_name   TEXT,
    api_signature  TEXT,
    local_signature TEXT,
    use_local      INTEGER NOT NULL DEFAULT 0,
    is_default     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (account, email)
);

CREATE TABLE IF NOT EXISTS rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    account    TEXT NOT NULL,
    direction  TEXT NOT NULL CHECK (direction IN ('recebido','enviado')),
    pattern    TEXT NOT NULL,
    label_ids  TEXT NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS rule_applied (
    rule_id    INTEGER NOT NULL,
    account    TEXT NOT NULL,
    message_id TEXT NOT NULL,
    PRIMARY KEY (rule_id, account, message_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    account    TEXT NOT NULL,
    message_id TEXT NOT NULL,
    thread_id  TEXT NOT NULL,
    from_name  TEXT,
    subject    TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (account, message_id)
);
"""


def _connect() -> sqlite3.Connection:
    global _initialized_for
    db_file = config.DB_FILE
    with _init_lock:
        if _initialized_for != db_file:
            os.makedirs(os.path.dirname(db_file), exist_ok=True)
            conn = sqlite3.connect(db_file)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            # Migração de bancos criados antes do contador de notificações
            cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
            for col in ("tipo", "subtipo"):
                if col not in cols:
                    conn.execute(f"ALTER TABLE messages ADD COLUMN {col} TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_msg_tipo ON messages(tipo)")
            conn.commit()
            conn.close()
            _initialized_for = db_file
    conn = sqlite3.connect(db_file, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def connection():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def rows(sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
    with connection() as c:
        return [dict(r) for r in c.execute(sql, tuple(params)).fetchall()]


def one(sql: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
    with connection() as c:
        r = c.execute(sql, tuple(params)).fetchone()
        return dict(r) if r else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with connection() as c:
        cur = c.execute(sql, tuple(params))
        return cur.lastrowid


# ─── Mensagens ────────────────────────────────────────────────────────────────

def upsert_message(account: str, m: Dict[str, Any]) -> bool:
    """Grava/atualiza uma mensagem. Retorna True se ela não existia antes."""
    with connection() as c:
        existed = c.execute(
            "SELECT 1 FROM messages WHERE account=? AND id=?", (account, m["id"])
        ).fetchone() is not None
        c.execute(
            """
            INSERT INTO messages (id, account, thread_id, internal_date, from_raw,
                from_name, from_email, to_raw, cc_raw, subject, snippet, label_ids,
                message_id_header, references_header, has_attachments, tipo, subtipo)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(account, id) DO UPDATE SET
                thread_id=excluded.thread_id,
                label_ids=excluded.label_ids,
                snippet=excluded.snippet,
                has_attachments=MAX(messages.has_attachments, excluded.has_attachments)
            """,
            (
                m["id"], account, m["thread_id"], m["internal_date"], m["from_raw"],
                m["from_name"], m["from_email"], m["to_raw"], m["cc_raw"], m["subject"],
                m["snippet"], json.dumps(m["label_ids"]), m["message_id_header"],
                m["references_header"], 1 if m.get("has_attachments") else 0,
                *classify.classify(m["from_raw"], m["subject"], m["snippet"]),
            ),
        )
        _set_labels(c, account, m["id"], m["label_ids"])
        return not existed


def _set_labels(c: sqlite3.Connection, account: str, message_id: str, label_ids: List[str]):
    c.execute("DELETE FROM message_labels WHERE account=? AND message_id=?", (account, message_id))
    c.executemany(
        "INSERT OR IGNORE INTO message_labels (account, message_id, label_id) VALUES (?,?,?)",
        [(account, message_id, lid) for lid in label_ids],
    )


def update_message_labels(account: str, message_id: str, label_ids: List[str]):
    with connection() as c:
        c.execute(
            "UPDATE messages SET label_ids=? WHERE account=? AND id=?",
            (json.dumps(label_ids), account, message_id),
        )
        _set_labels(c, account, message_id, label_ids)


def delete_message(account: str, message_id: str):
    with connection() as c:
        c.execute("DELETE FROM messages WHERE account=? AND id=?", (account, message_id))
        c.execute("DELETE FROM message_labels WHERE account=? AND message_id=?", (account, message_id))


def message_exists(account: str, message_id: str) -> bool:
    return one("SELECT 1 AS x FROM messages WHERE account=? AND id=?", (account, message_id)) is not None


def save_body(account: str, message_id: str, body: Dict[str, Any]):
    execute(
        "UPDATE messages SET body_json=?, has_attachments=? WHERE account=? AND id=?",
        (json.dumps(body), 1 if body.get("attachments") else 0, account, message_id),
    )


def decode_message(r: Dict[str, Any]) -> Dict[str, Any]:
    r = dict(r)
    r["label_ids"] = json.loads(r.get("label_ids") or "[]")
    body = r.pop("body_json", None)
    r["body"] = json.loads(body) if body else None
    return r


# ─── Contas ───────────────────────────────────────────────────────────────────

def ensure_account(email: str):
    execute("INSERT OR IGNORE INTO accounts (email) VALUES (?)", (email,))


def account_state(email: str) -> Optional[Dict[str, Any]]:
    return one("SELECT * FROM accounts WHERE email=?", (email,))


def set_account_state(email: str, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    execute(f"UPDATE accounts SET {cols} WHERE email=?", (*fields.values(), email))


def backfill_tipos() -> int:
    """Classifica mensagens antigas do cache que ainda não têm tipo."""
    pend = rows("SELECT account, id, from_raw, subject, snippet FROM messages WHERE tipo IS NULL")
    with connection() as c:
        for r in pend:
            c.execute("UPDATE messages SET tipo=?, subtipo=? WHERE account=? AND id=?",
                      (*classify.classify(r["from_raw"], r["subject"], r["snippet"]), r["account"], r["id"]))
    return len(pend)


# ─── Preferências ─────────────────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    # Quando "1", conversa lida no Gmail também aparece como lida no MarquesPro.
    # O inverso nunca acontece: abrir no MarquesPro não altera o Gmail.
    "lida_no_gmail_conta_como_lida": "0",
}


def get_setting(key: str) -> str:
    r = one("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else DEFAULT_SETTINGS.get(key, "")


def set_setting(key: str, value: str):
    if key not in DEFAULT_SETTINGS:
        raise ValueError("Preferência desconhecida")
    execute("INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value))


def all_settings() -> Dict[str, str]:
    return {k: get_setting(k) for k in DEFAULT_SETTINGS}
