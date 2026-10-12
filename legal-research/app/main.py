"""API do Legal Research local (compatível, em espírito, com os endpoints observados na ferramenta de referência).

Desempenho: cache de consultas invalidado a cada gravação (db.VERSION), materialização dos acertos
em tabela temporária para facetas/jurimetria (uma única varredura do FTS por requisição) e
tarefas longas em segundo plano com progresso.
"""
import json
import os
import shutil
import time
import zipfile
from collections import OrderedDict
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config  # noqa: F401  (carrega .env)
from . import db, jobs
from .fontes import datajud, privadas
from .indexer import index_folder
from .query import ENT_TIPOS, ORDER, build_fts, doc_where, entity_where, process_where

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
DOCS_ROOT = os.path.abspath(os.environ.get("LR_DOCS", os.path.join(BASE, "data", "documentos")))
UPLOAD_ROOT = os.environ.get("LR_UPLOADS", os.path.join(BASE, "data", "uploads"))

app = FastAPI(title="Legal Research Local", version="1.1.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class Bloco(BaseModel):
    conteudo: Dict[str, Any] = {}


class Consulta(BaseModel):
    filtroGeral: Optional[Bloco] = None
    filtroPesquisaTextual: Optional[Bloco] = None


# ---------------------------------------------------------------- cache de consultas

_cache: "OrderedDict[str, Any]" = OrderedDict()
_cache_lock = Lock()
CACHE_MAX = 512


def cached(nome: str, chave: Any, fn):
    k = json.dumps([db.VERSION, nome, chave], sort_keys=True, default=str)
    with _cache_lock:
        if k in _cache:
            _cache.move_to_end(k)
            return _cache[k], True
    val = fn()
    with _cache_lock:
        _cache[k] = val
        if len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)
    return val, False


@app.on_event("startup")
def _startup():
    db.init_db()
    if os.environ.get("LR_AUTOINDEX", "1") == "1":
        pastas = [p for p in (DOCS_ROOT, UPLOAD_ROOT) if os.path.isdir(p)]
        if pastas:
            jobs.iniciar("indexacao", lambda pr: [index_folder(p, log=lambda *_: None, progress=pr) for p in pastas], "Indexação inicial das pastas de documentos")


@app.get("/", response_class=HTMLResponse)
def home():
    with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------- busca

def _build(q: Consulta):
    fg = (q.filtroGeral.conteudo if q.filtroGeral else {}) or {}
    ft = (q.filtroPesquisaTextual.conteudo if q.filtroPesquisaTextual else {}) or {}
    pw, pp = process_where(fg)
    dw, dp = doc_where(ft)
    trecho = (ft.get("trecho") or "").strip()
    adv = ft.get("buscaDocumentosAvancada") or {}
    fts, hl = build_fts(trecho, adv, modo_ia=bool(ft.get("modoIA")))
    ew, ep = entity_where(ft.get("tiposEntidades") or [], [trecho] if trecho else [])
    frm = _from_clause(fts, ew)
    params = ([fts] if fts else []) + ep + pp + dp
    where = f"{frm} AND ({pw}) AND ({dw})"
    return fg, ft, fts, hl, where, params


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


def _materializar(con, where: str, params: list):
    """Uma única passagem pelo FTS: acertos vão para uma tabela temporária usada por todas as agregações."""
    con.execute("DROP TABLE IF EXISTS temp.hits")
    try:
        con.execute(f"CREATE TEMP TABLE hits AS SELECT pg.id AS pagina_id, d.id AS documento_id, p.id AS processo_id {where}", params)
    except Exception as e:
        raise HTTPException(400, f"Expressão de busca inválida: {e}")
    con.execute("CREATE INDEX temp.hits_doc ON hits(documento_id)")
    con.execute("CREATE INDEX temp.hits_proc ON hits(processo_id)")


