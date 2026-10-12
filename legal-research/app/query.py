"""Construção da consulta: filtro geral (processo) + pesquisa textual (FTS5) + facetas + jurimetria."""
import re
from typing import Any, Dict, List, Optional, Tuple

from .entities import norm

ENT_TIPOS = ("pessoas", "organizacoes", "juizes", "varas", "tribunais", "fundamentos", "funcoes", "advogados")

SINONIMOS = {  # modo "I.A. local": expansão simples de termos jurídicos
    "horas extras": ["hora extra", "sobrejornada", "jornada extraordinária", "labor extraordinário"],
    "justa causa": ["despedida por justa causa", "dispensa motivada", "art. 482"],
    "dano moral": ["danos morais", "indenização por dano moral", "abalo moral"],
    "assedio moral": ["assédio moral", "assedio", "humilhação", "constrangimento"],
    "vinculo": ["vínculo empregatício", "reconhecimento de vínculo", "relação de emprego"],
    "acidente": ["acidente de trabalho", "acidente do trabalho", "doença ocupacional", "nexo causal"],
    "intervalo": ["intervalo intrajornada", "art. 71", "intervalo para refeição"],
    "equiparacao": ["equiparação salarial", "art. 461", "paradigma"],
    "adicional": ["adicional de insalubridade", "adicional de periculosidade", "adicional noturno"],
    "revelia": ["revel", "confissão ficta", "art. 844"],
    "acordo": ["conciliação", "transação", "acordo homologado", "homologação"],
    "rescisao": ["rescisão indireta", "verbas rescisórias", "art. 483"],
}


def _fts_term(t: str) -> str:
    t = t.replace('"', " ").strip()
    if not t:
        return ""
    return '"' + t + '"'


def build_fts(trecho: str, adv: Dict[str, Any], modo_ia: bool = False) -> Tuple[str, List[str]]:
    """Retorna (expressão MATCH do FTS5, lista de termos para destaque)."""
    parts, hl = [], []
    todas = (adv.get("todasPalavras") or "").strip()
    frase = (adv.get("fraseExata") or "").strip()
    alguma = (adv.get("aoMenosUma") or "").strip()
    nenhuma = (adv.get("nenhumaPalavra") or "").strip()
    lei = (adv.get("numeroLei") or "").strip()
    ano_lei = (adv.get("anoLei") or "").strip()

    base_words = [w for w in re.split(r"\s+", trecho.strip()) if w] if trecho else []
    if trecho and (trecho.startswith('"') and trecho.endswith('"')):
        parts.append(_fts_term(trecho.strip('"')))
        hl.append(trecho.strip('"'))
    elif base_words:
        if modo_ia:
            key = norm(trecho)
            alts = [trecho] + [s for k, v in SINONIMOS.items() if k in key or key in k for s in v]
            parts.append("(" + " OR ".join(_fts_term(a) for a in alts) + ")")
            hl.extend(alts)
        else:
            parts.append(" AND ".join(_fts_term(w) + "*" if len(w) > 3 else _fts_term(w) for w in base_words))
            hl.extend(base_words)
    if todas:
        ws = re.split(r"\s+", todas)
        parts.append(" AND ".join(_fts_term(w) for w in ws))
        hl.extend(ws)
    if frase:
        parts.append(_fts_term(frase))
        hl.append(frase)
    if alguma:
        ws = re.split(r"\s+", alguma)
        parts.append("(" + " OR ".join(_fts_term(w) for w in ws) + ")")
        hl.extend(ws)
    if lei:
        num = re.sub(r"[^\d]", "", lei)
        variants = {lei, num}
        if len(num) > 3:
            variants.add(f"{num[:-3]}.{num[-3:]}")
        alt = " OR ".join(_fts_term(f"lei {v}") + " OR " + _fts_term(f"lei nº {v}") + " OR " + _fts_term(f"lei n {v}") for v in variants)
        if ano_lei:
            alt += " OR " + " OR ".join(_fts_term(f"{v}/{ano_lei}") for v in variants)
        parts.append("(" + alt + ")")
        hl.append(lei)
    expr = " AND ".join(p for p in parts if p)
    if nenhuma:
        ws = re.split(r"\s+", nenhuma)
        if expr:
            expr = "(" + expr + ") NOT (" + " OR ".join(_fts_term(w) for w in ws) + ")"
    return expr, [h for h in hl if h]


def _in(col: str, values: List[str], params: list) -> str:
    vals = [v for v in (values or []) if v not in (None, "")]
    if not vals:
        return ""
    params.extend(vals)
    return f"{col} IN ({','.join('?' for _ in vals)})"


def _between(col: str, faixa: Optional[Dict], params: list) -> str:
    if not faixa:
        return ""
    conds = []
    if faixa.get("min") not in (None, ""):
        conds.append(f"{col} >= ?")
        params.append(faixa["min"])
    if faixa.get("max") not in (None, ""):
        conds.append(f"{col} <= ?")
        params.append(faixa["max"])
    return " AND ".join(conds)


