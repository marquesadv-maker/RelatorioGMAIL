"""Indexador: varre uma pasta de processos e alimenta o banco.

Estrutura esperada (flexível):
  <raiz>/<pasta do processo>/*.pdf|*.docx|*.txt
  <raiz>/<pasta do processo>/processo.json   (opcional: metadados)

O número CNJ é lido do nome da pasta, do nome do arquivo ou do texto do documento.
"""
import hashlib
import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

from . import db
from .entities import (classify_doc, classify_fase, extract_entities, find_cnj, mask_doc, norm, parse_date, CNPJ_RE, CPF_RE)
from .extract import extract_pages

EXTS = {".pdf", ".docx", ".txt", ".md", ".html", ".htm"}

# TRT -> UF principal (regiões com mais de um estado usam o estado-sede)
TRT_UF = {1: "RJ", 2: "SP", 3: "MG", 4: "RS", 5: "BA", 6: "PE", 7: "CE", 8: "PA", 9: "PR", 10: "DF", 11: "AM", 12: "SC",
          13: "PB", 14: "RO", 15: "SP", 16: "MA", 17: "ES", 18: "GO", 19: "AL", 20: "SE", 21: "RN", 22: "PI", 23: "MT", 24: "MS"}
SEGMENTO = {1: "STF", 2: "CNJ", 3: "STJ", 4: "TRF", 5: "TRT", 6: "TRE", 7: "STM", 8: "TJ", 9: "TJM"}


def cnj_info(numero: str) -> Dict:
    m = re.match(r"(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})", numero)
    if not m:
        return {"tribunal": None, "uf": None, "ano": None, "grau": None}
    ano, j, tr, oooo = int(m.group(3)), int(m.group(4)), int(m.group(5)), m.group(6)
    seg = SEGMENTO.get(j, "")
    tribunal = f"{seg}{tr}" if seg in ("TRT", "TRF", "TRE", "TJ") else seg
    if seg == "TRT":
        tribunal = f"TRT-{tr}"
    uf = TRT_UF.get(tr) if seg == "TRT" else None
    grau = "2º grau" if oooo == "0000" else "1º grau"
    return {"tribunal": tribunal, "uf": uf, "ano": ano, "grau": grau}


