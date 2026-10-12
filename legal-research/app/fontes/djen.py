"""Conector ao DJEN / Comunica PJe (CNJ): publicações oficiais com nomes de partes, advogados e texto integral.

Endpoint público, sem chave:  GET https://comunicaapi.pje.jus.br/api/v1/comunicacao
Documentação (Swagger):        https://comunicaapi.pje.jus.br/swagger/index.html
Portal CNJ:                    https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/comunicacoes-processuais/

Parâmetros usados: nomeParte, nomeAdvogado, numeroOab + ufOab, numeroProcesso, siglaTribunal,
dataDisponibilizacaoInicio/Fim, meio (D = Diário, E = Editais), itensPorPagina (5 ou 100), pagina.
Limites conhecidos: controle por IP (HTTP 429 → aguardar 1 minuto); no máximo 10.000 resultados por pesquisa.

É a única fonte pública gratuita que permite buscar por NOME de parte ou advogado. Não traz as peças do
processo, apenas o texto das intimações, despachos, sentenças e editais publicados.
"""
import html as html_mod
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import json
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from .. import config  # noqa: F401
from .. import db
from ..entities import extract_entities, mask_doc, norm
from ..indexer import cnj_info
from .datajud import formatar

BASE_URL = os.environ.get("DJEN_BASE_URL", "https://comunicaapi.pje.jus.br/api/v1/comunicacao")
TIMEOUT = int(os.environ.get("DJEN_TIMEOUT", "60"))
FORMATO_DATA = os.environ.get("DJEN_FORMATO_DATA", "iso")   # iso = AAAA-MM-DD | br = DD/MM/AAAA
TRIBUNAIS_TRABALHISTAS = [f"TRT{n}" for n in range(1, 25)] + ["TST"]


def _data(d: Optional[str]) -> Optional[str]:
    if not d:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", d)
    if not m:
        return d
    return d if FORMATO_DATA == "iso" else f"{m.group(3)}/{m.group(2)}/{m.group(1)}"