def process_where(fg: Dict[str, Any]) -> Tuple[str, list]:
    """WHERE sobre a tabela processos p (filtroGeral.conteudo)."""
    fg = fg or {}
    params: list = []
    conds = [
        _in("p.uf", fg.get("ufs"), params),
        _in("p.tribunal", fg.get("tribunais"), params),
        _in("p.classe", fg.get("classes"), params),
        _in("p.assunto", fg.get("assuntos"), params),
        _in("p.fase", fg.get("fases"), params),
        _in("p.status", fg.get("status"), params),
        _in("p.desfecho", fg.get("desfechos"), params),
        _in("p.orgao_julgador", fg.get("orgaosJulgadores"), params),
        _in("p.orgao_origem", fg.get("orgaosOrigem"), params),
        _in("p.comarca", fg.get("comarcas"), params),
        _in("p.grau", fg.get("graus"), params),
        _between("p.valor_causa", fg.get("faixaValorCausa"), params),
        _between("p.valor_condenacao", fg.get("faixaValorCondenacao"), params),
        _between("p.valor_acordo", fg.get("faixaValorAcordo"), params),
        _between("p.valor_liquidacao", fg.get("faixaValorLiquidacao"), params),
        _between("p.custas", fg.get("faixaCustas"), params),
        _between("p.data_ajuizamento", fg.get("periodo"), params),
        _between("p.ano", fg.get("faixaAno"), params),
    ]
    for flag in ("transito_julgado", "acordo_homologado", "bloqueio", "revelia", "sindicato", "acao_coletiva", "covid", "pf_polo_passivo", "sem_advogado_passivo"):
        v = fg.get(flag)
        if v in (True, 1, "1", "true", "sim"):
            conds.append(f"p.{flag}=1")
        elif v in (False, 0, "0", "false", "nao", "não"):
            conds.append(f"p.{flag}=0")
    if fg.get("filtrarValoresAnomalos"):
        conds.append("(p.valor_causa IS NULL OR p.valor_causa BETWEEN 100 AND 50000000)")
    for nome_list, sql in (
        (fg.get("partes"), "EXISTS (SELECT 1 FROM partes x WHERE x.processo_id=p.id AND lower(x.nome) LIKE ?)"),
        (fg.get("advogados"), "EXISTS (SELECT 1 FROM profissionais x WHERE x.processo_id=p.id AND x.papel='advogado' AND lower(x.nome) LIKE ?)"),
        (fg.get("magistrados"), "EXISTS (SELECT 1 FROM profissionais x WHERE x.processo_id=p.id AND x.papel='magistrado' AND lower(x.nome) LIKE ?)"),
        (fg.get("cnpjs"), "EXISTS (SELECT 1 FROM partes x WHERE x.processo_id=p.id AND x.documento LIKE ?)"),
        (fg.get("atividadesEconomicas"), "EXISTS (SELECT 1 FROM partes x WHERE x.processo_id=p.id AND lower(x.atividade_economica) LIKE ?)"),
    ):
        vals = [v for v in (nome_list or []) if v]
        if vals:
            conds.append("(" + " OR ".join(sql for _ in vals) + ")")
            params.extend(f"%{v.lower()}%" for v in vals)
    if fg.get("numeroProcesso"):
        conds.append("p.numero LIKE ?")
        params.append(f"%{fg['numeroProcesso']}%")
    where = " AND ".join(c for c in conds if c)
    return (where or "1=1"), params


def doc_where(ft: Dict[str, Any]) -> Tuple[str, list]:
    """WHERE sobre documentos d (tipo, data, fase)."""
    ft = ft or {}
    params: list = []
    conds = [
        _in("d.tipo", ft.get("tiposDocumento"), params),
        _in("d.fase", ft.get("fasesDocumento"), params),
        _between("d.data_documento", ft.get("periodoDataDocumento"), params),
    ]
    where = " AND ".join(c for c in conds if c)
    return (where or "1=1"), params


def entity_where(tipos: List[str], termos: List[str]) -> Tuple[str, list]:
    """Restringe a páginas cujo texto contém o termo como entidade de um dos tipos escolhidos."""
    tipos = [t for t in (tipos or []) if t in ENT_TIPOS]
    termos = [norm(t) for t in termos if t]
    if not tipos or not termos:
        return "", []
    params: list = list(tipos)
    like = " OR ".join("e.valor_norm LIKE ?" for _ in termos)
    params.extend(f"%{t}%" for t in termos)
    sql = f"EXISTS (SELECT 1 FROM entidades e WHERE e.documento_id=d.id AND e.pagina=pg.numero AND e.tipo IN ({','.join('?' for _ in tipos)}) AND ({like}))"
    return sql, params


ORDER = {
    "relevancia": "rank, d.data_documento DESC",
    "dataDesc": "d.data_documento DESC, rank",
    "dataAsc": "d.data_documento ASC, rank",
    "processo": "p.numero, d.data_documento, pg.numero",
}