def file_hash(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_meta(folder: str) -> Dict:
    p = os.path.join(folder, "processo.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as e:  # noqa
            print(f"[aviso] processo.json inválido em {folder}: {e}")
    return {}


def guess_number(folder: str, filename: str, text: str) -> Optional[str]:
    for src in (os.path.basename(folder), filename, text[:5000]):
        nums = find_cnj(src)
        if nums:
            return nums[0]
    return None


def guess_parties(text: str) -> List[Dict]:
    """Heurística simples para polo ativo/passivo a partir de 'Reclamante:'/'Reclamada:'."""
    out = []
    for polo, pat in (("ativo", r"Reclamante\s*[:\-–]\s*([^\n,;]{4,90})"), ("passivo", r"Reclamad[oa]s?\s*[:\-–]\s*([^\n,;]{4,90})")):
        for m in re.finditer(pat, text):
            nome = re.sub(r"\s+", " ", m.group(1)).strip(" .")
            if nome and nome.upper() == nome or len(nome.split()) >= 2:
                tp = "PJ" if re.search(r"LTDA|S\.?/?A|EIRELI|\bME\b|EPP", nome, re.I) else "PF"
                out.append({"nome": nome.title() if nome.isupper() else nome, "polo": polo, "tipo_pessoa": tp})
    seen, uniq = set(), []
    for p in out:
        k = (norm(p["nome"]), p["polo"])
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


def index_folder(root: str, reindex: bool = False, log=print) -> Dict:
    db.init_db()
    stats = {"processos": 0, "documentos": 0, "paginas": 0, "ignorados": 0, "erros": []}
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise FileNotFoundError(root)
    with db.session() as con:
        for folder, _dirs, files in os.walk(root):
            docs = sorted(f for f in files if os.path.splitext(f)[1].lower() in EXTS)
            if not docs:
                continue
            meta = load_meta(folder)
            for f in docs:
                path = os.path.join(folder, f)
                try:
                    n = _index_file(con, path, folder, meta, reindex, stats)
                    if n:
                        log(f"  + {f} ({n} págs.)")
                except Exception as e:  # noqa
                    stats["erros"].append(f"{path}: {e}")
                    log(f"  ! erro em {f}: {e}")
        stats["processos"] = con.execute("SELECT COUNT(*) FROM processos").fetchone()[0]
    return stats


def _upsert_processo(con, numero: str, meta: Dict, folder: str, text: str) -> int:
    info = cnj_info(numero)
    row = con.execute("SELECT id FROM processos WHERE numero=?", (numero,)).fetchone()
    partes = meta.get("partes") or guess_parties(text)
    pf_passivo = int(any(p.get("polo") == "passivo" and p.get("tipo_pessoa") == "PF" for p in partes))
    sindicato = int(any("sindicato" in norm(p.get("nome", "")) for p in partes if p.get("polo") == "ativo"))
    campos = {
        "tribunal": meta.get("tribunal") or info["tribunal"], "uf": meta.get("uf") or info["uf"], "grau": meta.get("grau") or info["grau"],
        "ano": info["ano"], "orgao_julgador": meta.get("orgao_julgador"), "orgao_origem": meta.get("orgao_origem"), "comarca": meta.get("comarca"),
        "classe": meta.get("classe") or "Ação Trabalhista - Rito Ordinário", "assunto": meta.get("assunto"), "fase": meta.get("fase"),
        "status": meta.get("status") or "Ativo", "desfecho": meta.get("desfecho"),
        "valor_causa": meta.get("valor_causa"), "valor_condenacao": meta.get("valor_condenacao"), "valor_acordo": meta.get("valor_acordo"),
        "valor_liquidacao": meta.get("valor_liquidacao"), "custas": meta.get("custas"),
        "data_ajuizamento": meta.get("data_ajuizamento"), "data_encerramento": meta.get("data_encerramento"),
        "transito_julgado": int(bool(meta.get("transito_julgado"))), "acordo_homologado": int(bool(meta.get("acordo_homologado"))),
        "bloqueio": int(bool(meta.get("bloqueio"))), "revelia": int(bool(meta.get("revelia"))),
        "sindicato": int(bool(meta.get("sindicato", sindicato))), "acao_coletiva": int(bool(meta.get("acao_coletiva"))),
        "covid": int(bool(meta.get("covid")) or bool(re.search(r"covid|pandemia|coronav[ií]rus", text, re.I))),
        "pf_polo_passivo": int(bool(meta.get("pf_polo_passivo", pf_passivo))), "sem_advogado_passivo": int(bool(meta.get("sem_advogado_passivo"))),
        "pasta": folder,
    }
    if row:
        pid = row["id"]
        sets = ", ".join(f"{k}=COALESCE(?, {k})" for k in campos)
        con.execute(f"UPDATE processos SET {sets} WHERE id=?", (*campos.values(), pid))
    else:
        cols = ", ".join(campos)
        qs = ", ".join("?" for _ in campos)
        cur = con.execute(f"INSERT INTO processos (numero, {cols}) VALUES (?, {qs})", (numero, *campos.values()))
        pid = cur.lastrowid
    # partes e profissionais (substitui para refletir metadados/heurística atual)
    if partes:
        con.execute("DELETE FROM partes WHERE processo_id=?", (pid,))
        for p in partes:
            con.execute("INSERT INTO partes (processo_id, nome, polo, tipo_pessoa, documento, atividade_economica) VALUES (?,?,?,?,?,?)",
                        (pid, p.get("nome"), p.get("polo"), p.get("tipo_pessoa"), mask_doc(p["documento"]) if p.get("documento") else None, p.get("atividade_economica")))
    profs = []
    for a in meta.get("advogados", []):
        profs.append((a.get("nome"), "advogado", a.get("oab"), a.get("polo")))
    for m in meta.get("magistrados", []):
        profs.append((m if isinstance(m, str) else m.get("nome"), "magistrado", None, None))
    if profs:
        con.execute("DELETE FROM profissionais WHERE processo_id=?", (pid,))
        for nome, papel, reg, polo in profs:
            con.execute("INSERT INTO profissionais (processo_id, nome, papel, registro, polo) VALUES (?,?,?,?,?)", (pid, nome, papel, reg, polo))
    return pid


def _index_file(con, path: str, folder: str, meta: Dict, reindex: bool, stats: Dict) -> int:
    h = file_hash(path)
    existing = con.execute("SELECT id, hash FROM documentos WHERE caminho=?", (path,)).fetchone()
    if existing and existing["hash"] == h and not reindex:
        stats["ignorados"] += 1
        return 0
    pages = extract_pages(path)
    full = "\n".join(pages)
    numero = guess_number(folder, os.path.basename(path), full) or meta.get("numero")
    if not numero:
        numero = "SEM-NUMERO/" + os.path.basename(folder)
    pid = _upsert_processo(con, numero, meta, folder, full)
    if existing:
        con.execute("DELETE FROM documentos WHERE id=?", (existing["id"],))
    fname = os.path.basename(path)
    tipo = classify_doc(fname, pages[0] if pages else "")
    fase = classify_fase(tipo, full)
    data_doc = parse_date(fname) or parse_date(full[-2500:]) or parse_date(full[:2500]) or datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d")
    cur = con.execute(
        "INSERT INTO documentos (processo_id, arquivo, caminho, tipo, data_documento, fase, paginas, tamanho, hash, indexado_em) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (pid, fname, path, tipo, data_doc, fase, len(pages), os.path.getsize(path), h, datetime.now().isoformat(timespec="seconds")))
    did = cur.lastrowid
    for i, txt in enumerate(pages, start=1):
        # LGPD: CPF mascarado no índice (o original permanece apenas no arquivo)
        txt_idx = CPF_RE.sub(lambda m: mask_doc(m.group(0)), txt)
        con.execute("INSERT INTO paginas (documento_id, numero, texto) VALUES (?,?,?)", (did, i, txt_idx))
        for tipo_ent, valores in extract_entities(txt).items():
            for v in valores:
                con.execute("INSERT INTO entidades (documento_id, pagina, tipo, valor, valor_norm) VALUES (?,?,?,?,?)", (did, i, tipo_ent, v, norm(v)))
    # advogados extraídos do texto viram profissionais do processo se não vieram dos metadados
    if not meta.get("advogados"):
        for r in con.execute("SELECT DISTINCT valor FROM entidades WHERE documento_id=? AND tipo='advogados'", (did,)):
            nome, _, oab = r["valor"].partition(" (OAB/")
            if not con.execute("SELECT 1 FROM profissionais WHERE processo_id=? AND papel='advogado' AND nome=?", (pid, nome)).fetchone():
                con.execute("INSERT INTO profissionais (processo_id, nome, papel, registro) VALUES (?,?,?,?)", (pid, nome, "advogado", oab.rstrip(")")))
    if not meta.get("magistrados"):
        for r in con.execute("SELECT DISTINCT valor FROM entidades WHERE documento_id=? AND tipo='juizes'", (did,)):
            if not con.execute("SELECT 1 FROM profissionais WHERE processo_id=? AND papel='magistrado' AND nome=?", (pid, r["valor"])).fetchone():
                con.execute("INSERT INTO profissionais (processo_id, nome, papel) VALUES (?,?,?)", (pid, r["valor"], "magistrado"))
    if not meta.get("orgao_julgador"):
        v = con.execute("SELECT valor FROM entidades WHERE documento_id=? AND tipo='varas' LIMIT 1", (did,)).fetchone()
        if v:
            con.execute("UPDATE processos SET orgao_julgador=COALESCE(orgao_julgador, ?) WHERE id=?", (v["valor"], pid))
    if not meta.get("fase"):
        con.execute("UPDATE processos SET fase=? WHERE id=? AND (fase IS NULL OR ?='Execução')", (fase, pid, fase))
    stats["documentos"] += 1
    stats["paginas"] += len(pages)
    return len(pages)


if __name__ == "__main__":
    import sys
    r = index_folder(sys.argv[1] if len(sys.argv) > 1 else "samples", reindex="--reindex" in sys.argv)
    print(json.dumps(r, ensure_ascii=False, indent=2))