@app.post("/api/documento")
def buscar(q: Consulta, limite: int = Query(30, le=200), deslocamento: int = 0):
    t0 = time.perf_counter()
    fg, ft, fts, hl, where, params = _build(q)
    ordem = ORDER.get(ft.get("tipoOrdenacao") or "relevancia", ORDER["relevancia"]) if fts else "d.data_documento DESC, pg.numero"
    snippet = "snippet(paginas_fts, 0, '<mark>', '</mark>', ' … ', 28)" if fts else "substr(pg.texto, 1, 240)"
    rank = "bm25(paginas_fts)" if fts else "0"
    sql = (f"SELECT pg.id AS pagina_id, pg.numero AS pagina, d.id AS documento_id, d.arquivo, d.tipo, d.data_documento, d.paginas, d.fase AS fase_doc, "
           f"p.id AS processo_id, p.numero AS processo, p.tribunal, p.uf, p.orgao_julgador, p.classe, p.status, p.fase, {snippet} AS trecho, {rank} AS rank "
           f"{where} ORDER BY {ordem} LIMIT ? OFFSET ?")

    def run():
        with db.session() as con:
            try:
                rows = con.execute(sql, (*params, limite, deslocamento)).fetchall()
            except Exception as e:
                raise HTTPException(400, f"Expressão de busca inválida: {e}")
            tot, _ = cached("contagem", [q.model_dump(), fts], lambda: dict(con.execute(
                f"SELECT COUNT(*) AS n, COUNT(DISTINCT d.id) AS docs, COUNT(DISTINCT p.id) AS procs {where}", params).fetchone()))
            out, partes_cache = [], {}
            for r in rows:
                d = dict(r)
                pid = r["processo_id"]
                if pid not in partes_cache:
                    partes_cache[pid] = [dict(x) for x in con.execute("SELECT nome, polo, tipo_pessoa FROM partes WHERE processo_id=? ORDER BY polo LIMIT 6", (pid,))]
                d["partes"] = partes_cache[pid]
                out.append(d)
            return {"resultados": out, "totalTrechos": tot["n"], "totalDocumentos": tot["docs"], "totalProcessos": tot["procs"]}

    res, hit = cached("busca", [q.model_dump(), limite, deslocamento], run)
    return {**res, "destaques": hl, "limite": limite, "deslocamento": deslocamento, "tempoMs": round((time.perf_counter() - t0) * 1000, 1), "cache": hit}


@app.post("/api/documento/obterQuantidadeDeProcessos")
def quantidade(q: Consulta):
    fg, ft, fts, hl, where, params = _build(q)

    def run():
        with db.session() as con:
            r = con.execute(f"SELECT COUNT(DISTINCT d.id) AS docs, COUNT(DISTINCT p.id) AS procs {where}", params).fetchone()
            total = con.execute("SELECT COUNT(*) FROM processos").fetchone()[0]
            return {"processos": r["procs"], "documentos": r["docs"], "totalBase": total}
    return cached("qtd", q.model_dump(), run)[0]


FACETAS = {
    "tiposDocumento": "d.tipo", "tribunais": "p.tribunal", "ufs": "p.uf", "fases": "p.fase", "status": "p.status",
    "classes": "p.classe", "assuntos": "p.assunto", "orgaosJulgadores": "p.orgao_julgador", "graus": "p.grau",
    "fasesDocumento": "d.fase", "anosDocumento": "substr(d.data_documento,1,4)", "desfechos": "p.desfecho",
}
FLAGS = ("transito_julgado", "acordo_homologado", "bloqueio", "revelia", "sindicato", "acao_coletiva", "covid", "pf_polo_passivo", "sem_advogado_passivo")


