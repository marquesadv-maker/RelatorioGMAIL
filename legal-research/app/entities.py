"""Extração de entidades por regras (sem modelos externos).

Tipos gerados (equivalentes aos "Tipos de trecho" do Legal Research):
 pessoas, organizacoes, juizes, varas, tribunais, fundamentos, funcoes, advogados, cnpj
"""
import re
import unicodedata
from typing import Dict, List, Tuple

CNJ_RE = re.compile(r"\b(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})\b")
OAB_RE = re.compile(r"OAB\s*[/\-]?\s*([A-Z]{2})\s*(?:n[ºo°\.]?\s*)?[:\-]?\s*([\d\.]{3,8})", re.I)
CNPJ_RE = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
VALOR_RE = re.compile(r"R\$\s?([\d\.]+,\d{2})")
DATA_RE = re.compile(r"\b(\d{1,2})\s*(?:/|de\s+)\s*(\d{1,2}|janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s*(?:/|de\s+)\s*(\d{4})\b", re.I)
MESES = {m: i + 1 for i, m in enumerate(["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"])}
MESES["marco"] = 3

NOME = r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+(?:\s+(?:d[aeo]s?\s+)?[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+){1,5}"
NOME_CAIXA = r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}(?:\s+(?:D[AEO]S?\s+)?[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,6}"
NOME_QQ = f"(?:{NOME_CAIXA}|{NOME})"

ORG_SUFIX = r"(?:LTDA\.?|LTDA\s*-\s*ME|S\.?/?A\.?|S\.A\.|EIRELI|ME|EPP|MEI|SOCIEDADE AN[ÔO]NIMA|COMÉRCIO|INDÚSTRIA|SERVIÇOS|TRANSPORTES|CONSTRUTORA|ALIMENTOS|SUPERMERCADO|HOSPITAL|BANCO|COOPERATIVA|ASSOCIAÇÃO|SINDICATO(?:\s+D[AEO]S?\s+[A-ZÁÉÍÓÚ][\w\s]+?)?)"
ORG_RE = re.compile(r"\b((?:[A-ZÁÉÍÓÚÂÊÔÃÕÇ&][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç&\.\-]*\s+){0,6}" + ORG_SUFIX + r")(?=[\s,\.;:\)]|$)")
JUIZ_RE = re.compile(r"\b(?:Juiz[a]?(?:\s+do\s+Trabalho)?(?:\s+Substitut[oa]|\s+Titular)?|Desembargador[a]?(?:\s+do\s+Trabalho)?|Ministr[oa]|Relator[a]?)\s*[:\-–]?\s*(" + NOME_QQ + r")")
VARA_RE = re.compile(r"\b(\d{1,3}ª?\s*Vara\s+do\s+Trabalho\s+de\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wáéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ]+(?:\s+(?:d[aeo]s?\s+)?[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wáéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ]+){0,3}|Vara\s+do\s+Trabalho\s+de\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wáéíóúâêôãõç]+(?:\s+(?:d[aeo]s?\s+)?[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wáéíóúâêôãõç]+){0,3})")
TRIB_RE = re.compile(r"\b(Tribunal\s+Regional\s+do\s+Trabalho\s+da\s+\d{1,2}ª\s+Região|TRT\s*[-–]?\s*\d{1,2}ª?\s*(?:Região)?|Tribunal\s+Superior\s+do\s+Trabalho|TST|Supremo\s+Tribunal\s+Federal|STF|Superior\s+Tribunal\s+de\s+Justiça|STJ)\b", re.I)
FUND_RE = re.compile(r"\b((?:art(?:igo)?s?\.?\s*\d{1,4}(?:º|o)?(?:\s*,\s*(?:§|par[áa]grafo)\s*\d+º?|\s*,\s*(?:inciso\s+)?[IVXLC]+|\s*,\s*al[íi]nea\s+[a-z])*(?:\s*(?:d[ao]|,)\s*(?:CLT|CF(?:/88)?|Constituição\s+Federal|CPC|CC|Código\s+Civil|Código\s+de\s+Processo\s+Civil|Lei\s+n?[ºo°\.]?\s*[\d\.]+(?:/\d{2,4})?))?)|Súmula\s+(?:n?[ºo°\.]?\s*)?\d{1,4}(?:\s+do\s+TST|\s+do\s+STF|\s+do\s+STJ)?|OJ\s+(?:n?[ºo°\.]?\s*)?\d{1,4}(?:\s+da\s+SDI-?\d)?|Lei\s+n?[ºo°\.]?\s*[\d\.]{3,7}(?:/\d{2,4})?|Lei\s+Complementar\s+n?[ºo°\.]?\s*\d+|Tema\s+\d{1,4}\s+(?:do|da)\s+(?:STF|TST|STJ))\b", re.I)
FUNCAO_RE = re.compile(r"\b(?:fun[çc][ãa]o|cargo|contratad[oa]\s+como|exerc(?:ia|eu|endo)\s+(?:a\s+fun[çc][ãa]o\s+de|o\s+cargo\s+de)|na\s+fun[çc][ãa]o\s+de|admitid[oa]\s+(?:como|para\s+exercer\s+a\s+fun[çc][ãa]o\s+de))\s*(?:de\s+|:\s*)?([a-záéíóúâêôãõç][\wáéíóúâêôãõç]+(?:\s+(?:de|do|da|dos|das|e)?\s*[a-záéíóúâêôãõç][\wáéíóúâêôãõç]+){0,3})", re.I)
ADV_RE = re.compile(r"(" + NOME_QQ + r")\s*[,\-–]?\s*(?:advogad[oa]\s*,?\s*)?(?:inscrit[oa]\s+na\s+)?OAB\s*[/\-]?\s*([A-Z]{2})\s*(?:n[ºo°\.]?\s*)?[:\-]?\s*([\d\.]{3,8})", re.I)
PESSOA_CTX_RE = re.compile(r"\b(?:Reclamante|Reclamad[oa]|Autor[a]?|R[ée]u|Requerente|Requerid[oa]|Exequente|Executad[oa]|Agravante|Agravad[oa]|Recorrente|Recorrid[oa]|Embargante|Embargad[oa]|Testemunha|Perit[oa]|Preposto|Sr\.?|Sra\.?|Senhor[a]?)\s*[:\-–]?\s*(" + NOME_QQ + r")")

STOP_PESSOA = {"VARA DO TRABALHO", "TRIBUNAL REGIONAL", "PODER JUDICIÁRIO", "JUSTIÇA DO TRABALHO", "PROCESSO JUDICIAL", "RECLAMAÇÃO TRABALHISTA", "DOS FATOS", "DO DIREITO", "DOS PEDIDOS", "TERMO DE AUDIÊNCIA", "PETIÇÃO INICIAL"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


def mask_doc(s: str) -> str:
    """Minimização LGPD: CPF nunca é armazenado em claro; CNPJ é mantido (dado de pessoa jurídica)."""
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11:
        return f"***.{digits[3:6]}.{digits[6:9]}-**"
    return s


def find_cnj(text: str) -> List[str]:
    out = []
    for m in CNJ_RE.finditer(text):
        out.append("{}-{}.{}.{}.{}.{}".format(*m.groups()))
    return out


def parse_date(text: str):
    m = DATA_RE.search(text)
    if not m:
        return None
    d, mo, y = m.groups()
    mo_l = mo.lower()
    mon = MESES.get(mo_l) if not mo.isdigit() else int(mo)
    try:
        return f"{int(y):04d}-{int(mon):02d}-{int(d):02d}"
    except Exception:
        return None


def extract_entities(text: str) -> Dict[str, List[str]]:
    ents: Dict[str, set] = {k: set() for k in ("pessoas", "organizacoes", "juizes", "varas", "tribunais", "fundamentos", "funcoes", "advogados", "cnpj")}
    for m in ORG_RE.finditer(text):
        v = re.sub(r"\s+", " ", m.group(1)).strip(" ,.;:-")
        if 4 < len(v) < 90:
            ents["organizacoes"].add(v)
    for m in JUIZ_RE.finditer(text):
        ents["juizes"].add(_tc(m.group(1)))
    for m in VARA_RE.finditer(text):
        ents["varas"].add(_tc(m.group(1)))
    for m in TRIB_RE.finditer(text):
        ents["tribunais"].add(_tc(m.group(1)))
    for m in FUND_RE.finditer(text):
        v = re.sub(r"\s+", " ", m.group(1)).strip()
        if len(v) > 5:
            ents["fundamentos"].add(v)
    for m in FUNCAO_RE.finditer(text):
        v = m.group(1).strip().lower()
        if 3 < len(v) < 50 and not v.startswith(("que", "para", "pela", "com")):
            ents["funcoes"].add(v)
    for m in ADV_RE.finditer(text):
        ents["advogados"].add(f"{_tc(m.group(1))} (OAB/{m.group(2).upper()} {m.group(3)})")
    for m in PESSOA_CTX_RE.finditer(text):
        bruto = m.group(1)
        v = _tc(bruto)
        if v.upper() not in STOP_PESSOA and not ORG_RE.search(bruto) and not ORG_RE.search(bruto.upper()) and len(v) < 80:
            ents["pessoas"].add(v)
    for m in CNPJ_RE.finditer(text):
        ents["cnpj"].add(m.group(0))
    return {k: sorted(v) for k, v in ents.items()}


def _tc(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip(" ,.;:-")
    if s.isupper():
        small = {"da", "de", "do", "das", "dos", "e"}
        return " ".join(w if w.lower() in small else w.capitalize() for w in s.lower().split())
    return s


TIPOS_DOC: List[Tuple[str, str]] = [
    (r"peti[çc][ãa]o\s+inicial|reclama[çc][ãa]o\s+trabalhista|reclamat[óo]ria", "Petição Inicial"),
    (r"contesta[çc][ãa]o|defesa", "Contestação"),
    (r"senten[çc]a", "Sentença"),
    (r"ac[óo]rd[ãa]o", "Acórdão"),
    (r"ata\s+de\s+audi[êe]ncia|termo\s+de\s+audi[êe]ncia", "Ata de Audiência"),
    (r"recurso\s+ordin[áa]rio", "Recurso Ordinário"),
    (r"recurso\s+de\s+revista", "Recurso de Revista"),
    (r"agravo\s+de\s+peti[çc][ãa]o", "Agravo de Petição"),
    (r"agravo\s+de\s+instrumento", "Agravo de Instrumento"),
    (r"embargos\s+de\s+declara[çc][ãa]o", "Embargos de Declaração"),
    (r"embargos\s+[àa]\s+execu[çc][ãa]o", "Embargos à Execução"),
    (r"impugna[çc][ãa]o\s+[àa]\s+senten[çc]a\s+de\s+liquida[çc][ãa]o", "Impugnação à Sentença de Liquidação"),
    (r"laudo\s+pericial|laudo\s+m[ée]dico|laudo", "Laudo Pericial"),
    (r"procura[çc][ãa]o", "Procuração"),
    (r"substabelecimento", "Substabelecimento"),
    (r"planilha|c[áa]lculo", "Planilha de Cálculo"),
    (r"termo\s+de\s+acordo|acordo", "Termo de Acordo"),
    (r"despacho", "Despacho"),
    (r"decis[ãa]o", "Decisão"),
    (r"certid[ãa]o", "Certidão"),
    (r"notifica[çc][ãa]o|intima[çc][ãa]o", "Notificação"),
    (r"manifesta[çc][ãa]o", "Manifestação"),
    (r"r[ée]plica", "Réplica"),
    (r"contrarraz[õo]es", "Contrarrazões"),
    (r"carta\s+de\s+preposi[çc][ãa]o", "Carta de Preposição"),
    (r"contrato\s+de\s+trabalho|ctps|carteira\s+de\s+trabalho", "Contrato de Trabalho"),
    (r"cart[ãa]o\s+de\s+ponto|controle\s+de\s+jornada|espelho\s+de\s+ponto", "Controle de Jornada"),
    (r"holerite|contracheque|recibo\s+de\s+pagamento", "Recibo de Pagamento"),
    (r"trct|termo\s+de\s+rescis[ãa]o", "TRCT"),
    (r"guia|gfip|fgts", "Guia / FGTS"),
]


def classify_doc(filename: str, first_text: str) -> str:
    base = norm(filename)
    head = norm(first_text[:1500])
    for pat, label in TIPOS_DOC:
        if re.search(pat, base):
            return label
    for pat, label in TIPOS_DOC:
        if re.search(pat, head):
            return label
    return "Documento"


def classify_fase(tipo: str, text: str) -> str:
    t = norm(text[:3000])
    if re.search(r"execu[cç][aã]o|penhora|bacenjud|sisbajud|bloqueio|arresto", t) or tipo in ("Agravo de Petição", "Embargos à Execução"):
        return "Execução"
    if re.search(r"liquida[cç][aã]o|c[aá]lculos? de liquida", t) or tipo in ("Planilha de Cálculo", "Impugnação à Sentença de Liquidação"):
        return "Liquidação"
    return "Conhecimento"
