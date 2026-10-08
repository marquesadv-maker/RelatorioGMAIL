"""
Sincronização Gmail → cache local, aplicação de regras de etiquetas e
registro de notificações (mensagens novas na caixa de entrada).

- Sincronização inicial: mensagens dos últimos SYNC_DAYS dias.
- Incremental: users.history.list a partir do último historyId.
- Somente leitura de estado no Gmail, exceto a inclusão de etiquetas
  pelas regras configuradas (nunca remove UNREAD/INBOX).
"""
import json
import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from googleapiclient.errors import HttpError

from . import auth, config, db, gmail_ops

log = logging.getLogger("gestor_email.sync")

_sync_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(account: str) -> threading.Lock:
    with _locks_guard:
        return _sync_locks.setdefault(account, threading.Lock())


# ─── Regras de etiquetas ──────────────────────────────────────────────────────

def _matches(rule: Dict[str, Any], m: Dict[str, Any]) -> bool:
    pattern = (rule["pattern"] or "").strip().lower()
    if not pattern:
        return False
    labels = m.get("label_ids") or []
    is_sent = "SENT" in labels
    if rule["direction"] == "enviado":
        # Mensagem enviada pelo usuário/alias indicado (campo De)
        return is_sent and pattern in (m.get("from_raw") or "").lower()
    # Recebida: remetente contém o padrão (nome ou e-mail)
    return (not is_sent) and pattern in (m.get("from_raw") or "").lower()


def apply_rules(service, account: str, messages: Iterable[Dict[str, Any]],
                rule_id: Optional[int] = None) -> int:
    """Aplica as regras ativas às mensagens informadas. Retorna quantas foram etiquetadas."""
    sql = "SELECT * FROM rules WHERE account=? AND active=1"
    params: List[Any] = [account]
    if rule_id is not None:
        sql += " AND id=?"
        params.append(rule_id)
    rules = db.rows(sql, params)
    if not rules:
        return 0
    count = 0
    for m in messages:
        to_add: List[str] = []
        applied: List[int] = []
        for r in rules:
            if db.one("SELECT 1 AS x FROM rule_applied WHERE rule_id=? AND account=? AND message_id=?",
                      (r["id"], account, m["id"])):
                continue
            if _matches(r, m):
                wanted = [l for l in json.loads(r["label_ids"]) if l not in (m.get("label_ids") or [])]
                to_add.extend(wanted)
                applied.append(r["id"])
        if applied:
            if to_add:
                try:
                    gmail_ops.add_message_labels(service, account, m["id"], sorted(set(to_add)))
                    count += 1
                except HttpError as e:
                    log.warning("Falha ao aplicar regra em %s: %s", m["id"], e)
                    continue
            for rid in applied:
                db.execute("INSERT OR IGNORE INTO rule_applied (rule_id, account, message_id) VALUES (?,?,?)",
                           (rid, account, m["id"]))
    return count


def apply_rule_to_existing(account: str, rule_id: int) -> int:
    service = auth.get_service(account)
    msgs = [db.decode_message(r) for r in db.rows(
        "SELECT * FROM messages WHERE account=?", (account,))]
    return apply_rules(service, account, msgs, rule_id=rule_id)


# ─── Notificações ─────────────────────────────────────────────────────────────

def _register_notification(account: str, m: Dict[str, Any]):
    labels = m.get("label_ids") or []
    if "INBOX" not in labels or "SENT" in labels:
        return
    db.execute(
        "INSERT OR IGNORE INTO notifications (account, message_id, thread_id, from_name, subject) "
        "VALUES (?,?,?,?,?)",
        (account, m["id"], m["thread_id"], m["from_name"], m["subject"]),
    )


# ─── Sincronização ────────────────────────────────────────────────────────────

def _store(service, account: str, raw_msgs: List[Dict[str, Any]], notify: bool, rules: bool) -> int:
    new_msgs = []
    for raw in raw_msgs:
        m = gmail_ops.parse_metadata(raw)
        if db.upsert_message(account, m):
            new_msgs.append(m)
            if notify:
                _register_notification(account, m)
    if rules and new_msgs:
        apply_rules(service, account, new_msgs)
    return len(new_msgs)