def _get(params: Dict[str, Any]) -> Dict[str, Any]:
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    req = urllib.request.Request(f"{BASE_URL}?{qs}", headers={"Accept": "application/json", "User-Agent": "legal-research-local/1.0"})
    for tentativa in range(3):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            if e.code == 429 and tentativa < 2:
                time.sleep(61)
                continue
            raise RuntimeError(f"DJEN HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"DJEN inacessível: {e.reason}") from e
    return {}


def buscar(nome_parte: str = "", nome_advogado: str = "", numero_oab: str = "", uf_oab: str = "", numero_processo: str = "",
           tribunal: str = "", data_inicio: str = "", data_fim: str = "", meio: str = "", maximo: int = 100,
           somente_trabalhista: bool = True) -> Iterator[Dict[str, Any]]:
    """Itera publicações (100 por página) até `maximo`. Sem tribunal, percorre todos e filtra a esfera localmente."""
    base = {"nomeParte": nome_parte or None, "nomeAdvogado": nome_advogado or None, "numeroOab": re.sub(r"\D", "", numero_oab) or None,
            "ufOab": (uf_oab or "").upper() or None, "numeroProcesso": re.sub(r"\D", "", numero_processo) or None,
            "siglaTribunal": tribunal or None, "dataDisponibilizacaoInicio": _data(data_inicio), "dataDisponibilizacaoFim": _data(data_fim),
            "meio": meio or None, "itensPorPagina": 100}
    if not any(base[k] for k in ("nomeParte", "nomeAdvogado", "numeroOab", "numeroProcesso")):
        raise ValueError("informe nome da parte, nome do advogado, OAB ou número do processo")
    total, pagina = 0, 1
    while total < maximo:
        res = _get({**base, "pagina": pagina})
        itens = res.get("items") or res.get("itens") or []
        if not itens:
            break
        for it in itens:
            sigla = (it.get("siglaTribunal") or "").upper()
            if somente_trabalhista and not tribunal and sigla and sigla not in TRIBUNAIS_TRABALHISTAS:
                continue
            yield it
            total += 1
            if total >= maximo:
                return
        if len(itens) < 100:
            break
        pagina += 1


def _texto(it: Dict[str, Any]) -> str:
    t = it.get("texto") or ""
    t = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html_mod.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _partes(it: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for d in it.get("destinatarios") or []:
        nome = (d.get("nome") or "").strip()
        if not nome:
            continue
        polo = {"A": "ativo", "P": "passivo"}.get((d.get("polo") or "").upper()[:1], None)
        tp = "PJ" if re.search(r"LTDA|S\.?/?A\b|S\.A\.|EIRELI|\bME\b|EPP|MUNICIPIO|MUNICÍPIO|ESTADO D|UNIÃO|SINDICATO|ASSOCIA", nome, re.I) else "PF"
        out.append({"nome": nome, "polo": polo, "tipo_pessoa": tp})
    return out


def _advogados(it: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for a in it.get("destinatarioadvogados") or []:
        adv = a.get("advogado") if isinstance(a.get("advogado"), dict) else a
        nome = (adv.get("nome") or "").strip()
        if nome:
            oab = f"{(adv.get('uf_oab') or '').upper()} {adv.get('numero_oab') or ''}".strip()
            out.append({"nome": nome, "oab": oab or None})
    return out


def _numero(it: Dict[str, Any]) -> str:
    n = it.get("numeroprocessocommascara") or it.get("numero_processo") or it.get("numeroProcesso") or ""
    return formatar(str(n)) if n else ""


def _dt(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(s))
    if m:
        return m.group(1)
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", str(s))
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def importar(itens, progress=None, total: Optional[int] = None) -> Dict[str, Any]:
    """Grava cada publicação como documento 'Publicação (DJEN)' do processo correspondente; partes e advogados viram filtros."""
    db.init_db()
    stats = {"processos": 0, "atualizados": 0, "publicacoes": 0, "ignoradas": 0}
    with db.session() as con:
        for i, it in enumerate(itens, 1):
            if progress:
                progress(i, total, _numero(it))
            if i % 50 == 0:
                con.commit()
            numero = _numero(it)
            if not numero:
                stats["ignoradas"] += 1
                continue
            info = cnj_info(numero)
            sigla = (it.get("siglaTribunal") or "").upper()
            trib = (f"TRT-{sigla[3:]}" if sigla.startswith("TRT") else sigla) or info["tribunal"]
            campos = {"tribunal": trib, "uf": info["uf"], "grau": info["grau"], "ano": info["ano"], "orgao_julgador": it.get("nomeOrgao"),
                      "classe": it.get("nomeClasse"), "pasta": "djen"}
            row = con.execute("SELECT id FROM processos WHERE numero=?", (numero,)).fetchone()
            if row:
                pid = row["id"]
                con.execute("UPDATE processos SET " + ", ".join(f"{k}=COALESCE({k}, ?)" for k in campos) + " WHERE id=?", (*campos.values(), pid))
                stats["atualizados"] += 1
            else:
                cur = con.execute(f"INSERT INTO processos (numero, status, {', '.join(campos)}) VALUES (?, 'Ativo', {', '.join('?' for _ in campos)})", (numero, *campos.values()))
                pid = cur.lastrowid
                stats["processos"] += 1
            for p in _partes(it):
                if not con.execute("SELECT 1 FROM partes WHERE processo_id=? AND lower(nome)=lower(?)", (pid, p["nome"])).fetchone():
                    con.execute("INSERT INTO partes (processo_id, nome, polo, tipo_pessoa) VALUES (?,?,?,?)", (pid, p["nome"], p["polo"], p["tipo_pessoa"]))
            for a in _advogados(it):
                if not con.execute("SELECT 1 FROM profissionais WHERE processo_id=? AND papel='advogado' AND lower(nome)=lower(?)", (pid, a["nome"])).fetchone():
                    con.execute("INSERT INTO profissionais (processo_id, nome, papel, registro) VALUES (?,?,?,?)", (pid, a["nome"], "advogado", a["oab"]))
            ident = it.get("id") or it.get("hash") or it.get("numeroComunicacao") or f"{numero}-{_dt(it.get('data_disponibilizacao'))}"
            caminho = f"djen://{ident}"
            if con.execute("SELECT 1 FROM documentos WHERE caminho=?", (caminho,)).fetchone():
                stats["ignoradas"] += 1
                continue
            tipo = (it.get("tipoDocumento") or it.get("tipoComunicacao") or "Publicação").strip().title()
            texto = _texto(it)
            cab = (f"Processo nº {numero} ({sigla})\nÓrgão: {it.get('nomeOrgao') or ''}\nTipo: {it.get('tipoComunicacao') or ''} · {tipo} · {it.get('nomeClasse') or ''}\n"
                   f"Disponibilizado em {_dt(it.get('data_disponibilizacao')) or ''} · Meio: {'Diário Eletrônico' if (it.get('meio') or '') == 'D' else 'Plataforma de Editais' if (it.get('meio') or '') == 'E' else it.get('meio') or ''}\n"
                   + "\n".join(f"{(p['polo'] or 'parte').upper()}: {p['nome']}" for p in _partes(it)) + "\n"
                   + "\n".join(f"ADVOGADO: {a['nome']} (OAB {a['oab']})" for a in _advogados(it) if a.get('oab')) + "\n\n")
            paginas = [cab + texto[i:i + 3500] for i in range(0, max(len(texto), 1), 3500)]
            cur = con.execute("INSERT INTO documentos (processo_id, arquivo, caminho, tipo, data_documento, fase, paginas, tamanho, hash, indexado_em) VALUES (?,?,?,?,?,?,?,?,?,?)",
                              (pid, f"{numero} - {tipo} (DJEN).txt", caminho, f"{tipo} (DJEN)", _dt(it.get("data_disponibilizacao")), None, len(paginas), len(texto), it.get("hash"), datetime.now().isoformat(timespec="seconds")))
            did = cur.lastrowid
            linhas_p, linhas_e = [], []
            for n, pg in enumerate(paginas, 1):
                pg = re.sub(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", lambda m: mask_doc(m.group(0)), pg)  # LGPD: CPF mascarado
                linhas_p.append((did, n, pg))
                for t, vals in extract_entities(pg).items():
                    linhas_e.extend((did, n, t, v, norm(v)) for v in vals)
            con.executemany("INSERT INTO paginas (documento_id, numero, texto) VALUES (?,?,?)", linhas_p)
            con.executemany("INSERT INTO entidades (documento_id, pagina, tipo, valor, valor_norm) VALUES (?,?,?,?,?)", linhas_e)
            if it.get("link"):
                con.execute("UPDATE documentos SET caminho=caminho WHERE id=?", (did,))
            stats["publicacoes"] += 1
    db.bump()
    return stats
