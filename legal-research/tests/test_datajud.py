"""Testes com uma resposta no formato documentado do DataJud (estrutura real; conteúdo de exemplo)."""
import os, sys, tempfile, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db
from app.fontes import datajud
from app.query import build_fts

SRC = {
    "numeroProcesso": "00012345620235020001", "tribunal": "TRT2", "grau": "G1", "nivelSigilo": 0,
    "classe": {"codigo": 985, "nome": "Ação Trabalhista - Rito Ordinário"},
    "assuntos": [{"codigo": 2704, "nome": "Horas Extras"}, {"codigo": 1855, "nome": "Indenização por Dano Moral"}],
    "orgaoJulgador": {"codigo": 1, "nome": "1ª Vara do Trabalho de São Paulo"},
    "dataAjuizamento": "2023-03-10T00:00:00.000Z",
    "movimentos": [
        {"codigo": 26, "nome": "Distribuição", "dataHora": "2023-03-10T10:00:00.000Z"},
        {"codigo": 970, "nome": "Audiência", "dataHora": "2023-08-01T14:00:00.000Z", "complementosTabelados": [{"nome": "tipo_de_audiencia", "descricao": "Una"}]},
        {"codigo": 466, "nome": "Homologação de transação", "dataHora": "2023-08-01T15:00:00.000Z"},
        {"codigo": 848, "nome": "Trânsito em julgado", "dataHora": "2023-08-20T10:00:00.000Z"},
        {"codigo": 22, "nome": "Baixa Definitiva", "dataHora": "2023-12-01T10:00:00.000Z"},
    ],
}


def test_alias_e_importacao():
    assert datajud.alias_for("0001234-56.2023.5.02.0001") == "api_publica_trt2"
    st = datajud.importar([SRC], log=lambda *_: None)
    assert st["processos"] == 1
    with db.session() as con:
        p = con.execute("SELECT * FROM processos").fetchone()
        assert p["numero"] == "0001234-56.2023.5.02.0001" and p["uf"] == "SP" and p["status"] == "Arquivado"
        assert p["acordo_homologado"] == 1 and p["transito_julgado"] == 1 and p["desfecho"] == "Acordo"
        n = con.execute("SELECT COUNT(*) FROM paginas_fts WHERE paginas_fts MATCH ?", (build_fts("homologação transação", {})[0],)).fetchone()[0]
        assert n == 1
        assert con.execute("SELECT COUNT(*) FROM entidades WHERE tipo='varas'").fetchone()[0] >= 1


def test_fts_avancada():
    expr, hl = build_fts("", {"fraseExata": "horas extras", "nenhumaPalavra": "acordo", "numeroLei": "13.467", "anoLei": "2017"})
    assert '"horas extras"' in expr and "NOT" in expr and "13467" in expr.replace(".", "") and "2017" in expr
