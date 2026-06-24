"""
Cruza threads do Gmail (SQLite) com processos/tarefas do Projuris.
Uso: python check_projuris.py TOKEN
"""
import sys, json, re, sqlite3, urllib.request, urllib.parse, time

TOKEN   = sys.argv[1]
DB_PATH = r"C:\Users\advogados\Claude\2. Docs. Defesa\gmail_monitor\Relatorios\gmail_monitor.db"
BASE    = "https://api.projurisadv.com.br/adv-service"

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

# ── regex para número CNJ (0000000-00.0000.0.00.0000) ──────────────────────
CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")


def api_get(path):
    url = BASE + path
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_msg": e.reason}
    except Exception as e:
        return {"_error": str(e)}


def search_processo(numero_cnj):
    enc = urllib.parse.quote(numero_cnj)
    return api_get(f"/processo?numeroProcesso={enc}&size=5")


def search_tarefas(processo_id):
    return api_get(f"/tarefa?processoId={processo_id}&size=10&sort=dataLimite,asc")


def buscar_tarefas_abertas_geral():
    """Busca todas tarefas abertas/pendentes para cruzamento por assunto."""
    return api_get("/tarefa?size=50&sort=dataLimite,asc")


# ── lê threads do SQLite ────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT id FROM execucoes ORDER BY id DESC LIMIT 1")
row = c.fetchone()
if not row:
    print("[]"); sys.exit(0)

eid = row[0]
c.execute("""
    SELECT DISTINCT sender, subject, tipo, hours_since_last, snippet
    FROM threads
    WHERE execucao_id=? AND category != 'COMERCIAL'
    ORDER BY hours_since_last DESC
""", (eid,))
threads = [dict(r) for r in c.fetchall()]
conn.close()

print(f"[INFO] {len(threads)} threads carregadas do SQLite", file=sys.stderr)

# ── busca tarefas abertas no Projuris para cruzamento ───────────────────────
print("[INFO] Buscando tarefas abertas no Projuris...", file=sys.stderr)
tarefas_resp = buscar_tarefas_abertas_geral()
tarefas_list = tarefas_resp if isinstance(tarefas_resp, list) else tarefas_resp.get("content", [])
print(f"[INFO] {len(tarefas_list)} tarefas retornadas", file=sys.stderr)

# monta set de palavras-chave das tarefas (assunto/descrição)
def words(text):
    return set(re.findall(r"\w{4,}", (text or "").lower()))

tarefas_words = []
for t in tarefas_list:
    desc  = (t.get("descricao") or t.get("titulo") or t.get("assunto") or "").lower()
    prazo = t.get("dataLimite") or t.get("prazo") or ""
    tarefas_words.append({"desc": desc, "prazo": prazo, "raw": t})


# ── cruza cada thread com Projuris ──────────────────────────────────────────
results = []
for th in threads:
    subj    = th["subject"]
    text    = (subj + " " + (th.get("snippet") or "")).lower()
    cnj_hit = CNJ_RE.findall(text)

    projuris_status = "NÃO ENCONTRADO"
    projuris_info   = ""
    processo_id     = None

    # 1. busca por número CNJ se encontrado no assunto/snippet
    if cnj_hit:
        numero = cnj_hit[0]
        resp = search_processo(numero)
        content = resp if isinstance(resp, list) else resp.get("content", [])
        if content:
            p = content[0]
            processo_id = p.get("id")
            projuris_status = "PROCESSO ENCONTRADO"
            projuris_info   = f"Nº {p.get('numeroProcesso','')} | {p.get('fase','') or p.get('situacao','')}"
            # verifica tarefas do processo
            t_resp = search_tarefas(processo_id)
            t_list = t_resp if isinstance(t_resp, list) else t_resp.get("content", [])
            abertas = [t for t in t_list if str(t.get("situacao","")).upper() not in ("CONCLUIDA","CANCELADA")]
            if abertas:
                projuris_status = "PROCESSO + TAREFA OK"
                prazos = ", ".join(t.get("dataLimite","") or "" for t in abertas[:3])
                projuris_info += f" | Tarefas: {len(abertas)} | Prazo(s): {prazos}"
            else:
                projuris_status = "PROCESSO SEM TAREFA ⚠️"
                projuris_info  += " | Nenhuma tarefa aberta cadastrada"
        time.sleep(0.13)  # respeitar rate limit

    # 2. cruzamento por palavras-chave com tarefas abertas
    else:
        w_email = words(subj)
        melhor  = None
        melhor_score = 0
        for tw in tarefas_words:
            score = len(w_email & words(tw["desc"]))
            if score > melhor_score:
                melhor_score = score
                melhor = tw
        if melhor and melhor_score >= 2:
            projuris_status = "TAREFA RELACIONADA"
            projuris_info   = f"Match: {melhor_score} palavras | Prazo: {melhor['prazo']} | {melhor['desc'][:80]}"
        else:
            projuris_status = "NÃO ENCONTRADO"
            projuris_info   = "Nenhum processo ou tarefa correspondente no Projuris"

    results.append({
        "sender":          th["sender"],
        "subject":         subj,
        "tipo":            th.get("tipo","CLIENTE"),
        "hours":           th["hours_since_last"],
        "cnj":             cnj_hit[0] if cnj_hit else "",
        "projuris_status": projuris_status,
        "projuris_info":   projuris_info,
    })

print(json.dumps(results, ensure_ascii=False, indent=2))
