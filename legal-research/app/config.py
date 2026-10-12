"""Configuração: lê variáveis do ambiente e de um arquivo .env na raiz do projeto (nunca versionado)."""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(BASE, ".env")


def load_env():
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()


def get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)