def full_sync(service, account: str) -> int:
    profile = service.users().getProfile(userId="me").execute()
    history_id = profile.get("historyId")
    gmail_ops.sync_labels(service, account)
    try:
        gmail_ops.sync_send_as(service, account)
    except HttpError as e:
        log.warning("Não foi possível ler assinaturas de %s: %s", account, e)

    ids: List[str] = []
    page = None
    while len(ids) < config.SYNC_MAX_MESSAGES:
        params = {"userId": "me", "q": f"newer_than:{config.SYNC_DAYS}d",
                  "maxResults": min(500, config.SYNC_MAX_MESSAGES - len(ids))}
        if page:
            params["pageToken"] = page
        resp = service.users().messages().list(**params).execute()
        ids.extend(m["id"] for m in resp.get("messages", []))
        page = resp.get("nextPageToken")
        if not page:
            break

    # Só busca o que ainda não está no cache, mas atualiza etiquetas de todos
    # na incremental; aqui basta trazer os ausentes.
    missing_local = [i for i in ids if not db.message_exists(account, i)]
    found, _ = gmail_ops.get_metadata_batch(service, missing_local)
    # Na primeira carga não gera notificações nem aplica regras retroativamente.
    first_load = db.account_state(account) is None or not db.account_state(account).get("history_id")
    n = _store(service, account, found, notify=not first_load, rules=not first_load)
    db.set_account_state(account, history_id=history_id, last_sync=_now(), last_error=None)
    return n


def incremental_sync(service, account: str, start_history_id: str) -> int:
    changed: Dict[str, None] = {}
    deleted: set = set()
    page = None
    latest = start_history_id
    while True:
        params = {"userId": "me", "startHistoryId": start_history_id,
                  "historyTypes": ["messageAdded", "messageDeleted", "labelAdded", "labelRemoved"]}
        if page:
            params["pageToken"] = page
        resp = service.users().history().list(**params).execute()
        latest = resp.get("historyId", latest)
        for h in resp.get("history", []) or []:
            for key in ("messagesAdded", "labelsAdded", "labelsRemoved"):
                for item in h.get(key, []) or []:
                    changed[item["message"]["id"]] = None
            for item in h.get("messagesDeleted", []) or []:
                deleted.add(item["message"]["id"])
        page = resp.get("nextPageToken")
        if not page:
            break

    for mid in deleted:
        db.delete_message(account, mid)
        changed.pop(mid, None)

    ids = list(changed)
    found, missing = gmail_ops.get_metadata_batch(service, ids)
    for mid in missing:
        db.delete_message(account, mid)
    # Filtra spam/lixeira do cache (não aparecem nas listas, mas mantém coerência)
    n = _store(service, account, found, notify=True, rules=True)
    db.set_account_state(account, history_id=latest, last_sync=_now(), last_error=None)
    return n


def sync_account(account: str) -> Dict[str, Any]:
    lock = _lock_for(account)
    if not lock.acquire(blocking=False):
        return {"account": account, "status": "em andamento"}
    try:
        db.ensure_account(account)
        service = auth.get_service(account)
        state = db.account_state(account) or {}
        hid = state.get("history_id")
        if hid:
            try:
                n = incremental_sync(service, account, hid)
            except HttpError as e:
                if getattr(e.resp, "status", None) == 404:  # historyId expirado
                    n = full_sync(service, account)
                else:
                    raise
            # Etiquetas podem ter sido criadas/renomeadas no Gmail
            gmail_ops.sync_labels(service, account)
        else:
            n = full_sync(service, account)
        return {"account": account, "status": "ok", "novas": n}
    except Exception as e:  # registra e segue para a próxima conta
        log.exception("Erro ao sincronizar %s", account)
        db.set_account_state(account, last_error=str(e)[:500])
        return {"account": account, "status": "erro", "erro": str(e)[:500]}
    finally:
        lock.release()


def sync_all() -> List[Dict[str, Any]]:
    return [sync_account(a) for a in auth.list_accounts()]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SyncLoop(threading.Thread):
    daemon = True

    def __init__(self, interval: int = config.SYNC_INTERVAL_SECONDS):
        super().__init__(name="gestor-sync")
        self.interval = interval
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            sync_all()
            self._stop_event.wait(self.interval)

    def stop(self):
        self._stop_event.set()
