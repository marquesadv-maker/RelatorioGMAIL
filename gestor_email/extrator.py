"""
Leitura local de documentos (sem IA e, portanto, sem gastar tokens).

- texto_do_arquivo: extrai o texto de PDFs que tenham texto selecionável.
- extrair_campos: acha nº do processo, data, horário, modalidade, link e partes.
- classificar: escolhe o modelo de e-mail por regras (seção "SELEÇÃO AUTOMÁTICA" da skill).
- recorte: devolve só os trechos úteis do texto, para a IA gastar menos.

A IA só entra depois, para o que estas regras não resolverem.
"""
import io
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

MESES = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
         "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
CNJ = re.compile(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b")
DATA_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
DATA_EXT = re.compile(r"\b(\d{1,2})\s+de\s+(janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})\b", re.I)
HORA = re.compile(r"\b(\d{1,2})\s*(?:h|:|horas?)\s*(\d{2})?\s*(?:min)?", re.I)
LINK = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
LINK_REUNIAO = re.compile(r"zoom|teams|meet\.google|webex|videoconfer|audienciavirtual|cnj\.jus|pje.*audiencia", re.I)
PALAVRAS_DATA_BOA = re.compile(r"audi[eê]ncia|per[ií]cia|designad|realiz|marcad|comparec|prazo|vistoria", re.I)
PALAVRAS_DATA_RUIM = re.compile(r"publicad|disponibiliz|assinad|expedid|protocol|distribu[ií]d|ajuizad|autua", re.I)


def cnj_valido(numero: str) -> bool:
    """Confere os dígitos verificadores do número único do processo (Resolução CNJ 65/2008, módulo 97)."""
    m = re.fullmatch(r"(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})", numero or "")
    if not m:
        return False
    nnnnnnn, dd, aaaa, j, tr, oooo = m.groups()
    return 98 - (int(nnnnnnn + aaaa + j + tr + oooo + "00") % 97) == int(dd)


def dias_uteis_antes(data_br: str, n: int) -> Optional[str]:
    """Data n dias úteis (seg-sex; feriados não considerados) antes de data_br."""
    try:
        d = datetime.strptime(data_br, "%d/%m/%Y")
    except ValueError:
        return None
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d.strftime("%d/%m/%Y")


def _n(t: str) -> str:
    """Minúsculas e sem acentos, para casar palavras-chave."""
    return unicodedata.normalize("NFD", t.lower()).encode("ascii", "ignore").decode()


# ─── Texto dos arquivos ──────────────────────────────────────────────────────

def texto_do_arquivo(nome: str, mime: str, dados: bytes) -> Optional[str]:
    """Texto do PDF, ou None se não houver texto (PDF escaneado, imagem) ou pypdf ausente."""
    if mime != "application/pdf":
        return None
    try:
        from pypdf import PdfReader
        leitor = PdfReader(io.BytesIO(dados))
        paginas = [(p.extract_text() or "") for p in leitor.pages[:40]]
    except Exception:
        return None
    texto = "\n".join(paginas).strip()
    if len(re.sub(r"\s+", "", texto)) < 80 * max(1, len(paginas)):
        return None  # praticamente sem texto: precisa de leitura por imagem
    return texto


# ─── Campos ──────────────────────────────────────────────────────────────────

def _trecho(texto: str, ini: int, fim: int, folga: int = 50) -> str:
    return re.sub(r"\s+", " ", texto[max(0, ini - folga):fim + folga]).strip()


def _datas(texto: str) -> List[Tuple[int, str]]:
    out = []
    for m in DATA_NUM.finditer(texto):
        d, mm, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mm <= 12:
            out.append((m.start(), f"{d:02d}/{mm:02d}/{a}"))
    for m in DATA_EXT.finditer(texto):
        mes = MESES.get(m.group(2).lower().replace("ç", "c").replace("c", "ç") if False else m.group(2).lower())
        if mes is None:
            mes = MESES.get(_n(m.group(2)))
        if mes:
            out.append((m.start(), f"{int(m.group(1)):02d}/{mes:02d}/{m.group(3)}"))
    return sorted(out)


def _melhor_data(texto: str) -> Optional[Tuple[int, str, str]]:
    """(posição, data dd/mm/aaaa, confiança). Sem nenhuma pista de que é a data do ato, devolve None."""
    cands = _datas(texto)
    if not cands:
        return None
    pont = []
    for pos, d in cands:
        antes = texto[max(0, pos - 140):pos]
        depois = texto[pos:pos + 60]
        pt = 2 * len(PALAVRAS_DATA_BOA.findall(antes)) + len(PALAVRAS_DATA_BOA.findall(depois))
        pt -= 3 * len(PALAVRAS_DATA_RUIM.findall(antes[-80:]))
        pont.append((pt, -pos, pos, d))
    pont.sort(reverse=True)
    melhor = pont[0]
    distintas = {d for _, d in cands}
    if len(cands) == 1:
        return cands[0][0], cands[0][1], "alta" if melhor[0] > 0 else "media"
    if melhor[0] <= 0:
        return None  # várias datas e nenhuma pista: deixa para a IA
    empate = len(pont) > 1 and pont[1][0] == melhor[0] and pont[1][3] != melhor[3]
    return melhor[2], melhor[3], "media" if (empate or len(distintas) > 2 and melhor[0] < 3) else "alta"


def _horario(texto: str, pos_data: Optional[int]) -> Optional[Tuple[int, str, str]]:
    regioes = []
    if pos_data is not None:
        regioes.append((pos_data, texto[pos_data:pos_data + 140]))
    regioes.append((0, texto))
    for base, trecho in regioes:
        for m in HORA.finditer(trecho):
            h = int(m.group(1))
            mm = m.group(2)
            if not (0 <= h <= 23) or (mm and int(mm) > 59):
                continue
            ctx = trecho[max(0, m.start() - 12):m.start()].lower()
            com_as = bool(re.search(r"[àa]s\s*$|hor[aá]rio|hora", ctx))
            if not com_as and base == 0:
                continue
            valor = f"{h}h{mm}" if mm and mm != "00" else f"{h}h"
            return base + m.start(), valor, "alta" if (base != 0 and com_as) else "media"
    return None


def _nome_apos(texto: str, rotulos: str) -> Optional[Tuple[int, int, str]]:
    m = re.search(rf"(?im)\b(?:{rotulos})\s*[:\-–]\s*([^\n\r]{{3,140}})", texto)
    if not m:
        return None
    nome = m.group(1)
    nome = re.split(r"\s{2,}|\s+(?:reclamad[ao]s?|reclamantes?|advogad[ao]s?|cpf|cnpj|processo|r[ée]us?|autor(?:es|a)?|requerid[ao]s?|requerentes?)\b\s*[:\-–]",
                    nome, maxsplit=1, flags=re.I)[0]
    # Corta no fim da frase ("... Ltda. Valor da causa"), mas preserva abreviaturas societárias
    for fim in re.finditer(r"\.\s+(?=[A-ZÀ-Ú])", nome):
        ultimo = nome[:fim.start()].split()[-1].lower() if nome[:fim.start()].split() else ""
        if ultimo not in {"ltda", "s/a", "s.a", "epp", "me", "eireli", "cia", "s.a.", "ltda."}:
            nome = nome[:fim.start()]
            break
    nome = nome.strip(" ;,-–")
    if nome.endswith(".") and not re.search(r"(?i)\b(ltda|s/a|s\.a|epp|eireli|cia)\.$", nome):
        nome = nome[:-1]
    return (m.start(1), m.start(1) + len(nome), nome) if len(nome) >= 3 else None


_NOME_OK = re.compile(r"^[A-ZÀ-Úa-zà-ú0-9][A-ZÀ-Úa-zà-ú0-9 .'&/\-ªº,]+$")


def extrair(texto: str, agora: Optional[datetime] = None) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Campos encontrados por regras, cada um com {valor, origem, trecho, confianca}, e avisos de ambiguidade."""
    out: Dict[str, Dict[str, Any]] = {}
    avisos: List[str] = []

    def add(campo: str, valor: str, trecho: str = "", origem: str = "documento", conf: str = "alta"):
        if valor:
            out[campo] = {"valor": valor, "origem": origem, "trecho": trecho[:160], "confianca": conf}

    procs = list(dict.fromkeys(CNJ.findall(texto)))
    if procs:
        # com mais de um número, prefere o que vem logo depois de "processo"
        escolhido = procs[0]
        if len(procs) > 1:
            for mm in re.finditer(r"processo\s*(?:n[ºo.°]*\s*)?[:\-]?\s*(" + CNJ.pattern + ")", texto, re.I):
                escolhido = mm.group(1)
                break
            avisos.append(f"O documento cita {len(procs)} números de processo; usei {escolhido}. Confira.")
        pos = texto.index(escolhido)
        valido = cnj_valido(escolhido)
        if not valido:
            avisos.append(f"O número {escolhido} não passa na conferência dos dígitos verificadores do CNJ: confira.")
        add("PROCESSO", escolhido, _trecho(texto, pos, pos + len(escolhido)), conf="alta" if valido and len(procs) == 1 else "media")
        if not valido:
            out["PROCESSO"]["verificar"] = True
    d = _melhor_data(texto)
    if d:
        add("DATA", d[1], _trecho(texto, d[0], d[0] + 10), conf=d[2])
    h = _horario(texto, d[0] if d else None)
    if h:
        add("HORARIO", h[1], _trecho(texto, h[0], h[0] + 8), conf=h[2])
    tn = _n(texto)
    tem_tele = bool(re.search(r"telepresencial|videoconfer|\bvirtual\b|\bzoom\b|\bteams\b|meet\.google", tn))
    tem_pres = bool(re.search(r"\bpresencial", tn))
    if re.search(r"hibrid", tn):
        add("MODALIDADE", "híbrida", "menção a audiência híbrida")
    elif tem_tele:
        add("MODALIDADE", "telepresencial", "menção a telepresencial/videoconferência", conf="media" if tem_pres else "alta")
    elif tem_pres:
        add("MODALIDADE", "presencial", "menção a audiência presencial")
    for lk in LINK.finditer(texto):
        if LINK_REUNIAO.search(lk.group(0)):
            add("LINK", lk.group(0).rstrip(".,;"), _trecho(texto, lk.start(), lk.end(), 20))
            break
    ta = re.search(r"audi[eê]ncia\s+(?:de\s+)?(concilia[cç][aã]o|instru[cç][aã]o|una|inaugural|julgamento)", texto, re.I)
    if ta:
        add("TIPO_AUDIENCIA", {"conciliacao": "conciliação", "instrucao": "instrução"}.get(_n(ta.group(1)), _n(ta.group(1))), ta.group(0))
    vc = re.search(r"valor da causa[^R\n]{0,40}(R\$\s*[\d\.]+,\d{2})", texto, re.I)
    if vc:
        add("VALOR_CAUSA", vc.group(1), vc.group(0))
    vara = re.search(r"\b(\d{1,3}\s*[ªaº]?\s*Vara do Trabalho(?:\s+de\s+[A-ZÀ-Ú][A-Za-zà-ú]+(?:\s+[A-ZÀ-Ú][A-Za-zà-ú]+)?)?)", texto)
    if vara:
        add("VARA", vara.group(1), vara.group(0))
        add("ORGAO", vara.group(1), vara.group(0))
    for campo, rotulos in (("RECLAMANTE", r"reclamante|autor(?:a)?|requerente|parte autora"),
                           ("RECLAMADA", r"reclamad[ao]s?|r[ée]u|requerid[ao]|parte r[ée]")):
        r = _nome_apos(texto, rotulos)
        if r:
            nome = r[2]
            if campo == "RECLAMADA":  # razão social costuma terminar no tipo societário
                ms = re.search(r"^(.*?\b(?:Ltda\.?|S/A|S\.A\.?|EPP|Eireli|Cia\.?|ME))(?=\s|$|[,;])", nome, re.I)
                if ms:
                    nome = ms.group(1)
            seguro = len(nome.split()) >= 2 and not re.search(r"\d", nome) and len(nome) <= 90 and bool(_NOME_OK.match(nome))
            add(campo, nome, _trecho(texto, r[0], r[1], 25), conf="alta" if seguro else "media")
    hora = (agora or datetime.now()).hour
    add("PERIODO", "bom dia" if hora < 12 else "boa tarde" if hora < 18 else "boa noite", "pelo horário atual", "automatico")
    _derivar(out)
    return out, avisos


def _derivar(c: Dict[str, Dict[str, Any]]) -> None:
    """Campos que repetem outros (ex.: PARTE_A x PARTE_B = reclamante x reclamada)."""
    mapa = {"PARTE_A": "RECLAMANTE", "PARTE_B": "RECLAMADA", "DATA_AUDIENCIA": "DATA",
            "LINK_OU_ENDERECO": "LINK", "LOCAL_OU_LINK": "LINK", "LINK_OU_ENDERECO_REUNIAO": "LINK"}
    for destino, origem in mapa.items():
        if destino not in c and origem in c:
            c[destino] = {"valor": c[origem]["valor"], "origem": "derivado", "trecho": f"igual a {origem}", "confianca": c[origem]["confianca"]}


def extrair_campos(texto: str, agora: Optional[datetime] = None) -> Dict[str, Dict[str, Any]]:
    return extrair(texto, agora)[0]


# ─── Escolha do modelo por regras ────────────────────────────────────────────

def classificar(texto: str, campos: Dict[str, Any]) -> Dict[str, Any]:
    """{codigo, confianca: alta|media|baixa, candidatos: [...]}  (nunca "chuta" com confiança alta sem sinal claro)."""
    t = _n(texto)
    tem = lambda rx: re.search(rx, t) is not None
    res = lambda c, conf, cands=None: {"codigo": c, "confianca": conf, "candidatos": cands or [c]}

    if tem(r"homologacao de transacao extrajudicial|\bhte\b"):
        return res("HTE-01", "media", ["HTE-01", "HTE-02", "HTE-03", "HTE-04", "HTE-05"])
    if tem(r"carta precatoria"):
        return res("CP-01", "media")
    if tem(r"pericia|perito|laudo pericial|assistente tecnico|quesitos"):
        if tem(r"laudo pericial") and tem(r"desfavor|insalubr|periculos|conclusao"):
            return res("PER-05", "media", ["PER-05", "PER-03"])
        if tem(r"quesitos"):
            return res("PER-02", "media", ["PER-02", "PER-03", "PER-04"])
        if "DATA" in campos:
            return res("PER-03", "media", ["PER-03", "PER-04"])
        return res("PER-01", "alta")
    if tem(r"audiencia"):
        if tem(r"segundo grau|2[o°º] grau") and tem(r"concilia"):
            return res("AUD-03", "alta")
        if tem(r"audiencia una|\buna\b"):
            return res("AUD-05", "media", ["AUD-05", "AUD-04"])
        if tem(r"instrucao"):
            return res("AUD-01", "alta", ["AUD-01", "AUD-04"])
        if tem(r"concilia"):
            if tem(r"contestac|defesa|documentos"):
                return res("AUD-06", "media", ["AUD-06", "AUD-02", "AUD-08"])
            return res("AUD-02", "alta", ["AUD-02", "AUD-08"])
        return res("AUD-04", "baixa", ["AUD-04", "AUD-02", "AUD-01"])
    if tem(r"sentenca|acordao|julgo|dispositivo"):
        if tem(r"acordao") and tem(r"exclu"):
            return res("JUL-05", "media", ["JUL-05", "DEC-01"])
        if tem(r"improcedente") and not tem(r"condena|parcialmente procedente|procedente em parte"):
            return res("JUL-04" if tem(r"acordao") else "JUL-03", "media", ["JUL-03", "JUL-04", "DEC-01"])
        if tem(r"condena|parcialmente procedente|procedente em parte|julgo procedente"):
            return res("JUL-02", "media", ["JUL-02", "JUL-06", "DEC-01"])
        return res("DEC-01", "baixa", ["DEC-01", "JUL-02", "JUL-03"])
    if tem(r"tutela de urgencia|liminar|tutela provisoria"):
        return res("JUL-01", "media")
    if tem(r"homolog\w+ (?:o )?acordo|acordo homologado|termo de acordo"):
        return res("ACO-01", "media", ["ACO-01", "ACO-02"])
    if tem(r"custas|deposito recursal"):
        return res("CUST-01", "media")
    if tem(r"execucao|penhora|sisbajud|bacenjud|garantia do juizo"):
        return res("EXE-01", "media")
    return {"codigo": "", "confianca": "baixa", "candidatos": []}


# ─── Recorte do texto para a IA ──────────────────────────────────────────────

_CHAVES = re.compile(
    r"processo|audi[eê]ncia|per[ií]cia|reclamante|reclamad|autor|r[ée]u|designad|intim|cita[cç][aã]o|"
    r"julg|condena|defiro|indefiro|homolog|valor|R\$|prazo|dia \d|[àa]s \d|link|zoom|teams|dispositivo|ac[oó]rd[aã]o",
    re.I,
)


def recorte(texto: str, limite: int = 7000) -> str:
    """Se o texto for longo, mantém o início e as janelas em torno das palavras-chave (menos tokens)."""
    texto = re.sub(r"[ \t]+", " ", re.sub(r"\n{2,}", "\n", texto)).strip()
    if len(texto) <= limite:
        return texto
    partes: List[Tuple[int, int]] = [(0, 1800)]
    for m in _CHAVES.finditer(texto):
        partes.append((max(0, m.start() - 250), min(len(texto), m.end() + 350)))
    partes.sort()
    fund: List[List[int]] = []
    for a, b in partes:
        if fund and a <= fund[-1][1]:
            fund[-1][1] = max(fund[-1][1], b)
        else:
            fund.append([a, b])
    saida, total = [], 0
    for a, b in fund:
        trecho = texto[a:b]
        if total + len(trecho) > limite:
            trecho = trecho[: max(0, limite - total)]
        if trecho:
            saida.append(trecho)
            total += len(trecho)
        if total >= limite:
            break
    return "\n[...]\n".join(saida)
