"""
Integridade da sincronização Gmail → MarquesPro.

Objetivo: o escritório precisa de certeza de que tudo o que chega no Gmail também chega aqui.
Três camadas:
 1. Cada sincronização registra sucesso/falha (erro de autorização, rede, cota) e quantas falhas seguidas.
 2. Verificação cruzada: lista no Gmail (inclusive spam/lixeira) tudo o que chegou na janela e confere,
    um a um, se está no cache. O que faltar é trazido na hora e registrado como "recuperado".
 3. Estado visível: semáforo (ok / atenção / erro) calculado só com dados locais, mostrado no topo
    da tela, e histórico dos eventos.
"""
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import auth, config, db, gmail_ops

INTERVALO_VERIFICACAO = 300      # verificação rápida (últimos 2 dias) a cada 5 min
INTERVALO_PROFUNDA = 6 * 3600    # verificação da janela inteira a cada 6 h
MAX_LISTA = 5000

_AUTH = re.compile(r"invalid_grant|refresherror|token has been (expired|revoked)|unauthorized|\b401\b|invalid_client|credentials", re.I)
_REDE = re.compile(r"connection|timed? ?out|timeout|getaddrinfo|name resolution|max retries|ssl|network|unreachable|\b50[234]\b", re.I)
_COTA = re.compile(r"\b429\b|ratelimit|rate limit|quota|userratelimit", re.I)


