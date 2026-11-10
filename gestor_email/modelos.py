"""
Modelos de e-mail do escritório (skill "modelos-de-e-mails-marques").

Lê o arquivo modelos/modelos-de-e-mails-marques.md e extrai cada modelo
(código, título, grupo, assunto, texto-base e blocos condicionais), para
uso no menu "/" da janela de escrita e no preenchimento por IA.
Para atualizar os modelos, basta substituir o arquivo .md.
"""
import os
import re
from functools import lru_cache
from typing import Dict, List

ARQUIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelos", "modelos-de-e-mails-marques.md")

_HEAD = re.compile(r"^\d+(?:-[A-Z])?\.\s+([A-Z]+-\d+)\s+—\s+(.+?)\s*$")
_MENU_ITEM = re.compile(r"^([A-Z]+-\d+)\s+—\s+(.+?)\s*$")
_BLOCO = re.compile(r"^(BLOCO_[A-Z0-9_]+)\s*$")
_VAR = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def texto_skill() -> str:
    with open(ARQUIVO, encoding="utf-8") as f:
        return f.read()


def _menu(linhas: List[str]) -> Dict[str, Dict[str, str]]:
    """Grupos e títulos do item 8 (MENU COMPLETO DE MODELOS)."""
    out: Dict[str, Dict[str, str]] = {}
    try:
        ini = next(i for i, l in enumerate(linhas) if l.startswith("8. MENU COMPLETO"))
    except StopIteration:
        return out
    grupo = ""
    for l in linhas[ini + 1:]:
        l = l.strip()
        if _HEAD.match(l):
            break
        m = _MENU_ITEM.match(l)
        if m:
            out[m.group(1)] = {"grupo": grupo, "titulo": m.group(2)}
        elif l and l.upper() == l and not l[0].isdigit():
            grupo = l[:1] + l[1:].lower()
            grupo = grupo.replace("(hte)", "(HTE)")
    return out


def _limpa(bloco: List[str]) -> str:
    texto = "\n".join(bloco).strip("\n")
    return re.sub(r"\n{3,}", "\n\n", texto)


def _desquebra(texto: str) -> str:
    """Junta as linhas quebradas a ~80 colunas do arquivo-fonte em parágrafos."""
    paras = []
    for p in re.split(r"\n\s*\n", texto):
        linhas = p.split("\n")
        out = [linhas[0]]
        for l in linhas[1:]:
            prev = out[-1]
            if len(prev) >= 55 and not prev.rstrip().endswith((":", ";")) and l[:1] not in ("-", "•"):
                out[-1] = prev.rstrip() + " " + l.lstrip()
            else:
                out.append(l)
        paras.append("\n".join(out))
    return "\n\n".join(paras)


_COND = re.compile(r"^(somente|usar|quando|se |apenas|caso|incluir)", re.I)


def _separa_condicao(texto: str):
    """Primeiro parágrafo de um bloco costuma ser a condição de uso ("Somente se houver link:")."""
    partes = re.split(r"\n\s*\n", texto, maxsplit=1)
    if len(partes) == 2 and (partes[0].strip().endswith(":") or _COND.match(partes[0].strip())):
        return partes[0].strip(), partes[1]
    return "", texto


_REGRA_FINAL = re.compile(r"^(REGRA|OBSERVAÇÃO|OBSERVACAO|NOTA|ATENÇÃO)[A-ZÀ-Ú \-]*$")


def _separa_regras_finais(texto: str):
    """Regras escritas depois da assinatura (ex.: "REGRA CRÍTICA") não entram no e-mail."""
    linhas = texto.split("\n")
    for k, l in enumerate(linhas):
        if _REGRA_FINAL.match(l.strip()):
            return "\n".join(linhas[:k]).rstrip(), "\n".join(linhas[k:]).strip()
    return texto, ""


