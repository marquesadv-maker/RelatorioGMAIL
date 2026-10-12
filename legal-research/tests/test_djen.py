"""Teste do conector DJEN com um item no formato observado em integrações públicas da ComunicaAPI (conteúdo de exemplo)."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import db
from app.fontes import djen
from app.query import build_fts

ITEM = {
    "id": 123456, "numero_processo": "00012345620235020001", "numeroprocessocommascara": "0001234-56.2023.5.02.0001",
    "siglaTribunal": "TRT2", "tipoComunicacao": "Intimação", "tipoDocumento": "Despacho", "nomeOrgao": "1ª Vara do Trabalho de São Paulo",
    "nomeClasse": "Ação Trabalhista - Rito Ordinário", "data_disponibilizacao": "2024-05-10", "meio": "D", "link": "https://comunica.pje.jus.br/consulta?id=123456",
    "texto": "<p>Intime-se a parte reclamada <b>EMPRESA EXEMPLO LTDA</b> para manifestação em 5 dias, nos termos do art. 841 da CLT.</p>",
    "destinatarios": [{"nome": "PESSOA EXEMPLO", "polo": "A"}, {"nome": "EMPRESA EXEMPLO LTDA", "polo": "P"}],
    "destinatarioadvogados": [{"advogado": {"nome": "ADVOGADO EXEMPLO", "numero_oab": "123456", "uf_oab": "SP"}}],
}


def test_importa_publicacao():
    st = djen.importar([ITEM])
    assert st["processos"] == 1 and st["publicacoes"] == 1
    with db.session() as con:
        p = con.execute("SELECT * FROM processos").fetchone()
        assert p["numero"] == "0001234-56.2023.5.02.0001" and p["tribunal"] == "TRT-2" and p["uf"] == "SP"
        assert con.execute("SELECT COUNT(*) FROM partes WHERE polo='passivo'").fetchone()[0] == 1
        assert con.execute("SELECT registro FROM profissionais").fetchone()[0] == "SP 123456"
        n = con.execute("SELECT COUNT(*) FROM paginas_fts WHERE paginas_fts MATCH ?", (build_fts("empresa exemplo", {})[0],)).fetchone()[0]
        assert n == 1
        assert "<p>" not in con.execute("SELECT texto FROM paginas").fetchone()[0]
    # reimportação não duplica
    st2 = djen.importar([ITEM])
    assert st2["publicacoes"] == 0 and st2["ignoradas"] == 1


def test_valida_parametros():
    import pytest
    with pytest.raises(ValueError):
        list(djen.buscar())