def classificar_erro(msg: str) -> str:
    m = msg or ""
    if _AUTH.search(m):
        return "autorizacao"
    if _COTA.search(m):
        return "cota"
    if _REDE.search(m):
        return "rede"
    return "outro"


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _idade(ts: Optional[str]) -> Optional[float]:
    if not ts:
        return None
    try:
        return (datetime.now() - datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")).total_seconds()
    except ValueError:
        return None


def registrar(account: str, nivel: str, evento: str, detalhe: str = ""):
    db.execute("INSERT INTO sync_log (account, nivel, evento, detalhe) VALUES (?,?,?,?)", (account, nivel, evento, detalhe[:500]))
    db.execute("DELETE FROM sync_log WHERE id <= (SELECT MAX(id) FROM sync_log) - 300")


def _estado_conta(account: str) -> Dict[str, Any]:
    db.execute("INSERT OR IGNORE INTO integridade (account) VALUES (?)", (account,))
    return db.one("SELECT * FROM integridade WHERE account=?", (account,))


def registrar_sync(account: str, ok: bool, erro: str = ""):
    """Chamado ao fim de cada sincronização."""
    e = _estado_conta(account)
    if ok:
        if e["falhas_seguidas"]:
            registrar(account, "info", "sync_normalizada", f"Voltou a sincronizar após {e['falhas_seguidas']} falha(s).")
        db.execute("UPDATE integridade SET falhas_seguidas=0, ultimo_erro=NULL, erro_tipo=NULL WHERE account=?", (account,))
    else:
        tipo = classificar_erro(erro)
        db.execute("UPDATE integridade SET falhas_seguidas=falhas_seguidas+1, ultimo_erro=?, erro_tipo=? WHERE account=?",
                   (erro[:500], tipo, account))
        registrar(account, "erro", f"sync_falhou_{tipo}", erro)


def verificar(account: str, dias: int = 2, service=None) -> Dict[str, Any]:
    """Confere Gmail × cache dos últimos `dias` dias e traz o que estiver faltando."""
    from . import sync, triagem   # import tardio: sync também usa este módulo
    profunda = dias > 3
    _estado_conta(account)
    try:
        service = service or auth.get_service(account)
        desde = int(time.time()) - dias * 86400
        ids: List[str] = []
        page = None
        while len(ids) < MAX_LISTA:
            params = {"userId": "me", "q": f"after:{desde}", "includeSpamTrash": True, "maxResults": 500}
            if page:
                params["pageToken"] = page
            resp = service.users().messages().list(**params).execute()
            ids.extend(m["id"] for m in resp.get("messages", []) or [])
            page = resp.get("nextPageToken")
            if not page:
                break
        ids = list(dict.fromkeys(ids))
        gmail = set(ids)

        # 1) No Gmail e fora do cache → traz agora
        faltam = [i for i in ids if not db.message_exists(account, i)]
        recuperados = 0
        if faltam:
            found, _ = gmail_ops.get_metadata_batch(service, faltam)
            recuperados = sync._store(service, account, found, notify=True, rules=True)
            triagem.revisar_spam(account)
            registrar(account, "aviso", "recuperado",
                      f"{len(faltam)} e-mail(s) estavam no Gmail e não tinham chegado aqui; recuperados: {len(found)}. "
                      + "; ".join(f"{(f.get('payload', {}).get('headers') and next((h['value'] for h in f['payload']['headers'] if h['name'].lower() == 'subject'), '')) or '(sem assunto)'}" for f in found[:3]))
        # 2) No cache (na janela) e fora do Gmail → confirma se foi apagado
        locais = [r["id"] for r in db.rows("SELECT id FROM messages WHERE account=? AND internal_date>=?", (account, desde * 1000))
                  if r["id"] not in gmail][:300]
        removidos = 0
        if locais:
            achadas, ausentes = gmail_ops.get_metadata_batch(service, locais)
            for mid in ausentes:
                db.delete_message(account, mid)
                removidos += 1
            if achadas:
                sync._store(service, account, achadas, notify=False, rules=False)   # só atualiza etiquetas
        trouxe = sum(1 for i in ids if db.message_exists(account, i))
        pendentes = len(ids) - trouxe
        ult_local = db.one("SELECT MAX(internal_date) AS d FROM messages WHERE account=? AND internal_date>=?", (account, desde * 1000))["d"]
        agora = _agora()
        db.execute(
            "UPDATE integridade SET ultima_verificacao=?, gmail_n=?, local_n=?, ultimo_local_ms=?, "
            "recuperados_total=recuperados_total+?, "
            + ("ultima_profunda=?, " if profunda else "") + "janela_dias=? WHERE account=?",
            [agora, len(ids), trouxe, ult_local, len(faltam) - pendentes] + ([agora] if profunda else []) + [dias, account])
        if pendentes:
            registrar(account, "erro", "faltando", f"{pendentes} e-mail(s) do Gmail não puderam ser trazidos nesta verificação.")
            db.execute("UPDATE integridade SET ultimo_erro=?, erro_tipo='faltando' WHERE account=?",
                       (f"{pendentes} e-mail(s) do Gmail ainda não chegaram aqui", account))
        else:
            db.execute("UPDATE integridade SET ultima_ok=? WHERE account=?", (agora, account))
            if (_estado_conta(account) or {}).get("erro_tipo") == "faltando":
                db.execute("UPDATE integridade SET ultimo_erro=NULL, erro_tipo=NULL WHERE account=?", (account,))
        return {"account": account, "gmail": len(ids), "aqui": trouxe, "recuperados": len(faltam) - pendentes,
                "removidos": removidos, "pendentes": pendentes, "dias": dias}
    except Exception as e:
        registrar_sync(account, False, f"Verificação cruzada: {e}")
        db.execute("UPDATE integridade SET ultima_verificacao=? WHERE account=?", (_agora(), account))
        return {"account": account, "erro": str(e)[:300]}


def rotina(account: str, forcar: bool = False) -> Optional[Dict[str, Any]]:
    """Roda a verificação quando está na hora (chamado após cada sincronização bem-sucedida)."""
    e = _estado_conta(account)
    idade_p, idade_v = _idade(e["ultima_profunda"]), _idade(e["ultima_verificacao"])
    if forcar or idade_p is None or idade_p >= INTERVALO_PROFUNDA:
        return verificar(account, config.SYNC_DAYS)
    if idade_v is None or idade_v >= INTERVALO_VERIFICACAO:
        return verificar(account, 2)
    return None


def reconhecer():
    db.set_setting("integridade_ack", _agora())


# ─── Estado exibido na tela (só dados locais) ─────────────────────────────────────

_ORDEM = {"ok": 0, "atencao": 1, "erro": 2}
_MSG_ERRO = {
    "autorizacao": "A autorização desta conta no Google expirou ou foi revogada. Reconecte a conta em Configurações → Contas.",
    "rede": "Sem conexão com o Gmail (internet ou Google indisponível).",
    "cota": "O Google limitou temporariamente as consultas (cota). A sincronização tenta de novo sozinha.",
    "faltando": "Há e-mails no Gmail que não conseguiram chegar aqui.",
    "outro": "A sincronização com o Gmail falhou.",
}


def estado() -> Dict[str, Any]:
    contas: List[Dict[str, Any]] = []
    ack = db.get_setting("integridade_ack") or ""
    limite_parada = max(3 * config.SYNC_INTERVAL_SECONDS, 240)
    for email in auth.list_accounts():
        e = _estado_conta(email)
        st = db.account_state(email) or {}
        nivel, msg, acao = "ok", "Tudo sincronizado: o que chega no Gmail está chegando aqui.", None
        idade_sync = _idade(st.get("last_sync"))
        if e["erro_tipo"] == "autorizacao":
            nivel, msg, acao = "erro", _MSG_ERRO["autorizacao"], "reconectar"
        elif e["falhas_seguidas"] >= 2 or e["erro_tipo"] == "faltando":
            nivel, msg, acao = "erro", _MSG_ERRO.get(e["erro_tipo"] or "outro", _MSG_ERRO["outro"]), "verificar"
        elif idade_sync is None:
            nivel, msg, acao = "atencao", "Esta conta ainda não terminou a primeira sincronização.", "verificar"
        elif idade_sync > limite_parada:
            nivel, msg, acao = "erro", f"A sincronização está parada há {int(idade_sync // 60)} min. Novos e-mails podem não estar aparecendo.", "verificar"
        elif e["falhas_seguidas"] == 1:
            nivel, msg, acao = "atencao", _MSG_ERRO.get(e["erro_tipo"] or "outro", _MSG_ERRO["outro"]) + " Nova tentativa em instantes.", "verificar"
        else:
            rec = db.one("SELECT COUNT(*) AS n, MAX(detalhe) AS d FROM sync_log WHERE account=? AND evento='recuperado' AND ts>?", (email, ack))
            idade_v = _idade(e["ultima_verificacao"])
            if rec["n"]:
                nivel, msg, acao = "atencao", "E-mails que não tinham chegado foram recuperados automaticamente. Veja os detalhes.", "reconhecer"
            elif idade_v is None or idade_v > 3 * INTERVALO_VERIFICACAO:
                nivel, msg, acao = "atencao", "A verificação cruzada com o Gmail está atrasada.", "verificar"
        contas.append({
            "email": email, "nivel": nivel, "mensagem": msg, "acao": acao,
            "ultima_sync": st.get("last_sync"), "ultima_verificacao": e["ultima_verificacao"], "ultima_ok": e["ultima_ok"],
            "gmail_n": e["gmail_n"], "aqui_n": e["local_n"], "janela_dias": e["janela_dias"],
            "recuperados_total": e["recuperados_total"], "falhas_seguidas": e["falhas_seguidas"], "erro": e["ultimo_erro"],
        })
    if not contas:
        geral = {"nivel": "atencao", "mensagem": "Nenhuma conta do Gmail conectada.", "acao": "reconectar"}
    else:
        pior = max(contas, key=lambda c: _ORDEM[c["nivel"]])
        geral = {"nivel": pior["nivel"], "mensagem": pior["mensagem"] if pior["nivel"] != "ok" else contas[0]["mensagem"],
                 "acao": pior["acao"], "conta": pior["email"] if pior["nivel"] != "ok" else None}
    return dict(geral, contas=contas)


def eventos(limite: int = 40) -> List[Dict[str, Any]]:
    return db.rows("SELECT ts, account, nivel, evento, detalhe FROM sync_log ORDER BY id DESC LIMIT ?", (limite,))
