"""Camada de persistência: SQLite + FTS5 (busca textual com remoção de acentos)."""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("LR_DB", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "legal_research.db"))

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS processos (
    id INTEGER PRIMARY KEY,
    numero TEXT UNIQUE NOT NULL,
    tribunal TEXT, uf TEXT, grau TEXT, ano INTEGER,
    orgao_julgador TEXT, orgao_origem TEXT, comarca TEXT,
    classe TEXT, assunto TEXT, fase TEXT, status TEXT, desfecho TEXT,
    valor_causa REAL, valor_condenacao REAL, valor_acordo REAL, valor_liquidacao REAL, custas REAL,
    data_ajuizamento TEXT, data_encerramento TEXT,
    transito_julgado INTEGER DEFAULT 0, acordo_homologado INTEGER DEFAULT 0,
    bloqueio INTEGER DEFAULT 0, revelia INTEGER DEFAULT 0,
    sindicato INTEGER DEFAULT 0, acao_coletiva INTEGER DEFAULT 0, covid INTEGER DEFAULT 0,
    pf_polo_passivo INTEGER DEFAULT 0, sem_advogado_passivo INTEGER DEFAULT 0,
    pasta TEXT
);
CREATE TABLE IF NOT EXISTS partes (
    id INTEGER PRIMARY KEY, processo_id INTEGER NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
    nome TEXT NOT NULL, polo TEXT, tipo_pessoa TEXT, documento TEXT, atividade_economica TEXT
);
CREATE TABLE IF NOT EXISTS profissionais (
    id INTEGER PRIMARY KEY, processo_id INTEGER NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
    nome TEXT NOT NULL, papel TEXT NOT NULL, registro TEXT, polo TEXT
);
CREATE TABLE IF NOT EXISTS documentos (
    id INTEGER PRIMARY KEY, processo_id INTEGER NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
    arquivo TEXT NOT NULL, caminho TEXT NOT NULL UNIQUE, tipo TEXT, data_documento TEXT,
    fase TEXT, paginas INTEGER, tamanho INTEGER, hash TEXT, indexado_em TEXT
);
CREATE TABLE IF NOT EXISTS paginas (
    id INTEGER PRIMARY KEY, documento_id INTEGER NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    numero INTEGER NOT NULL, texto TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS paginas_fts USING fts5(
    texto, content='paginas', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS paginas_ai AFTER INSERT ON paginas BEGIN
    INSERT INTO paginas_fts(rowid, texto) VALUES (new.id, new.texto);
END;
CREATE TRIGGER IF NOT EXISTS paginas_ad AFTER DELETE ON paginas BEGIN
    INSERT INTO paginas_fts(paginas_fts, rowid, texto) VALUES ('delete', old.id, old.texto);
END;
CREATE TABLE IF NOT EXISTS entidades (
    id INTEGER PRIMARY KEY, documento_id INTEGER NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    pagina INTEGER, tipo TEXT NOT NULL, valor TEXT NOT NULL, valor_norm TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ent_tipo ON entidades(tipo, valor_norm);
CREATE INDEX IF NOT EXISTS idx_ent_doc ON entidades(documento_id);
CREATE INDEX IF NOT EXISTS idx_pag_doc ON paginas(documento_id);
CREATE INDEX IF NOT EXISTS idx_doc_proc ON documentos(processo_id);
CREATE INDEX IF NOT EXISTS idx_partes_proc ON partes(processo_id);
CREATE TABLE IF NOT EXISTS filtros_salvos (
    id INTEGER PRIMARY KEY, nome TEXT NOT NULL, corpo TEXT NOT NULL, criado_em TEXT
);
"""


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db():
    con = connect()
    con.executescript(SCHEMA)
    con.commit()
    con.close()


@contextmanager
def session():
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()