def _secao_romana(corpo: str, numeral: str) -> str:
    """Trecho de uma seção "III." / "IV." de um modelo (para expandir referências)."""
    linhas = corpo.split("\n")
    ini = next((k for k, l in enumerate(linhas) if l.startswith(numeral + ".")), None)
    if ini is None:
        return ""
    fim = len(linhas)
    for k in range(ini + 1, len(linhas)):
        l = linhas[k]
        if re.match(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X)\.", l) or l.startswith("{{") or l.startswith(("Ficamos", "Desde já", "Atenciosamente", "Permanecemos")):
            fim = k
            break
    return "\n".join(linhas[ini:fim]).strip()


@lru_cache(maxsize=1)
def carregar() -> List[Dict]:
    linhas = texto_skill().splitlines()
    menu = _menu(linhas)
    fim = next((i for i, l in enumerate(linhas) if l.startswith("44. SELEÇÃO AUTOMÁTICA")), len(linhas))
    heads = [(i, _HEAD.match(l)) for i, l in enumerate(linhas[:fim]) if _HEAD.match(l)]
    modelos = []
    for n, (i, m) in enumerate(heads):
        j = heads[n + 1][0] if n + 1 < len(heads) else fim
        corpo = linhas[i + 1:j]
        status = next((l.split(":", 1)[1].strip() for l in corpo if l.startswith("Status:")), "")
        corpo = [l for l in corpo if not l.startswith("Status:")]
        regras = ""
        idx_base = next((k for k, l in enumerate(corpo) if l.strip() == "TEXTO-BASE"), None)
        if idx_base is not None:
            regras = _limpa(corpo[:idx_base])
            corpo = corpo[idx_base + 1:]
        # Blocos condicionais (definidos após o texto-base)
        blocos: Dict[str, str] = {}
        texto: List[str] = []
        atual = None
        for l in corpo:
            b = _BLOCO.match(l.strip())
            if b:
                atual = b.group(1)
                blocos[atual] = []
                continue
            (blocos[atual] if atual else texto).append(l)
        assunto = ""
        for k, l in enumerate(texto):
            if l.startswith("Assunto:"):
                assunto = l.split(":", 1)[1].strip()
                del texto[k]
                break
        corpo_txt, regras_finais = _separa_regras_finais(_limpa(texto))
        # Parágrafos "REGRA: ..." no meio do texto são orientações internas, não vão no e-mail
        paras, internas = [], []
        for par in re.split(r"\n\s*\n", corpo_txt):
            (internas if par.strip().upper().startswith("REGRA") else paras).append(par)
        corpo_txt = "\n\n".join(paras)
        regras = "\n\n".join(x for x in (regras, *internas, regras_finais) if x)
        code = m.group(1)
        info = menu.get(code, {})
        modelos.append({
            "codigo": code,
            "titulo": info.get("titulo") or m.group(2).title(),
            "grupo": info.get("grupo", ""),
            "status": status,
            "assunto": assunto,
            "corpo": corpo_txt,
            "regras": regras,
            "blocos": {k: _limpa(v) for k, v in blocos.items()},
        })
    # Blocos definidos em um modelo e usados em outro (ex.: BLOCO_LINK)
    globais: Dict[str, str] = {}
    for md in modelos:
        for k, v in md["blocos"].items():
            globais.setdefault(k, v)
    por_cod = {md["codigo"]: md for md in modelos}
    ref = re.compile(r"^Usar integralmente a relação dos itens (\d+) a (\d+) do ([A-Z]+-\d+)\.?\s*$", re.M)
    for md in modelos:
        def expande(mt):
            alvo = por_cod.get(mt.group(3))
            if not alvo:
                return mt.group(0)
            numeral = "III" if int(mt.group(1)) == 1 else "IV"
            trecho = _secao_romana(alvo["corpo"], numeral)
            # remove o título da seção, que o modelo atual já tem
            return trecho.split("\n", 1)[1].strip() if "\n" in trecho else mt.group(0)
        md["corpo"] = ref.sub(expande, md["corpo"])
        usados = set(re.findall(r"\{\{(BLOCO_[A-Z0-9_]+)\}\}", md["corpo"]))
        blocos = {}
        for b in usados:
            raw = md["blocos"].get(b) or globais.get(b, "")
            cond, txt = _separa_condicao(raw)
            blocos[b] = {"condicao": cond, "texto": _desquebra(txt)}
        md["blocos"] = blocos
        md["corpo"] = _desquebra(md["corpo"])
        txt_total = md["assunto"] + "\n" + md["corpo"] + "\n" + "\n".join(b["texto"] for b in blocos.values())
        # Campos na ordem em que aparecem no texto (assunto, corpo e blocos)
        vistos: List[str] = []
        for v in _VAR.findall(txt_total):
            if not v.startswith("BLOCO_") and v not in vistos:
                vistos.append(v)
        md["campos"] = vistos
    return modelos


def por_codigo(codigo: str) -> Dict:
    return next((m for m in carregar() if m["codigo"] == codigo), None)
