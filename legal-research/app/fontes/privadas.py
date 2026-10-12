"""Conectores OPCIONAIS a provedores privados para busca por pessoa (nome, CPF, CNPJ, OAB).

O DataJud público não expõe partes nem advogados. Para essa necessidade, o escritório pode
contratar um provedor e informar a chave no .env. Os caminhos abaixo seguem a documentação
pública dos provedores, mas DEVEM ser conferidos na documentação vigente antes do uso em produção:

  Judit     https://docs.judit.io            (header "api-key")
  Escavador https://api.escavador.com/v2/docs/ (header "Authorization: Bearer <token>")

Os endereços-base são configuráveis via variáveis de ambiente para acompanhar mudanças dos provedores.
Resultados são normalizados para o formato interno e gravados no índice local; CPFs são mascarados.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

from .. import config  # noqa: F401
from .. import db
from ..entities import extract_entities, mask_doc, norm
from ..indexer import cnj_info
from .datajud import formatar

JUDIT_BASE = os.environ.get("JUDIT_BASE_URL", "https://requests.prod.judit.io")
ESCAVADOR_BASE = os.environ.get("ESCAVADOR_BASE_URL", "https://api.escavador.com/api/v2")
TIMEOUT = 60


def disponiveis() -> Dict[str, bool]:
    return {"judit": bool(os.environ.get("JUDIT_API_KEY")), "escavador": bool(os.environ.get("ESCAVADOR_TOKEN"))}


def _req(url: str, headers: Dict[str, str], body: Optional[Dict] = None, method: str = "GET") -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={**headers, "Content-Type": "application/json", "User-Agent": "legal-research-local/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} em {url}: {e.read().decode('utf-8', 'ignore')[:300]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Sem acesso a {url}: {e.reason}") from e


# ------------------------------------------------------------------ Judit

def judit_buscar(tipo: str, chave: str, esperar_seg: int = 90) -> List[Dict[str, Any]]:
    """tipo: cpf | cnpj | oab | name | lawsuit_cnj. Fluxo assíncrono: POST /requests -> GET /responses."""
    key = os.environ.get("JUDIT_API_KEY", "")
    if not key:
        raise RuntimeError("JUDIT_API_KEY não configurada")
    h = {"api-key": key}
    chave_limpa = re.sub(r"\D", "", chave) if tipo in ("cpf", "cnpj", "lawsuit_cnj") else chave
    created = _req(f"{JUDIT_BASE}/requests", h, {"search": {"search_type": tipo, "search_key": chave_limpa, "response_type": "lawsuit"}}, "POST")
    rid = (created or {}).get("request_id") or (created or {}).get("id")
    if not rid:
        raise RuntimeError(f"Judit não devolveu request_id: {str(created)[:200]}")
    fim = time.time() + esperar_seg
    while time.time() < fim:
        st = _req(f"{JUDIT_BASE}/requests/{rid}", h)
        if (st or {}).get("status") in ("completed", "done", "finished"):
            break
        time.sleep(3)
    res = _req(f"{JUDIT_BASE}/responses?request_id={urllib.parse.quote(rid)}", h)
    itens = res.get("page_data") if isinstance(res, dict) else res
    out = []
    for it in itens or []:
        rd = it.get("response_data") if isinstance(it, dict) else None
        if rd:
            out.append(_norm_judit(rd))
    return out


def _norm_judit(rd: Dict[str, Any]) -> Dict[str, Any]:
    partes = []
    for p in rd.get("parties") or []:
        partes.append({"nome": p.get("name"), "polo": {"active": "ativo", "passive": "passivo"}.get((p.get("side") or "").lower(), p.get("side")),
                       "tipo_pessoa": "PJ" if p.get("person_type") in ("legal", "PJ") else "PF", "documento": p.get("document")})
    advs = [{"nome": l.get("name"), "oab": l.get("license_number") or l.get("oab")} for p in rd.get("parties") or [] for l in p.get("lawyers") or []]
    movs = [{"data": (s.get("step_date") or "")[:10], "nome": s.get("content") or s.get("description") or ""} for s in rd.get("steps") or []]
    return {"numero": formatar(str(rd.get("code") or rd.get("lawsuit_cnj") or "")), "tribunal": rd.get("tribunal_acronym") or rd.get("tribunal"),
            "classe": ", ".join(rd.get("classifications_names") or []) or (rd.get("classification") or {}).get("name") if isinstance(rd.get("classification"), dict) else rd.get("classification"),
            "assunto": ", ".join(rd.get("subjects_names") or []) or None, "orgao_julgador": rd.get("court") or rd.get("justice_description"),
            "data_ajuizamento": (rd.get("distribution_date") or "")[:10] or None, "valor_causa": rd.get("amount"), "status": rd.get("status"),
            "partes": partes, "advogados": advs, "movimentos": movs, "fonte": "judit"}


# ------------------------------------------------------------------ Escavador

def escavador_buscar(tipo: str, chave: str, maximo: int = 100) -> List[Dict[str, Any]]:
    """tipo: nome | cpf_cnpj | oab (formato 'UF 123456') | numero_cnj."""
    tok = os.environ.get("ESCAVADOR_TOKEN", "")
    if not tok:
        raise RuntimeError("ESCAVADOR_TOKEN não configurado")
    h = {"Authorization": f"Bearer {tok}", "X-Requested-With": "XMLHttpRequest"}
    if tipo == "numero_cnj":
        res = _req(f"{ESCAVADOR_BASE}/processos/numero_cnj/{urllib.parse.quote(chave)}", h)
        return [_norm_escavador(res)] if res else []
    if tipo == "oab":
        uf, _, num = chave.replace("/", " ").strip().partition(" ")
        url = f"{ESCAVADOR_BASE}/advogado/processos?oab_estado={urllib.parse.quote(uf)}&oab_numero={urllib.parse.quote(num.strip())}"
    elif tipo == "cpf_cnpj":
        url = f"{ESCAVADOR_BASE}/envolvido/processos?cpf_cnpj={urllib.parse.quote(re.sub(r'\\D', '', chave))}"
    else:
        url = f"{ESCAVADOR_BASE}/envolvido/processos?nome={urllib.parse.quote(chave)}"
    out, prox = [], url
    while prox and len(out) < maximo:
        res = _req(prox, h)
        for it in (res or {}).get("items") or []:
            out.append(_norm_escavador(it))
        prox = ((res or {}).get("links") or {}).get("next")
    return out[:maximo]


def _norm_escavador(it: Dict[str, Any]) -> Dict[str, Any]:
    fontes = it.get("fontes") or []
    capa = (fontes[0].get("capa") if fontes else None) or {}
    partes, advs, movs = [], [], []
    for f in fontes:
        for e in f.get("envolvidos") or []:
            polo = {"ATIVO": "ativo", "PASSIVO": "passivo"}.get((e.get("polo") or "").upper())
            if polo:
                partes.append({"nome": e.get("nome"), "polo": polo, "tipo_pessoa": "PJ" if e.get("tipo_pessoa") == "JURIDICA" else "PF", "documento": e.get("cpf") or e.get("cnpj")})
            for a in e.get("advogados") or []:
                oabs = a.get("oabs") or []
                advs.append({"nome": a.get("nome"), "oab": f"{oabs[0].get('uf')} {oabs[0].get('numero')}" if oabs else None, "polo": polo})
    return {"numero": formatar(str(it.get("numero_cnj") or "")), "tribunal": (it.get("unidade_origem") or {}).get("tribunal_sigla"),
            "classe": capa.get("classe"), "assunto": capa.get("assunto"), "orgao_julgador": (it.get("unidade_origem") or {}).get("nome"),
            "data_ajuizamento": (it.get("data_inicio") or "")[:10] or None, "valor_causa": (capa.get("valor_causa") or {}).get("valor"),
            "status": None, "partes": partes, "advogados": advs, "movimentos": movs, "fonte": "escavador"}


# ------------------------------------------------------------------ gravação

def importar(itens: List[Dict[str, Any]]) -> Dict[str, Any]:
    db.init_db()
    stats = {"processos": 0, "atualizados": 0}
    with db.session() as con:
        for it in itens:
            numero = it.get("numero")
            if not numero:
                continue
            info = cnj_info(numero)
            campos = {"tribunal": it.get("tribunal") or info["tribunal"], "uf": info["uf"], "grau": info["grau"], "ano": info["ano"],
                      "orgao_julgador": it.get("orgao_julgador"), "classe": it.get("classe"), "assunto": it.get("assunto"),
                      "data_ajuizamento": it.get("data_ajuizamento"), "valor_causa": it.get("valor_causa"), "status": it.get("status") or "Ativo",
                      "pasta": it.get("fonte")}
            row = con.execute("SELECT id FROM processos WHERE numero=?", (numero,)).fetchone()
            if row:
                pid = row["id"]
                con.execute("UPDATE processos SET " + ", ".join(f"{k}=COALESCE(?, {k})" for k in campos) + " WHERE id=?", (*campos.values(), pid))
                stats["atualizados"] += 1
            else:
                cur = con.execute(f"INSERT INTO processos (numero, {', '.join(campos)}) VALUES (?, {', '.join('?' for _ in campos)})", (numero, *campos.values()))
                pid = cur.lastrowid
                stats["processos"] += 1
            for p in it.get("partes") or []:
                if p.get("nome") and not con.execute("SELECT 1 FROM partes WHERE processo_id=? AND lower(nome)=lower(?)", (pid, p["nome"])).fetchone():
                    con.execute("INSERT INTO partes (processo_id, nome, polo, tipo_pessoa, documento) VALUES (?,?,?,?,?)",
                                (pid, p["nome"], p.get("polo"), p.get("tipo_pessoa"), mask_doc(p["documento"]) if p.get("documento") else None))
            for a in it.get("advogados") or []:
                if a.get("nome") and not con.execute("SELECT 1 FROM profissionais WHERE processo_id=? AND papel='advogado' AND lower(nome)=lower(?)", (pid, a["nome"])).fetchone():
                    con.execute("INSERT INTO profissionais (processo_id, nome, papel, registro, polo) VALUES (?,?,?,?,?)", (pid, a["nome"], "advogado", a.get("oab"), a.get("polo")))
            if it.get("movimentos") or it.get("partes"):
                caminho = f"{it.get('fonte')}://{numero}"
                old = con.execute("SELECT id FROM documentos WHERE caminho=?", (caminho,)).fetchone()
                if old:
                    con.execute("DELETE FROM documentos WHERE id=?", (old["id"],))
                texto = f"Processo nº {numero}\nFonte: {it.get('fonte')}\n" + "\n".join(f"{p.get('polo','').upper()}: {p.get('nome')}" for p in it.get("partes") or []) + "\n\n"
                texto += "\n".join(f"{m.get('data','')} — {m.get('nome','')}" for m in it.get("movimentos") or [])
                cur = con.execute("INSERT INTO documentos (processo_id, arquivo, caminho, tipo, data_documento, fase, paginas, tamanho, hash, indexado_em) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                  (pid, f"{numero} - {it.get('fonte')}.txt", caminho, f"Capa e movimentações ({it.get('fonte')})", it.get("data_ajuizamento"), "Conhecimento", 1, len(texto), None, datetime.now().isoformat(timespec="seconds")))
                did = cur.lastrowid
                con.execute("INSERT INTO paginas (documento_id, numero, texto) VALUES (?,?,?)", (did, 1, texto))
                for t, vals in extract_entities(texto).items():
                    for v in vals:
                        con.execute("INSERT INTO entidades (documento_id, pagina, tipo, valor, valor_norm) VALUES (?,?,?,?,?)", (did, 1, t, v, norm(v)))
    return stats
