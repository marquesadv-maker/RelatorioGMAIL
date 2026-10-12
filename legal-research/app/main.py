"""API do Legal Research local (compatível, em espírito, com os endpoints observados na ferramenta de referência)."""
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config  # noqa: F401  (carrega .env)
from . import db
from .fontes import datajud, privadas
from .indexer import index_folder
from .query import ENT_TIPOS, ORDER, build_fts, doc_where, entity_where, process_where

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
DOCS_ROOT = os.path.abspath(os.environ.get("LR_DOCS", os.path.join(BASE, "data", "documentos")))
UPLOAD_ROOT = os.environ.get("LR_UPLOADS", os.path.join(BASE, "data", "uploads"))

app = FastAPI(title="Legal Research Local", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class Bloco(BaseModel):
    conteudo: Dict[str, Any] = {}


class Consulta(BaseModel):
    filtroGeral: Optional[Bloco] = None
    filtroPesquisaTextual: Optional[Bloco] = None


@app.on_event("startup")
def _startup():
    db.init_db()
    if os.environ.get("LR_AUTOINDEX", "1") == "1" and os.path.isdir(DOCS_ROOT):
        index_folder(DOCS_ROOT, log=lambda *_: None)
    if os.path.isdir(UPLOAD_ROOT):
        index_folder(UPLOAD_ROOT, log=lambda *_: None)


@app.get("/", response_class=HTMLResponse)
def home():
    with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------- busca

def _parts(q: Consulta):
    fg = (q.filtroGeral.conteudo if q.filtroGeral else {}) or {}
    ft = (q.filtroPesquisaTextual.conteudo if q.filtroPesquisaTextual else {}) or {}
    return fg, ft


def _build(q: Consulta):
    fg, ft = _parts(q)
    pw, pp = process_where(fg)
    dw, dp = doc_where(ft)
    trecho = (ft.get("trecho") or "").strip()
    adv = ft.get("buscaDocumentosAvancada") or {}
    fts, hl = build_fts(trecho, adv, modo_ia=bool(ft.get("modoIA")))
    ew, ep = entity_where(ft.get("tiposEntidades") or [], [trecho] if trecho else [])
    return fg, ft, pw, pp, dw, dp, fts, hl, ew, ep


def _from_clause(fts: str, ew: str):
    if fts:
        base = ("FROM paginas_fts f JOIN paginas pg ON pg.id=f.rowid JOIN documentos d ON d.id=pg.documento_id "
                "JOIN processos p ON p.id=d.processo_id WHERE paginas_fts MATCH ? ")
    else:
        base = ("FROM paginas pg JOIN documentos d ON d.id=pg.documento_id JOIN processos p ON p.id=d.processo_id "
                "WHERE pg.numero=1 ")
    if ew:
        base += " AND " + ew
    return base


@app.post("/api/documento")
def buscar(q: Consulta, limite: int = Query(30, le=200), deslocamento: int = 0):
    fg, ft, pw, pp, dw, dp, fts, hl, ew, ep = _build(q)
    frm = _from_clause(fts, ew)
    params = ([fts] if fts else []) + ep + pp + dp
    ordem = ORDER.get(ft.get("tipoOrdenacao") or "relevancia", ORDER["relevancia"]) if fts else "d.data_documento DESC, pg.numero"
    if fts:
        snippet = "snippet(paginas_fts, 0, '<mark>', '</mark>', ' … ', 28)"
        rank = "bm25(paginas_fts)"
    else:
        snippet = "substr(pg.texto, 1, 240)"
        rank = "0"
    sql = (f"SELECT pg.id AS pagina_id, pg.numero AS pagina, d.id AS documento_id, d.arquivo, d.tipo, d.data_documento, d.paginas, d.fase AS fase_doc, "
           f"p.id AS processo_id, p.numero AS processo, p.tribunal, p.uf, p.orgao_julgador, p.classe, p.status, p.fase, {snippet} AS trecho, {rank} AS rank "
           f"{frm} AND ({pw}) AND ({dw}) ORDER BY {ordem} LIMIT ? OFFSET ?")
    with db.session() as con:
        try:
            rows = con.execute(sql, (*params, limite, deslocamento)).fetchall()
        except Exception as e:  # consulta FTS inválida
            raise HTTPException(400, f"Expressão de busca inválida: {e}")
        tot = con.execute(f"SELECT COUNT(*) AS n, COUNT(DISTINCT d.id) AS docs, COUNT(DISTINCT p.id) AS procs {frm} AND ({pw}) AND ({dw})", params).fetchone()
        out = []
        for r in rows:
            d = dict(r)
            d["partes"] = [dict(x) for x in con.execute("SELECT nome, polo, tipo_pessoa FROM partes WHERE processo_id=? ORDER BY polo", (r["processo_id"],))]
            out.append(d)
    return {"resultados": out, "totalTrechos": tot["n"], "totalDocumentos": tot["docs"], "totalProcessos": tot["procs"],
            "destaques": hl, "limite": limite, "deslocamento": deslocamento}


@app.post("/api/documento/obterQuantidadeDeProcessos")
def quantidade(q: Consulta):
    fg, ft, pw, pp, dw, dp, fts, hl, ew, ep = _build(q)
    frm = _from_clause(fts, ew)
    params = ([fts] if fts else []) + ep + pp + dp
    with db.session() as con:
        r = con.execute(f"SELECT COUNT(DISTINCT d.id) AS docs, COUNT(DISTINCT p.id) AS procs {frm} AND ({pw}) AND ({dw})", params).fetchone()
        total = con.execute("SELECT COUNT(*) FROM processos").fetchone()[0]
    return {"processos": r["procs"], "documentos": r["docs"], "totalBase": total}


FACETAS = {
    "tiposDocumento": "d.tipo", "tribunais": "p.tribunal", "ufs": "p.uf", "fases": "p.fase", "status": "p.status",
    "classes": "p.classe", "assuntos": "p.assunto", "orgaosJulgadores": "p.orgao_julgador", "graus": "p.grau",
    "fasesDocumento": "d.fase", "anosDocumento": "substr(d.data_documento,1,4)", "desfechos": "p.desfecho",
}


@app.post("/api/documento/obterMenuLateral")
def menu_lateral(q: Consulta):
    fg, ft, pw, pp, dw, dp, fts, hl, ew, ep = _build(q)
    frm = _from_clause(fts, ew)
    params = ([fts] if fts else []) + ep + pp + dp
    out: Dict[str, Any] = {}
    with db.session() as con:
        for nome, col in FACETAS.items():
            rows = con.execute(f"SELECT {col} AS v, COUNT(DISTINCT d.id) AS n {frm} AND ({pw}) AND ({dw}) AND {col} IS NOT NULL GROUP BY {col} ORDER BY n DESC LIMIT 40", params).fetchall()
            out[nome] = [{"valor": r["v"], "quantidade": r["n"]} for r in rows]
        docs_sql = f"SELECT DISTINCT d.id {frm} AND ({pw}) AND ({dw})"
        out["entidades"] = {}
        for t in ENT_TIPOS:
            rows = con.execute(f"SELECT e.valor AS v, COUNT(DISTINCT e.documento_id) AS n FROM entidades e WHERE e.tipo=? AND e.documento_id IN ({docs_sql}) GROUP BY e.valor_norm ORDER BY n DESC LIMIT 25", (t, *params)).fetchall()
            out["entidades"][t] = [{"valor": r["v"], "quantidade": r["n"]} for r in rows]
        procs_sql = f"SELECT DISTINCT p.id {frm} AND ({pw}) AND ({dw})"
        out["partes"] = [{"valor": r["v"], "quantidade": r["n"]} for r in con.execute(f"SELECT nome AS v, COUNT(DISTINCT processo_id) AS n FROM partes WHERE processo_id IN ({procs_sql}) GROUP BY lower(nome) ORDER BY n DESC LIMIT 25", params)]
        out["advogados"] = [{"valor": r["v"], "quantidade": r["n"]} for r in con.execute(f"SELECT nome AS v, COUNT(DISTINCT processo_id) AS n FROM profissionais WHERE papel='advogado' AND processo_id IN ({procs_sql}) GROUP BY lower(nome) ORDER BY n DESC LIMIT 25", params)]
        out["magistrados"] = [{"valor": r["v"], "quantidade": r["n"]} for r in con.execute(f"SELECT nome AS v, COUNT(DISTINCT processo_id) AS n FROM profissionais WHERE papel='magistrado' AND processo_id IN ({procs_sql}) GROUP BY lower(nome) ORDER BY n DESC LIMIT 25", params)]
        out["marcadores"] = {}
        for flag in ("transito_julgado", "acordo_homologado", "bloqueio", "revelia", "sindicato", "acao_coletiva", "covid", "pf_polo_passivo", "sem_advogado_passivo"):
            out["marcadores"][flag] = con.execute(f"SELECT COUNT(DISTINCT p.id) {frm} AND ({pw}) AND ({dw}) AND p.{flag}=1", params).fetchone()[0]
    return out


@app.post("/api/jurimetria")
def jurimetria(q: Consulta):
    fg, ft, pw, pp, dw, dp, fts, hl, ew, ep = _build(q)
    frm = _from_clause(fts, ew)
    params = ([fts] if fts else []) + ep + pp + dp
    procs_sql = f"SELECT DISTINCT p.id {frm} AND ({pw}) AND ({dw})"
    with db.session() as con:
        base = f"FROM processos p WHERE p.id IN ({procs_sql})"
        g = con.execute(f"SELECT COUNT(*) n, AVG(valor_causa) vc, AVG(valor_condenacao) vcond, AVG(valor_acordo) vac, "
                        f"SUM(acordo_homologado) acordos, SUM(transito_julgado) transitados, SUM(revelia) revelias, SUM(bloqueio) bloqueios, "
                        f"AVG(julianday(COALESCE(data_encerramento, date('now'))) - julianday(data_ajuizamento)) dur {base}", params).fetchone()

        def grp(col):
            return [{"valor": r[0], "quantidade": r[1]} for r in con.execute(f"SELECT {col}, COUNT(*) {base} AND {col} IS NOT NULL GROUP BY {col} ORDER BY 2 DESC LIMIT 20", params)]
        return {
            "processos": g["n"], "valorMedioCausa": g["vc"], "valorMedioCondenacao": g["vcond"], "valorMedioAcordo": g["vac"],
            "taxaAcordo": (g["acordos"] or 0) / g["n"] if g["n"] else None, "transitados": g["transitados"], "revelias": g["revelias"], "bloqueios": g["bloqueios"],
            "duracaoMediaDias": g["dur"],
            "porTribunal": grp("tribunal"), "porUf": grp("uf"), "porFase": grp("fase"), "porStatus": grp("status"),
            "porDesfecho": grp("desfecho"), "porAno": grp("ano"), "porClasse": grp("classe"), "porAssunto": grp("assunto"), "porOrgao": grp("orgao_julgador"),
            "documentosPorTipo": [{"valor": r[0], "quantidade": r[1]} for r in con.execute(f"SELECT d.tipo, COUNT(*) FROM documentos d WHERE d.processo_id IN ({procs_sql}) GROUP BY d.tipo ORDER BY 2 DESC", params)],
        }


# ---------------------------------------------------------------- home (dashboards)

@app.post("/api/home/{painel}")
def painel_home(painel: str):
    with db.session() as con:
        if painel == "total":
            r = con.execute("SELECT (SELECT COUNT(*) FROM processos) p, (SELECT COUNT(*) FROM documentos) d, (SELECT COUNT(*) FROM paginas) pg").fetchone()
            return {"processos": r["p"], "documentos": r["d"], "paginas": r["pg"]}
        if painel == "ativosPorUf":
            return [{"uf": r[0], "quantidade": r[1]} for r in con.execute("SELECT uf, COUNT(*) FROM processos WHERE status='Ativo' AND uf IS NOT NULL GROUP BY uf ORDER BY 2 DESC")]
        if painel == "valorMedioCausas":
            return {"valorMedio": con.execute("SELECT AVG(valor_causa) FROM processos").fetchone()[0]}
        if painel == "duracaoMedia":
            return {"dias": con.execute("SELECT AVG(julianday(COALESCE(data_encerramento, date('now'))) - julianday(data_ajuizamento)) FROM processos WHERE data_ajuizamento IS NOT NULL").fetchone()[0]}
        if painel == "porFase":
            return [{"fase": r[0], "quantidade": r[1]} for r in con.execute("SELECT fase, COUNT(*) FROM processos GROUP BY fase")]
        if painel == "porTribunal":
            return [{"tribunal": r[0], "quantidade": r[1]} for r in con.execute("SELECT tribunal, COUNT(*) FROM processos GROUP BY tribunal ORDER BY 2 DESC")]
    raise HTTPException(404, "painel desconhecido")


# ---------------------------------------------------------------- autocomplete

AUTOCOMPLETE = {
    "parte": "SELECT DISTINCT nome FROM partes WHERE lower(nome) LIKE ? ORDER BY nome LIMIT 15",
    "advogado": "SELECT DISTINCT nome FROM profissionais WHERE papel='advogado' AND lower(nome) LIKE ? ORDER BY nome LIMIT 15",
    "magistrado": "SELECT DISTINCT nome FROM profissionais WHERE papel='magistrado' AND lower(nome) LIKE ? ORDER BY nome LIMIT 15",
    "orgaoJulgador": "SELECT DISTINCT orgao_julgador FROM processos WHERE lower(orgao_julgador) LIKE ? ORDER BY 1 LIMIT 15",
    "assunto": "SELECT DISTINCT assunto FROM processos WHERE lower(assunto) LIKE ? ORDER BY 1 LIMIT 15",
    "classe": "SELECT DISTINCT classe FROM processos WHERE lower(classe) LIKE ? ORDER BY 1 LIMIT 15",
    "tipoDocumento": "SELECT DISTINCT tipo FROM documentos WHERE lower(tipo) LIKE ? ORDER BY 1 LIMIT 15",
    "processo": "SELECT DISTINCT numero FROM processos WHERE numero LIKE ? ORDER BY 1 LIMIT 15",
}


@app.get("/api/autocomplete/{esfera}/{campo}")
def autocomplete(esfera: str, campo: str, q: str = ""):
    if campo in ENT_TIPOS:
        sql = "SELECT DISTINCT valor FROM entidades WHERE tipo=? AND valor_norm LIKE ? ORDER BY valor LIMIT 15"
        args = (campo, f"%{q.lower()}%")
    elif campo in AUTOCOMPLETE:
        sql, args = AUTOCOMPLETE[campo], (f"%{q.lower()}%",)
    else:
        raise HTTPException(404, "campo desconhecido")
    with db.session() as con:
        return [r[0] for r in con.execute(sql, args) if r[0]]


# ---------------------------------------------------------------- documento

@app.get("/api/documento/{doc_id}")
def documento(doc_id: int, pagina: Optional[int] = None):
    with db.session() as con:
        d = con.execute("SELECT d.*, p.numero AS processo, p.tribunal FROM documentos d JOIN processos p ON p.id=d.processo_id WHERE d.id=?", (doc_id,)).fetchone()
        if not d:
            raise HTTPException(404)
        if pagina:
            pages = con.execute("SELECT numero, texto FROM paginas WHERE documento_id=? AND numero=?", (doc_id, pagina)).fetchall()
        else:
            pages = con.execute("SELECT numero, texto FROM paginas WHERE documento_id=? ORDER BY numero", (doc_id,)).fetchall()
        ents = con.execute("SELECT tipo, valor, pagina FROM entidades WHERE documento_id=? ORDER BY tipo, valor", (doc_id,)).fetchall()
        return {"documento": dict(d), "paginas": [dict(p) for p in pages], "entidades": [dict(e) for e in ents]}


@app.get("/api/documento/{doc_id}/arquivo")
def arquivo(doc_id: int):
    with db.session() as con:
        d = con.execute("SELECT caminho, arquivo FROM documentos WHERE id=?", (doc_id,)).fetchone()
    if not d or not os.path.exists(d["caminho"]):
        raise HTTPException(404, "arquivo não encontrado")
    return FileResponse(d["caminho"], filename=d["arquivo"])


@app.get("/api/processo/{proc_id}")
def processo(proc_id: int):
    with db.session() as con:
        p = con.execute("SELECT * FROM processos WHERE id=?", (proc_id,)).fetchone()
        if not p:
            raise HTTPException(404)
        return {"processo": dict(p),
                "partes": [dict(x) for x in con.execute("SELECT nome, polo, tipo_pessoa, documento FROM partes WHERE processo_id=?", (proc_id,))],
                "profissionais": [dict(x) for x in con.execute("SELECT nome, papel, registro, polo FROM profissionais WHERE processo_id=?", (proc_id,))],
                "documentos": [dict(x) for x in con.execute("SELECT id, arquivo, tipo, data_documento, paginas, fase FROM documentos WHERE processo_id=? ORDER BY data_documento", (proc_id,))]}


# ---------------------------------------------------------------- indexação / upload / filtros salvos

class Indexar(BaseModel):
    pasta: str
    reindexar: bool = False


@app.post("/api/indexar")
def indexar(body: Indexar):
    try:
        return index_folder(body.pasta, reindex=body.reindexar, log=lambda *_: None)
    except FileNotFoundError:
        raise HTTPException(400, f"pasta não encontrada: {body.pasta}")


@app.post("/api/upload")
async def upload(arquivos: List[UploadFile] = File(...), numeroProcesso: Optional[str] = None):
    os.makedirs(UPLOAD_ROOT, exist_ok=True)
    dest = os.path.join(UPLOAD_ROOT, (numeroProcesso or datetime.now().strftime("%Y%m%d-%H%M%S")).replace("/", "_"))
    os.makedirs(dest, exist_ok=True)
    for up in arquivos:
        target = os.path.join(dest, os.path.basename(up.filename))
        with open(target, "wb") as fh:
            shutil.copyfileobj(up.file, fh)
        if target.lower().endswith(".zip"):
            with zipfile.ZipFile(target) as z:
                z.extractall(dest)
            os.remove(target)
    return index_folder(dest, log=lambda *_: None)


class FiltroSalvo(BaseModel):
    nome: str
    corpo: Dict[str, Any]


@app.get("/api/filtros")
def filtros():
    with db.session() as con:
        return [{"id": r["id"], "nome": r["nome"], "corpo": json.loads(r["corpo"]), "criado_em": r["criado_em"]} for r in con.execute("SELECT * FROM filtros_salvos ORDER BY id DESC")]


@app.post("/api/filtros")
def salvar_filtro(f: FiltroSalvo):
    with db.session() as con:
        cur = con.execute("INSERT INTO filtros_salvos (nome, corpo, criado_em) VALUES (?,?,?)", (f.nome, json.dumps(f.corpo, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")))
        return {"id": cur.lastrowid}


@app.delete("/api/filtros/{fid}")
def apagar_filtro(fid: int):
    with db.session() as con:
        con.execute("DELETE FROM filtros_salvos WHERE id=?", (fid,))
    return {"ok": True}


@app.get("/api/opcoes")
def opcoes():
    """Valores distintos para os selects do painel de filtros."""
    with db.session() as con:
        def dist(sql):
            return [r[0] for r in con.execute(sql) if r[0]]
        return {
            "tiposDocumento": dist("SELECT DISTINCT tipo FROM documentos ORDER BY 1"),
            "tribunais": dist("SELECT DISTINCT tribunal FROM processos ORDER BY 1"),
            "ufs": dist("SELECT DISTINCT uf FROM processos ORDER BY 1"),
            "classes": dist("SELECT DISTINCT classe FROM processos ORDER BY 1"),
            "assuntos": dist("SELECT DISTINCT assunto FROM processos ORDER BY 1"),
            "orgaosJulgadores": dist("SELECT DISTINCT orgao_julgador FROM processos ORDER BY 1"),
            "comarcas": dist("SELECT DISTINCT comarca FROM processos ORDER BY 1"),
            "desfechos": dist("SELECT DISTINCT desfecho FROM processos ORDER BY 1"),
            "status": ["Ativo", "Arquivado", "Suspenso"], "fases": ["Conhecimento", "Liquidação", "Execução"], "graus": ["1º grau", "2º grau"],
            "tiposEntidades": list(ENT_TIPOS),
        }


# ---------------------------------------------------------------- fontes de dados reais

class ImportNumero(BaseModel):
    numeros: List[str]


@app.post("/api/fontes/datajud/numero")
def datajud_numero(body: ImportNumero):
    """Consulta a API Pública do DataJud (CNJ) por número CNJ e grava no índice local."""
    encontrados, erros = [], []
    for n in body.numeros:
        n = n.strip()
        if not n:
            continue
        try:
            hits = datajud.buscar_por_numero(n)
            if not hits:
                erros.append(f"{n}: não encontrado no DataJud")
            encontrados.extend(hits)
        except Exception as e:  # noqa
            erros.append(f"{n}: {e}")
    stats = datajud.importar(encontrados, log=lambda *_: None) if encontrados else {"processos": 0, "atualizados": 0, "sigilosos": 0}
    return {**stats, "encontrados": len(encontrados), "erros": erros}


class ImportFiltro(BaseModel):
    tribunal: str
    classeCodigo: Optional[int] = None
    orgaoCodigo: Optional[int] = None
    assuntoCodigo: Optional[int] = None
    grau: Optional[str] = None
    dataInicio: Optional[str] = None
    dataFim: Optional[str] = None
    maximo: int = 200


@app.post("/api/fontes/datajud/filtro")
def datajud_filtro(body: ImportFiltro):
    """Varredura do DataJud por tribunal + classe/órgão/assunto/período (códigos das Tabelas Processuais Unificadas)."""
    try:
        fontes = list(datajud.buscar_filtrado(body.tribunal, body.classeCodigo, body.orgaoCodigo, body.assuntoCodigo,
                                              body.dataInicio, body.dataFim, body.grau, maximo=min(body.maximo, 2000)))
    except Exception as e:  # noqa
        raise HTTPException(502, str(e))
    stats = datajud.importar(fontes, log=lambda *_: None) if fontes else {"processos": 0, "atualizados": 0, "sigilosos": 0}
    return {**stats, "encontrados": len(fontes)}


@app.get("/api/fontes/status")
def fontes_status():
    return {"datajud": bool(os.environ.get("DATAJUD_API_KEY")), **privadas.disponiveis(),
            "pastaDocumentos": DOCS_ROOT, "tribunais": list(datajud.ALIASES_TRABALHISTA)}


class ImportPessoa(BaseModel):
    provedor: str   # judit | escavador
    tipo: str       # nome | cpf | cnpj | oab | numero
    chave: str
    maximo: int = 100


@app.post("/api/fontes/pessoa")
def fonte_pessoa(body: ImportPessoa):
    """Busca por pessoa/parte/advogado em provedor privado configurado no .env (dados pessoais: use com finalidade definida)."""
    try:
        if body.provedor == "judit":
            tipo = {"nome": "name", "cpf": "cpf", "cnpj": "cnpj", "oab": "oab", "numero": "lawsuit_cnj"}[body.tipo]
            itens = privadas.judit_buscar(tipo, body.chave)
        elif body.provedor == "escavador":
            tipo = {"nome": "nome", "cpf": "cpf_cnpj", "cnpj": "cpf_cnpj", "oab": "oab", "numero": "numero_cnj"}[body.tipo]
            itens = privadas.escavador_buscar(tipo, body.chave, maximo=body.maximo)
        else:
            raise HTTPException(400, "provedor deve ser judit ou escavador")
    except KeyError:
        raise HTTPException(400, "tipo inválido")
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    stats = privadas.importar(itens) if itens else {"processos": 0, "atualizados": 0}
    return {**stats, "encontrados": len(itens)}
