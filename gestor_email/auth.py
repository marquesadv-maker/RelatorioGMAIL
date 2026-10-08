"""
Autorização OAuth por conta (cada usuário do escritório conecta a própria
conta Google). Os tokens ficam em dados/tokens/<email>.json, separados do
token.json do gmail_monitor.py.
"""
import os
import re
import threading
from typing import Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from . import config, db

_token_lock = threading.Lock()
_local = threading.local()

_EMAIL_RE = re.compile(r"^[^@\s/\\]+@[^@\s/\\]+\.[^@\s/\\]+$")


def _token_path(email: str) -> str:
    if not _EMAIL_RE.match(email):
        raise ValueError("E-mail inválido")
    return os.path.join(config.TOKENS_DIR, f"{email.lower()}.json")


def list_accounts() -> List[str]:
    if not os.path.isdir(config.TOKENS_DIR):
        return []
    out = []
    for name in sorted(os.listdir(config.TOKENS_DIR)):
        if name.endswith(".json"):
            out.append(name[:-5])
    return out


def _load_credentials(email: str) -> Credentials:
    path = _token_path(email)
    if not os.path.exists(path):
        raise RuntimeError(f"Conta {email} não conectada")
    with _token_lock:
        creds = Credentials.from_authorized_user_file(path, config.SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            else:
                raise RuntimeError(f"Autorização da conta {email} expirou; reconecte-a")
    return creds


def get_service(email: str):
    """Serviço Gmail por thread (o cliente HTTP do Google não é thread-safe)."""
    cache: Dict[str, object] = getattr(_local, "services", None)
    if cache is None:
        cache = _local.services = {}
    svc = cache.get(email)
    creds = getattr(svc, "_gestor_creds", None) if svc else None
    if svc is None or creds is None or not creds.valid:
        creds = _load_credentials(email)
        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        svc._gestor_creds = creds
        cache[email] = svc
    return svc


def connect_account(login_hint: Optional[str] = None) -> str:
    """
    Abre o navegador para o usuário autorizar a conta e grava o token.
    Bloqueia até a autorização terminar. Retorna o e-mail conectado.
    """
    if not os.path.exists(config.CREDENTIALS_FILE):
        raise RuntimeError(
            "Arquivo credentials.json não encontrado. Coloque-o na pasta do projeto "
            "(o mesmo usado pelo gmail_monitor.py)."
        )
    flow = InstalledAppFlow.from_client_secrets_file(config.CREDENTIALS_FILE, config.SCOPES)
    kwargs = {"port": 0, "prompt": "consent", "access_type": "offline"}
    if login_hint:
        kwargs["login_hint"] = login_hint
    creds = flow.run_local_server(**kwargs)
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
    email = svc.users().getProfile(userId="me").execute()["emailAddress"].lower()
    os.makedirs(config.TOKENS_DIR, exist_ok=True)
    with _token_lock:
        with open(_token_path(email), "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    db.ensure_account(email)
    return email


def disconnect_account(email: str):
    path = _token_path(email)
    with _token_lock:
        if os.path.exists(path):
            os.remove(path)
    services = getattr(_local, "services", None)
    if services:
        services.pop(email, None)
