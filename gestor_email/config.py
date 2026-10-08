"""
Configurações do Gestor de E-mail.

Todas podem ser sobrescritas por variáveis de ambiente com o mesmo nome.
"""
import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PACKAGE_DIR)

# Mesmo arquivo de cliente OAuth usado pelo gmail_monitor.py
CREDENTIALS_FILE = os.environ.get(
    "GESTOR_CREDENTIALS_FILE", os.path.join(PROJECT_DIR, "credentials.json")
)

# Dados locais (tokens e cache). Nunca versionar — ver .gitignore.
DATA_DIR = os.environ.get("GESTOR_DATA_DIR", os.path.join(PACKAGE_DIR, "dados"))
TOKENS_DIR = os.path.join(DATA_DIR, "tokens")
DB_FILE = os.path.join(DATA_DIR, "gestor_email.db")

# Escopos: gmail.modify permite ler, enviar e alterar etiquetas, mas não
# exclui definitivamente. O token é separado do token.json do monitor,
# que continua apenas com gmail.readonly.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

HOST = os.environ.get("GESTOR_HOST", "127.0.0.1")
PORT = int(os.environ.get("GESTOR_PORT", "5055"))

# Janela da sincronização inicial e intervalo da sincronização incremental
SYNC_DAYS = int(os.environ.get("GESTOR_SYNC_DAYS", "60"))
SYNC_MAX_MESSAGES = int(os.environ.get("GESTOR_SYNC_MAX", "3000"))
SYNC_INTERVAL_SECONDS = int(os.environ.get("GESTOR_SYNC_INTERVAL", "60"))

# Etiquetas que o sistema NUNCA remove nem adiciona no Gmail, para não
# alterar o que a controladoria enxerga como "não lido" ou "na caixa".
PROTECTED_LABELS = {"UNREAD", "INBOX", "TRASH", "SPAM", "DRAFT", "SENT"}
