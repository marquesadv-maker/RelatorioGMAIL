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
from datetime import datetime
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


def _melhor_data(texto: str) -> Optional[Tuple[int, str]]:
    cands = _datas(texto)
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    pont = []
    for pos, d in cands:
        antes = texto[max(0, pos - 140):pos]
        depois = texto[pos:pos + 60]
        pt = 2 * len(PALAVRAS_DATA_BOA.findall(antes)) + len(PALAVRAS_DATA_BOA.findall(depois))
        pt -= 3 * len(PALAVRAS_DATA_RUIM.findall(antes[-80:]))
        pont.append((pt, -pos, pos, d))
    pont.sort(reverse=True)
    return (pont[0][2], pont[0][3]) if pont[0][0] > 0 else None  # sem pistas: deixa para a IA/usuário


def _horario(texto: str, pos_data: Optional[int]) -> Optional[Tuple[int, str]]:
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
            if not re.search(r"[àa]s\s*$|hor[aá]rio|hora", ctx) and base == 0:
                continue
            return base + m.start(), f"{h}h{mm}" if mm and mm != "00" else f"{h}h"
    return None


def _nome_apos(texto: str, rotulos: str) -> Optional[Tuple[int, int, str]]:
    m = re.search(rf"(?im)\b(?:{rotulos})\s*[:\-–]\s*([^\n\r]{{3,140}})", texto)
    if not m:
        return None
    nome = m.group(1)
    nome = re.split(r"\s{2,}|\s+(?:reclamad[ao]s?|reclamantes?|advogad[ao]s?|cpf|cnpj|processo|r[ée]us?|autor(?:es|a)?|requerid[ao]s?|requerentes?)\b\s*[:\-–]",
                    nome, maxsplit=1, flags=re.I)[0]
    nome = nome.strip(" .;,-–")
    return (m.start(1), m.start(1) + len(nome), nome) if len(nome) >= 3 else None


def extrair_campos(texto: str, agora: Optional[datetime] = None) -> Dict[str, Dict[str, Any]]:
    """Campos encontrados com certeza razoável. Cada um: {valor, origem, trecho}."""
    out: Dict[str, Dict[str, Any]] = {}

    def add(campo: str, valor: str, trecho: str = "", origem: str = "documento"):
        if valor:
            out[campo] = {"valor": valor, "origem": origem, "trecho": trecho[:160]}

    m = CNJ.search(texto)
    if m:
        add("PROCESSO", m.group(0), _trecho(texto, m.start(), m.end()))
    d = _melhor_data(texto)
    if d:
        add("DATA", d[1], _trecho(texto, d[0], d[0] + 10))
    h = _horario(texto, d[0] if d else None)
    if h:
        add("HORARIO", h[1], _trecho(texto, h[0], h[0] + 8))
    tn = _n(texto)
    if re.search(r"hibrid", tn):
        add("MODALIDADE", "híbrida", "menção a audiência híbrida")
    elif re.search(r"telepresencial|videoconfer|\bvirtual\b|\bzoom\b|\bteams\b|meet\.google", tn):
        add("MODALIDADE", "telepresencial", "menção a telepresencial/videoconferência")
    elif re.search(r"\bpresencial", tn):
        add("MODALIDADE", "presencial", "menção a audiência presencial")
    for lk in LINK.finditer(texto):
        if LINK_REUNIAO.search(lk.group(0)):
            add("LINK", lk.group(0).rstrip(".,;"), _trecho(texto, lk.start(), lk.end(), 20))
            break
    r = _nome_apos(texto, r"reclamante|autor(?:a)?|requerente|parte autora")
    if r:
        add("RECLAMANTE", r[2], _trecho(texto, r[0], r[1], 25))
    r = _nome_apos(texto, r"reclamad[ao]s?|r[ée]u|requerid[ao]|parte r[ée]")
    if r:
        add("RECLAMADA", r[2], _trecho(texto, r[0], r[1], 25))
    hora = (agora or datetime.now()).hour
    add("PERIODO", "bom dia" if hora < 12 else "boa tarde" if hora < 18 else "boa noite", "pelo horário atual", "automatico")
    return out


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
