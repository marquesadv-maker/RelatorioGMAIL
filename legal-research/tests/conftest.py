import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LR_DB"] = os.path.join(tempfile.mkdtemp(), "testes.db")
os.environ.setdefault("DATAJUD_API_KEY", "teste")
import pytest
from app import db


@pytest.fixture(autouse=True)
def banco_limpo():
    db.init_db()
    with db.session() as con:
        for t in ("entidades", "paginas", "documentos", "profissionais", "partes", "processos", "filtros_salvos"):
            con.execute(f"DELETE FROM {t}")
    yield