@app.post("/api/documento/obterMenuLateral")
def menu_lateral(q: Consulta):
    t0 = time.perf_counter()
    fg, ft, fts, hl, where, params = _build(q)

    def run():
        out: Dict[str, Any] = {}
        with db.session() as con:
            _materializar(con, where, params)
            base = "FROM (SELECT DISTINCT documento_id, processo_id FROM hits) h JOIN documentos d ON d.id=h.documento_id JOIN processos p ON p.id=h.processo_id"
            for nome, col in FACETAS.items():
                rows = con.execute(f"SELECT {col} AS v, COUNT(*) AS n {base} WHERE {col} IS NOT NULL GROUP BY {col} ORDER BY n DESC LIMIT 40").fetchall()
                out[nome] = [{"valor": r["v"], "quantidade": r["n"]} for r in rows]
            out["entidades"] = {}
            for t in ENT_TIPOS:
                rows = con.execute("SELECT e.valor AS v, COUNT(DISTINCT e.documento_id) AS n FROM entidades e WHERE e.tipo=? AND e.documento_id IN (SELECT documento_id FROM hits) "
                                   "GROUP BY e.valor_norm ORDER BY n DESC LIMIT 25", (t,)).fetchall()
                out["entidades"][t] = [{"valor": r["v"], "quantidade": r["n"]} for r in rows]
            procs = "(SELECT DISTINCT processo_id FROM hits)"
            out["partes"] = [{"valor": r["v"], "quantidade": r["n"]} for r in con.execute(f"SELECT nome AS v, COUNT(DISTINCT processo_id) AS n FROM partes WHERE processo_id IN {procs} GROUP BY lower(nome) ORDER BY n DESC LIMIT 25")]
            out["advogados"] = [{"valor": r["v"], "quantidade": r["n"]} for r in con.execute(f"SELECT nome AS v, COUNT(DISTINCT processo_id) AS n FROM profissionais WHERE papel='advogado' AND processo_id IN {procs} GROUP BY lower(nome) ORDER BY n DESC LIMIT 25")]
            out["magistrados"] = [{"valor": r["v"], "quantidade": r["n"]} for r in con.execute(f"SELECT nome AS v, COUNT(DISTINCT processo_id) AS n FROM profissionais WHERE papel='magistrado' AND processo_id IN {procs} GROUP BY lower(nome) ORDER BY n DESC LIMIT 25")]
            sums = ", ".join(f"SUM(p.{f}) AS {f}" for f in FLAGS)
            r = con.execute(f"SELECT {sums} FROM processos p WHERE p.id IN {procs}").fetchone()
            out["marcadores"] = {f: r[f] or 0 for f in FLAGS}
        return out

    res, hit = cached("menu", q.model_dump(), run)
    return {**res, "tempoMs": round((time.perf_counter() - t0) * 1000, 1), "cache": hit}


@app.post("/api/jurimetria")
def jurimetria(q: Consulta):
    fg, ft, fts, hl, where, params = _build(q)

    def run():
        with db.session() as con:
            _materializar(con, where, params)
            base = "FROM processos p WHERE p.id IN (SELECT DISTINCT processo_id FROM hits)"
            g = con.execute(f"SELECT COUNT(*) n, AVG(valor_causa) vc, AVG(valor_condenacao) vcond, AVG(valor_acordo) vac, "
                            f"SUM(acordo_homologado) acordos, SUM(transito_julgado) transitados, SUM(revelia) revelias, SUM(bloqueio) bloqueios, "
                            f"AVG(julianday(COALESCE(data_encerramento, date('now'))) - julianday(data_ajuizamento)) dur {base}").fetchone()

            def grp(col):
                return [{"valor": r[0], "quantidade": r[1]} for r in con.execute(f"SELECT {col}, COUNT(*) {base} AND {col} IS NOT NULL GROUP BY {col} ORDER BY 2 DESC LIMIT 20")]
            return {
                "processos": g["n"], "valorMedioCausa": g["vc"], "valorMedioCondenacao": g["vcond"], "valorMedioAcordo": g["vac"],
                "taxaAcordo": (g["acordos"] or 0) / g["n"] if g["n"] else None, "transitados": g["transitados"], "revelias": g["revelias"], "bloqueios": g["bloqueios"],
                "duracaoMediaDias": g["dur"],
                "porTribunal": grp("tribunal"), "porUf": grp("uf"), "porFase": grp("fase"), "porStatus": grp("status"),
                "porDesfecho": grp("desfecho"), "porAno": grp("ano"), "porClasse": grp("classe"), "porAssunto": grp("assunto"), "porOrgao": grp("orgao_julgador"),
                "documentosPorTipo": [{"valor": r[0], "quantidade": r[1]} for r in con.execute("SELECT d.tipo, COUNT(*) FROM documentos d WHERE d.processo_id IN (SELECT DISTINCT processo_id FROM hits) GROUP BY d.tipo ORDER BY 2 DESC")],
            }
    return cached("juri", q.model_dump(), run)[0]


