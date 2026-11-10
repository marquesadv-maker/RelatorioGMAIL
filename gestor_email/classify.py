"""
Classificação de notificações (intimações, citações, publicações etc.).

Reutiliza a mesma regra do analyzer.py do gmail_monitor (tipo TRIBUNAL),
para que o contador do Gestor e o relatório da controladoria coincidam.
"""
import os
import re
import sys
import unicodedata
from typing import Dict, Optional, Tuple

from . import config

if config.PROJECT_DIR not in sys.path:
    sys.path.insert(0, config.PROJECT_DIR)

try:
    from analyzer import detect_tipo as _detect_tipo  # mesmo critério do monitor
except Exception:  # analyzer.py ausente: usa critério mínimo próprio
    _detect_tipo = None

# Subtipos exibidos no contador (primeira correspondência no assunto/trecho)
SUBTIPOS = [
    ("Intimação", ("intimação", "intimacao", "intimad")),
    ("Citação", ("citação", "citacao", "citad")),
    ("Audiência", ("audiência", "audiencia", "pauta")),
    ("Decisão / Sentença", ("sentença", "sentenca", "decisão", "decisao", "acórdão", "acordao", "despacho")),
    ("Publicação / DJE", ("publicação", "publicacao", "diário oficial", "diario oficial", "dje")),
    ("Prazo", ("prazo",)),
]

_FALLBACK_SENDERS = ("pje", "esaj", "projudi", "eproc", "tribunal", ".jus.br", "dje")
_FALLBACK_SUBJECTS = ("intimação", "intimacao", "citação", "citacao", "publicação", "publicacao")


def classify(from_raw: str, subject: str, snippet: str) -> Tuple[str, Optional[str]]:
    """Retorna (tipo, subtipo). tipo segue o analyzer: TRIBUNAL, DUVIDA, DEFESA, COMERCIAL, CLIENTE."""
    if _detect_tipo is not None:
        tipo = _detect_tipo({"subject": subject or "", "snippet": snippet or "",
                             "sender_raw": from_raw or "", "sender": from_raw or ""})
    else:
        s, sub = (from_raw or "").lower(), (subject or "").lower()
        tipo = "TRIBUNAL" if any(x in s for x in _FALLBACK_SENDERS) or any(x in sub for x in _FALLBACK_SUBJECTS) else "CLIENTE"
    subtipo = None
    if tipo == "TRIBUNAL":
        text = f"{subject} {snippet}".lower()
        subtipo = next((nome for nome, chaves in SUBTIPOS if any(c in text for c in chaves)), "Outras")
    return tipo, subtipo


# ─── Prioridade de leitura ─────────────────────────────────────────────────────
# Assuntos que o escritório precisa ler primeiro. Procura no assunto e no começo do texto,
# sem diferenciar maiúsculas nem acentos. (nome exibido, expressão sobre o texto sem acentos)
PRIORIDADES = [
    ("DJE", r"\bdje\b|diario (?:da justica|de justica|oficial)(?: eletronico)?"),
    ("Domicílio Judicial", r"domicilio judicial(?: eletronico)?"),
    ("MPT", r"ministerio publico do trabalho|\bmpt\b"),
    ("Intimação", r"\bintima(?:cao|coes|do|da|dos|das)\b|\bintimar\b"),
    ("Contrato", r"solicit\w*[^.\n]{0,30}\bcontrato|\bcontrato\b[^.\n]{0,30}solicit"),
    ("Parecer", r"solicit\w*[^.\n]{0,30}\bparecer|\bparecer\b[^.\n]{0,30}solicit"),
]
_PRIO_RE = [(nome, re.compile(rx)) for nome, rx in PRIORIDADES]
PRIO_VERSAO = 1


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFD", (t or "").lower()).encode("ascii", "ignore").decode()


def prioridade(subject: str, snippet: str) -> Optional[str]:
    """Categorias de prioridade encontradas (separadas por "|") ou None."""
    texto = _sem_acento(f"{subject or ''}. {snippet or ''}")
    achadas = [nome for nome, rx in _PRIO_RE if rx.search(texto)]
    return "|".join(achadas) if achadas else None
