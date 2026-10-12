"""Conector à API Pública do DataJud (CNJ).

Documentação oficial: https://datajud-wiki.cnj.jus.br/api-publica/
Acesso/chave:          https://datajud-wiki.cnj.jus.br/api-publica/acesso/

A API é um Elasticsearch somente-leitura, com UM alias por tribunal
(ex.: api_publica_trt2) e autenticação por chave pública divulgada pelo CNJ.
A chave pode ser trocada a qualquer momento: copie o valor atual da wiki para
DATAJUD_API_KEY (arquivo .env). Se as consultas falharem com 401/403, atualize-a.

Campos devolvidos (metadados): numeroProcesso, tribunal, grau, classe{codigo,nome},
assuntos[{codigo,nome}], orgaoJulgador{codigo,nome,codigoMunicipioIBGE}, dataAjuizamento,
nivelSigilo, movimentos[{codigo,nome,dataHora,complementosTabelados[]}], sistema, formato.
NÃO há partes, advogados, valores nem inteiro teor.
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from .. import config  # noqa: F401  (carrega .env)
from .. import db
from ..entities import extract_entities, norm
from ..indexer import cnj_info

BASE_URL = os.environ.get("DATAJUD_BASE_URL", "https://api-publica.datajud.cnj.jus.br")
TIMEOUT = int(os.environ.get("DATAJUD_TIMEOUT", "60"))

ALIASES_TRABALHISTA = {f"TRT-{n}": f"api_publica_trt{n}" for n in range(1, 25)}
ALIASES_TRABALHISTA["TST"] = "api_publica_tst"

# Códigos TPU (Tabelas Processuais Unificadas do CNJ) usados para derivar situações.
# Além dos códigos, o nome do movimento é verificado por texto (os tribunais variam na codificação).
MOV_TRANSITO = {848}            # Trânsito em julgado
MOV_ACORDO = {466}              # Homologação de transação
MOV_ARQUIVAMENTO = {22, 246}    # Baixa definitiva / Arquivamento definitivo
MOV_SUSPENSAO = {264, 265, 272, 898}
MOV_EXECUCAO = {11010, 11011, 11385, 12731}
MOV_LIQUIDACAO = {11009}
MOV_BLOQUEIO = {11381}
MOV_REVELIA = {11796}


def api_key() -> str:
    k = os.environ.get("DATAJUD_API_KEY", "").strip()
    if not k:
        raise RuntimeError("DATAJUD_API_KEY não configurada. Copie a chave pública atual de "
                           "https://datajud-wiki.cnj.jus.br/api-publica/acesso/ para o arquivo .env")
    return k


def alias_for(numero: str, tribunal: Optional[str] = None) -> str:
    trib = tribunal or cnj_info(numero)["tribunal"]
    if not trib or trib not in ALIASES_TRABALHISTA:
        raise ValueError(f"Tribunal não suportado nesta esfera (Trabalhista): {trib or numero}")
    return ALIASES_TRABALHISTA[trib]


def _post(alias: str, body: Dict[str, Any]) -> Dict[str, Any]:
    req = urllib.request.Request(
        f"{BASE_URL}/{alias}/_search", data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"APIKey {api_key()}", "Content-Type": "application/json",
                 "User-Agent": "legal-research-local/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:400]
        raise RuntimeError(f"DataJud HTTP {e.code} em {alias}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"DataJud inacessível ({alias}): {e.reason}") from e


def buscar_por_numero(numero: str) -> List[Dict[str, Any]]:
    numero_limpo = re.sub(r"\D", "", numero)
    alias = alias_for(formatar(numero_limpo))
    res = _post(alias, {"query": {"match": {"numeroProcesso": numero_limpo}}, "size": 10})
    return [h["_source"] for h in res.get("hits", {}).get("hits", [])]


def buscar_varios(numeros: List[str], workers: int = 8):
    """Consulta vários números em paralelo. Retorna (fontes, erros)."""
    fontes, erros = [], []

    def um(n):
        try:
            hits = buscar_por_numero(n)
            return n, hits, None
        except Exception as e:  # noqa
            return n, [], str(e)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for n, hits, err in pool.map(um, [x.strip() for x in numeros if x.strip()]):
            if err:
                erros.append(f"{n}: {err}")
            elif not hits:
                erros.append(f"{n}: não encontrado no DataJud")
            fontes.extend(hits)
    return fontes, erros


def buscar_filtrado(tribunal: str, classe_codigo: Optional[int] = None, orgao_codigo: Optional[int] = None,
                    assunto_codigo: Optional[int] = None, data_inicio: Optional[str] = None, data_fim: Optional[str] = None,
                    grau: Optional[str] = None, tamanho: int = 100, maximo: int = 500) -> Iterator[Dict[str, Any]]:
    """Varredura paginada (search_after) por tribunal com filtros de classe/órgão/assunto/período."""
    alias = ALIASES_TRABALHISTA.get(tribunal)
    if not alias:
        raise ValueError(f"tribunal inválido: {tribunal}")
    must: List[Dict[str, Any]] = []
    if classe_codigo:
        must.append({"match": {"classe.codigo": int(classe_codigo)}})
    if orgao_codigo:
        must.append({"match": {"orgaoJulgador.codigo": int(orgao_codigo)}})
    if assunto_codigo:
        must.append({"match": {"assuntos.codigo": int(assunto_codigo)}})
    if grau:
        must.append({"match": {"grau": grau}})
    if data_inicio or data_fim:
        rng: Dict[str, str] = {}
        if data_inicio:
            rng["gte"] = _iso_datajud(data_inicio)
        if data_fim:
            rng["lte"] = _iso_datajud(data_fim, fim=True)
        must.append({"range": {"dataAjuizamento": rng}})
    query = {"bool": {"must": must}} if must else {"match_all": {}}
    body: Dict[str, Any] = {"query": query, "size": min(tamanho, 10000), "sort": [{"@timestamp": {"order": "asc"}}]}
    total = 0
    while total < maximo:
        res = _post(alias, body)
        hits = res.get("hits", {}).get("hits", [])
        if not hits:
            break
        for h in hits:
            yield h["_source"]
            total += 1
            if total >= maximo:
                return
        body["search_after"] = hits[-1].get("sort")
        if not body["search_after"]:
            break


def _iso_datajud(d: str, fim: bool = False) -> str:
    d = d.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return d + ("T23:59:59.000Z" if fim else "T00:00:00.000Z")
    return d


def formatar(num: str) -> str:
    num = re.sub(r"\D", "", num)
    if len(num) != 20:
        return num
    return f"{num[:7]}-{num[7:9]}.{num[9:13]}.{num[13]}.{num[14:16]}.{num[16:]}"


def _dt(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


def _render(src: Dict[str, Any]) -> List[str]:
    """Transforma o JSON do DataJud em texto por 'página', para busca textual e extração de entidades."""
    numero = formatar(str(src.get("numeroProcesso", "")))
    classe = (src.get("classe") or {}).get("nome", "")
    org = (src.get("orgaoJulgador") or {}).get("nome", "")
    assuntos = ", ".join(a.get("nome", "") for a in src.get("assuntos") or [] if a)
    head = [f"Processo nº {numero}",
            f"Tribunal: {src.get('tribunal', '')}  Grau: {src.get('grau', '')}  Sistema: {(src.get('sistema') or {}).get('nome', '')}",
            f"Classe: {classe}", f"Assuntos: {assuntos}", f"Órgão julgador: {org}",
            f"Data de ajuizamento: {_dt(src.get('dataAjuizamento')) or ''}", f"Nível de sigilo: {src.get('nivelSigilo', 0)}",
            "", "MOVIMENTAÇÕES PROCESSUAIS (fonte: DataJud/CNJ)"]
    movs = sorted(src.get("movimentos") or [], key=lambda m: m.get("dataHora") or "")
    linhas = []
    for m in movs:
        comp = "; ".join(f"{c.get('nome', '')}: {c.get('descricao', '')}" for c in m.get("complementosTabelados") or [] if c)
        linhas.append(f"{_dt(m.get('dataHora')) or ''} — [{m.get('codigo', '')}] {m.get('nome', '')}" + (f" ({comp})" if comp else ""))
    pages, cur = [], "\n".join(head) + "\n"
    for ln in linhas:
        if len(cur) > 3500:
            pages.append(cur)
            cur = f"Processo nº {numero} (continuação)\n"
        cur += ln + "\n"
    pages.append(cur)
    return pages


def _derivar(src: Dict[str, Any]) -> Dict[str, Any]:
    movs = src.get("movimentos") or []
    codigos = {int(m.get("codigo")) for m in movs if str(m.get("codigo", "")).isdigit()}
    nomes = norm(" ".join(m.get("nome", "") for m in movs))
    status = "Ativo"
    if codigos & MOV_ARQUIVAMENTO or "arquivamento definitivo" in nomes or "baixa definitiva" in nomes:
        status = "Arquivado"
    elif codigos & MOV_SUSPENSAO or "suspens" in nomes or "sobrestamento" in nomes:
        status = "Suspenso"
    fase = "Conhecimento"
    if codigos & MOV_EXECUCAO or "execucao" in nomes or "cumprimento de sentenca" in nomes:
        fase = "Execução"
    elif codigos & MOV_LIQUIDACAO or "liquidacao" in nomes:
        fase = "Liquidação"
    desfecho = None
    if codigos & MOV_ACORDO or "homologacao de transacao" in nomes or "homologacao de acordo" in nomes:
        desfecho = "Acordo"
    elif "procedente em parte" in nomes or "procedencia em parte" in nomes:
        desfecho = "Procedente em parte"
    elif "improcedencia" in nomes or "improcedente" in nomes:
        desfecho = "Improcedente"
    elif "procedencia" in nomes or "procedente" in nomes:
        desfecho = "Procedente"
    elif "extincao" in nomes and "sem resolucao" in nomes:
        desfecho = "Extinto sem resolução do mérito"
    ultimo = max((m.get("dataHora") or "" for m in movs), default=None)
    return {
        "status": status, "fase": fase, "desfecho": desfecho,
        "transito_julgado": int(bool(codigos & MOV_TRANSITO) or "transito em julgado" in nomes or "transitado em julgado" in nomes),
        "acordo_homologado": int(desfecho == "Acordo"),
        "bloqueio": int(bool(codigos & MOV_BLOQUEIO) or "bloqueio" in nomes or "sisbajud" in nomes or "bacenjud" in nomes),
        "revelia": int(bool(codigos & MOV_REVELIA) or "revelia" in nomes),
        "data_encerramento": _dt(ultimo) if status == "Arquivado" else None,
    }


def importar(fontes, log=print, progress=None, total: Optional[int] = None) -> Dict[str, Any]:
    """Grava processos do DataJud no banco local como processo + documento 'Movimentações (DataJud)'.
    Aceita lista ou iterador (varredura paginada): grava em lotes, com commit a cada 50."""
    db.init_db()
    stats = {"processos": 0, "atualizados": 0, "sigilosos": 0}
    with db.session() as con:
        for i, src in enumerate(fontes, 1):
            if i % 50 == 0:
                con.commit()
            if progress:
                progress(i, total, str(src.get("numeroProcesso", "")))
            numero = formatar(str(src.get("numeroProcesso", "")))
            if not numero:
                continue
            if int(src.get("nivelSigilo") or 0) > 0:
                stats["sigilosos"] += 1  # a própria API já restringe os dados; só contabilizamos
            info = cnj_info(numero)
            der = _derivar(src)
            campos = {
                "tribunal": src.get("tribunal") or info["tribunal"], "uf": info["uf"], "grau": src.get("grau") or info["grau"], "ano": info["ano"],
                "orgao_julgador": (src.get("orgaoJulgador") or {}).get("nome"), "classe": (src.get("classe") or {}).get("nome"),
                "assunto": "; ".join(a.get("nome", "") for a in src.get("assuntos") or [] if a) or None,
                "data_ajuizamento": _dt(src.get("dataAjuizamento")), "pasta": "datajud", **der,
            }
            row = con.execute("SELECT id FROM processos WHERE numero=?", (numero,)).fetchone()
            if row:
                pid = row["id"]
                con.execute("UPDATE processos SET " + ", ".join(f"{k}=?" for k in campos) + " WHERE id=?", (*campos.values(), pid))
                stats["atualizados"] += 1
            else:
                cur = con.execute(f"INSERT INTO processos (numero, {', '.join(campos)}) VALUES (?, {', '.join('?' for _ in campos)})", (numero, *campos.values()))
                pid = cur.lastrowid
                stats["processos"] += 1
            caminho = f"datajud://{numero}"
            old = con.execute("SELECT id FROM documentos WHERE caminho=?", (caminho,)).fetchone()
            if old:
                con.execute("DELETE FROM documentos WHERE id=?", (old["id"],))
            pages = _render(src)
            cur = con.execute(
                "INSERT INTO documentos (processo_id, arquivo, caminho, tipo, data_documento, fase, paginas, tamanho, hash, indexado_em) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (pid, f"{numero} - movimentacoes.txt", caminho, "Movimentações (DataJud)", der["data_encerramento"] or _dt(src.get("dataAjuizamento")),
                 der["fase"], len(pages), sum(len(p) for p in pages), None, datetime.now().isoformat(timespec="seconds")))
            did = cur.lastrowid
            for i, txt in enumerate(pages, 1):
                con.execute("INSERT INTO paginas (documento_id, numero, texto) VALUES (?,?,?)", (did, i, txt))
                for t, vals in extract_entities(txt).items():
                    for v in vals:
                        con.execute("INSERT INTO entidades (documento_id, pagina, tipo, valor, valor_norm) VALUES (?,?,?,?,?)", (did, i, t, v, norm(v)))
            log(f"  + {numero} ({len(src.get('movimentos') or [])} movimentos)")
    db.bump()
    return stats