# ---------------------------------------------------------------- home (dashboards)

@app.post("/api/home/{painel}")
def painel_home(painel: str):
    def run():
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
    return cached("home", painel, run)[0]


# ---------------------------------------------------------------- autocomplete

AUTOCOMPLETE = {
    "parte": "SELECT DISTINCT nome FROM partes WHERE nome LIKE ? COLLATE NOCASE ORDER BY nome LIMIT 15",
    "advogado": "SELECT DISTINCT nome FROM profissionais WHERE papel='advogado' AND nome LIKE ? COLLATE NOCASE ORDER BY nome LIMIT 15",
    "magistrado": "SELECT DISTINCT nome FROM profissionais WHERE papel='magistrado' AND nome LIKE ? COLLATE NOCASE ORDER BY nome LIMIT 15",
    "orgaoJulgador": "SELECT DISTINCT orgao_julgador FROM processos WHERE orgao_julgador LIKE ? COLLATE NOCASE ORDER BY 1 LIMIT 15",
    "assunto": "SELECT DISTINCT assunto FROM processos WHERE assunto LIKE ? COLLATE NOCASE ORDER BY 1 LIMIT 15",
    "classe": "SELECT DISTINCT classe FROM processos WHERE classe LIKE ? COLLATE NOCASE ORDER BY 1 LIMIT 15",
    "tipoDocumento": "SELECT DISTINCT tipo FROM documentos WHERE tipo LIKE ? COLLATE NOCASE ORDER BY 1 LIMIT 15",
    "processo": "SELECT DISTINCT numero FROM processos WHERE numero LIKE ? ORDER BY 1 LIMIT 15",
}


@app.get("/api/autocomplete/{esfera}/{campo}")
def autocomplete(esfera: str, campo: str, q: str = ""):
    def run():
        with db.session() as con:
            if campo in ENT_TIPOS:
                rows = con.execute("SELECT DISTINCT valor FROM entidades WHERE tipo=? AND valor_norm LIKE ? ORDER BY valor LIMIT 15", (campo, f"%{q.lower()}%"))
            elif campo in AUTOCOMPLETE:
                # prefixo primeiro (usa índice), depois contém
                rows = list(con.execute(AUTOCOMPLETE[campo], (f"{q}%",)))
                if len(rows) < 15:
                    extra = con.execute(AUTOCOMPLETE[campo], (f"%{q}%",))
                    vis = {r[0] for r in rows}
                    rows += [r for r in extra if r[0] not in vis]
            else:
                raise HTTPException(404, "campo desconhecido")
            return [r[0] for r in rows if r[0]][:15]
    return cached("ac", [campo, q], run)[0]


# ---------------------------------------------------------------- documento / processo

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
        raise HTTPException(404, "arquivo não encontrado (registro importado de fonte externa, sem arquivo original)")
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


# ---------------------------------------------------------------- tarefas em segundo plano

@app.get("/api/tarefas")
def tarefas():
    return jobs.listar()


@app.get("/api/tarefas/{jid}")
def tarefa(jid: str):
    j = jobs.obter(jid)
    if not j:
        raise HTTPException(404)
    return j


# ---------------------------------------------------------------- indexação / upload / filtros salvos

class Indexar(BaseModel):
    pasta: str
    reindexar: bool = False


@app.post("/api/indexar")
def indexar(body: Indexar):
    if not os.path.isdir(body.pasta):
        raise HTTPException(400, f"pasta não encontrada: {body.pasta}")
    return jobs.iniciar("indexacao", lambda pr: index_folder(body.pasta, reindex=body.reindexar, log=lambda *_: None, progress=pr), f"Indexação de {body.pasta}")


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
    return jobs.iniciar("indexacao", lambda pr: index_folder(dest, log=lambda *_: None, progress=pr), f"Indexação de {len(arquivos)} arquivo(s) enviados")


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
    def run():
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
                "tiposEntidades": list(ENT_TIPOS), "versao": db.VERSION,
            }
    return cached("opcoes", None, run)[0]


# ---------------------------------------------------------------- fontes de dados reais

class ImportNumero(BaseModel):
    numeros: List[str]


@app.post("/api/fontes/datajud/numero")
def datajud_numero(body: ImportNumero):
    """Consulta a API Pública do DataJud (CNJ) por número CNJ, em paralelo, e grava no índice local (tarefa em segundo plano)."""
    numeros = [n.strip() for n in body.numeros if n.strip()]
    if not numeros:
        raise HTTPException(400, "informe ao menos um número")
    datajud.api_key()  # falha cedo se a chave não estiver configurada

    def run(pr):
        pr(0, len(numeros), "consultando DataJud…")
        fontes, erros = datajud.buscar_varios(numeros)
        pr(len(numeros), len(numeros), f"{len(fontes)} encontrado(s); gravando…")
        stats = datajud.importar(fontes, log=lambda *_: None) if fontes else {"processos": 0, "atualizados": 0, "sigilosos": 0}
        return {**stats, "encontrados": len(fontes), "erros": erros}
    return jobs.iniciar("datajud", run, f"DataJud por número ({len(numeros)})")


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
    """Varredura do DataJud por tribunal + filtros; grava em lotes conforme as páginas chegam (resultados aparecem durante a importação)."""
    datajud.api_key()
    maximo = min(body.maximo, 5000)

    def run(pr):
        it = datajud.buscar_filtrado(body.tribunal, body.classeCodigo, body.orgaoCodigo, body.assuntoCodigo,
                                     body.dataInicio, body.dataFim, body.grau, maximo=maximo)
        stats = datajud.importar(it, log=lambda *_: None, progress=pr, total=maximo)
        return {**stats, "encontrados": stats["processos"] + stats["atualizados"]}
    return jobs.iniciar("datajud", run, f"Varredura DataJud {body.tribunal} (até {maximo})")


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
    mapa = {"judit": {"nome": "name", "cpf": "cpf", "cnpj": "cnpj", "oab": "oab", "numero": "lawsuit_cnj"},
            "escavador": {"nome": "nome", "cpf": "cpf_cnpj", "cnpj": "cpf_cnpj", "oab": "oab", "numero": "numero_cnj"}}
    if body.provedor not in mapa:
        raise HTTPException(400, "provedor deve ser judit ou escavador")
    if body.tipo not in mapa[body.provedor]:
        raise HTTPException(400, "tipo inválido")
    if not privadas.disponiveis()[body.provedor]:
        raise HTTPException(400, f"chave do provedor {body.provedor} não configurada no .env")
    tipo = mapa[body.provedor][body.tipo]

    def run(pr):
        pr(0, 0, f"consultando {body.provedor}…")
        itens = privadas.judit_buscar(tipo, body.chave) if body.provedor == "judit" else privadas.escavador_buscar(tipo, body.chave, maximo=body.maximo)
        pr(len(itens), len(itens), "gravando…")
        stats = privadas.importar(itens) if itens else {"processos": 0, "atualizados": 0}
        return {**stats, "encontrados": len(itens)}
    return jobs.iniciar("pessoa", run, f"{body.provedor}: {body.tipo}")
