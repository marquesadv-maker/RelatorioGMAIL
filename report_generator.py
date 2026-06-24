import os
import sqlite3
from datetime import datetime, date
from typing import Dict, List, Any

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "Relatorios")
DB_PATH     = os.path.join(REPORTS_DIR, "gmail_monitor.db")


# ─── BANCO DE DADOS ───────────────────────────────────────────────────────────

def _fmt_hours(h: float) -> str:
    if h < 1:   return "menos de 1h"
    if h < 24:  return f"{h:.0f}h"
    days = int(h // 24); rem = int(h % 24)
    return f"{days}d {rem}h" if rem else f"{days}d"


def init_db():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS execucoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL, gerado_em TEXT NOT NULL,
        total_alta INTEGER, total_media INTEGER, total_baixa INTEGER,
        total_insatisfeitos INTEGER, total_sem_resposta_48h INTEGER,
        total_tribunal INTEGER DEFAULT 0, total_duvida INTEGER DEFAULT 0,
        total_defesa INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS threads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        execucao_id INTEGER, thread_id TEXT, sender TEXT, subject TEXT,
        priority TEXT, hours_since_last REAL, reason TEXT,
        dissatisfaction_risk TEXT, snippet TEXT, urgency_keywords TEXT,
        category TEXT, tipo TEXT DEFAULT 'CLIENTE',
        FOREIGN KEY (execucao_id) REFERENCES execucoes(id)
    )""")
    # migrações seguras
    for col, defn in [
        ("total_tribunal", "INTEGER DEFAULT 0"),
        ("total_duvida",   "INTEGER DEFAULT 0"),
        ("total_defesa",   "INTEGER DEFAULT 0"),
        ("tipo",           "TEXT DEFAULT 'CLIENTE'"),
    ]:
        try:
            c.execute(f"ALTER TABLE execucoes ADD COLUMN {col} {defn}")
        except Exception:
            pass
        try:
            c.execute(f"ALTER TABLE threads ADD COLUMN {col} {defn}")
        except Exception:
            pass
    conn.commit(); conn.close()


def save_to_db(results: Dict[str, List[Dict]], today: date = None) -> int:
    if today is None: today = date.today()
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""INSERT INTO execucoes
        (data,gerado_em,total_alta,total_media,total_baixa,total_insatisfeitos,
         total_sem_resposta_48h,total_tribunal,total_duvida,total_defesa)
        VALUES (?,?,?,?,?,?,?,?,?,?)""", (
        today.isoformat(), now_str,
        len(results["ALTA"]), len(results["MÉDIA"]), len(results["BAIXA"]),
        len(results["dissatisfied"]), len(results["unanswered_48h"]),
        len(results.get("tribunal", [])), len(results.get("duvida", [])),
        len(results.get("defesa", [])),
    ))
    eid = c.lastrowid

    def ins(threads, cat):
        for t in threads:
            c.execute("""INSERT INTO threads
                (execucao_id,thread_id,sender,subject,priority,hours_since_last,
                 reason,dissatisfaction_risk,snippet,urgency_keywords,category,tipo)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (
                eid, t.get("thread_id",""), t.get("sender",""), t.get("subject",""),
                t.get("priority",""), t.get("hours_since_last",0), t.get("reason",""),
                t.get("dissatisfaction_risk",""), (t.get("snippet","") or "")[:300],
                ", ".join(t.get("urgency_keywords",[])), cat,
                t.get("tipo","CLIENTE"),
            ))

    ins(results["ALTA"],           "ALTA")
    ins(results["MÉDIA"],          "MEDIA")
    ins(results["BAIXA"],          "BAIXA")
    ins(results["dissatisfied"],   "INSATISFEITO")
    ins(results["unanswered_48h"], "SEM_RESPOSTA_48H")
    ins(results.get("tribunal",[]),"TRIBUNAL")
    ins(results.get("duvida",[]),  "DUVIDA")
    ins(results.get("defesa",[]),  "DEFESA")

    conn.commit(); conn.close()
    return eid


# ─── COMPATIBILIDADE ──────────────────────────────────────────────────────────

def generate_report(results, today=None): return ""
def save_report(content, today=None):     return ""


def generate_and_save(results: Dict[str, List[Dict]], today: date = None) -> str:
    if today is None: today = date.today()
    save_to_db(results, today)
    path = save_dashboard(today)
    save_index()
    return path


# ─── CSS ──────────────────────────────────────────────────────────────────────

CSS = """
:root{
  --bg:#f0f4f8; --surface:#ffffff; --surface2:#f8fafc; --surface3:#eef2f7;
  --navy:#0d2137; --navy2:#1a3a5c; --navy3:#0a1929;
  --gold:#c9a84c; --gold2:#a8872e; --gold3:#f0d080;
  --alta:#dc2626; --media:#d97706; --baixa:#16a34a;
  --insat:#7c3aed; --semresp:#2563eb; --tribunal:#0891b2;
  --duvida:#0d9488; --defesa:#7c3aed;
  --text:#0d2137; --muted:#4b6280; --border:#cbd5e1; --border2:#e2e8f0;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh}
a{color:inherit;text-decoration:none}

/* ── AVISO ── */
.aviso{background:var(--alta);color:#fff;text-align:center;padding:.55rem 1rem;
       font-size:.8rem;font-weight:700;letter-spacing:.03em;position:sticky;top:0;z-index:20}

/* ── NAV ── */
nav{background:var(--navy);border-bottom:3px solid var(--gold);
    display:flex;align-items:center;gap:.5rem;padding:.65rem 1.25rem;
    position:sticky;top:2rem;z-index:15;flex-wrap:wrap}
.logo{font-weight:800;font-size:1rem;color:var(--gold);margin-right:auto;letter-spacing:.04em}
nav button{background:none;border:1px solid rgba(201,168,76,.35);color:#cbd5e1;
           padding:.38rem .85rem;border-radius:6px;cursor:pointer;font-size:.78rem;
           font-weight:600;transition:.15s;white-space:nowrap}
nav button.active,nav button:hover{background:var(--gold);color:var(--navy);border-color:var(--gold)}
.nav-badge{display:inline-block;background:var(--alta);color:#fff;border-radius:99px;
           font-size:.65rem;padding:.05rem .35rem;margin-left:.3rem;font-weight:700}
.nav-badge.gold{background:var(--gold);color:var(--navy)}

/* ── PAGES ── */
.page{display:none;padding:1.5rem;max-width:1400px;margin:0 auto}
.page.active{display:block}

/* ── HEADER ── */
.page-header{margin-bottom:1.25rem}
.page-header h1{font-size:1.3rem;color:var(--navy);font-weight:800}
.page-header .meta{font-size:.78rem;color:var(--muted);margin-top:.2rem}
.gold-line{height:3px;background:linear-gradient(90deg,var(--gold),transparent);
           border-radius:2px;margin:.5rem 0 1.25rem}

/* ── KPIs ── */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:.85rem;margin-bottom:1.25rem}
.kpi{background:var(--surface);border-radius:10px;padding:.9rem 1.1rem;
     border-top:4px solid;box-shadow:0 1px 4px rgba(13,33,55,.08)}
.kpi.alta{border-color:var(--alta)}  .kpi.media{border-color:var(--media)}
.kpi.baixa{border-color:var(--baixa)} .kpi.insat{border-color:var(--insat)}
.kpi.semresp{border-color:var(--semresp)} .kpi.tribunal{border-color:var(--tribunal)}
.kpi.duvida{border-color:var(--duvida)} .kpi.defesa{border-color:var(--defesa)}
.kpi-num{font-size:1.9rem;font-weight:800;line-height:1;color:var(--navy)}
.kpi-label{font-size:.72rem;color:var(--muted);margin-top:.25rem;font-weight:600}

/* ── SECTION ── */
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem;margin-bottom:1rem}
.section{background:var(--surface);border-radius:10px;padding:1.1rem 1.25rem;margin-bottom:1rem;
         box-shadow:0 1px 4px rgba(13,33,55,.07)}
.section h2{font-size:.88rem;font-weight:700;color:var(--navy);margin-bottom:.85rem;
            display:flex;align-items:center;gap:.5rem;padding-bottom:.5rem;
            border-bottom:2px solid var(--border2)}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;flex-shrink:0}

/* ── CARDS ── */
.card{background:var(--surface2);border-radius:8px;padding:.8rem .95rem;margin-bottom:.5rem;
      border:1px solid var(--border2);transition:.12s}
.card:hover{border-color:var(--gold);box-shadow:0 2px 8px rgba(201,168,76,.15)}
.card-header{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap;margin-bottom:.2rem}
.sender{font-weight:700;font-size:.85rem;color:var(--navy);flex:1}
.subject{font-size:.8rem;color:var(--muted);margin-bottom:.18rem}
.reason{font-size:.73rem;color:var(--muted);font-style:italic}
.snippet{font-size:.73rem;color:var(--muted);margin-top:.28rem;
         border-left:2px solid var(--border);padding-left:.4rem}
.projuris-badge{display:inline-flex;align-items:center;gap:.3rem;
                background:#fff3cd;color:#856404;border:1px solid #ffc107;
                border-radius:6px;font-size:.68rem;font-weight:700;
                padding:.2rem .5rem;margin-top:.35rem}

/* ── BADGES ── */
.badge{font-size:.67rem;padding:.17rem .42rem;border-radius:99px;font-weight:700;white-space:nowrap}
.badge-time{background:#dbeafe;color:#1d4ed8}
.badge-risk-alto{background:#fee2e2;color:#b91c1c}
.badge-risk-médio,.badge-risk-medio{background:#fef3c7;color:#92400e}
.badge-risk-baixo{background:#dcfce7;color:#166534}
.badge-tipo-TRIBUNAL{background:#e0f2fe;color:#0369a1}
.badge-tipo-DUVIDA{background:#ccfbf1;color:#0f766e}
.badge-tipo-DEFESA{background:#ede9fe;color:#6d28d9}
.badge-tipo-CLIENTE{background:#f1f5f9;color:#475569}
.empty{color:var(--muted);font-size:.82rem;font-style:italic}

/* ── CHART ── */
.chart-wrap{height:210px;position:relative}

/* ── CALENDÁRIO ── */
.cal-nav{display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem}
.cal-nav button{background:var(--navy);border:1px solid var(--gold);color:var(--gold);
                padding:.32rem .75rem;border-radius:6px;cursor:pointer;font-size:.8rem;font-weight:700}
.cal-nav button:hover{background:var(--gold);color:var(--navy)}
.cal-title{font-weight:800;font-size:.95rem;color:var(--navy)}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}
.cal-dow{text-align:center;font-size:.7rem;color:var(--muted);padding:.28rem 0;font-weight:700;
         text-transform:uppercase}
.cal-day{min-height:78px;background:var(--surface);border-radius:7px;padding:.35rem .45rem;
         border:1px solid var(--border2);cursor:default;transition:.12s}
.cal-day.empty{background:transparent;border-color:transparent}
.cal-day.has-data{cursor:pointer}
.cal-day.has-data:hover{border-color:var(--gold);box-shadow:0 2px 8px rgba(201,168,76,.2)}
.cal-day.is-today{border-color:var(--navy);border-width:2px}
.day-num{font-size:.78rem;font-weight:700;color:var(--navy);margin-bottom:.28rem}
.cal-day.is-today .day-num{color:var(--gold2)}
.cal-pills{display:flex;flex-direction:column;gap:2px}
.cal-pill{font-size:.62rem;padding:.08rem .28rem;border-radius:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600}
.pill-alta{background:#fee2e2;color:#b91c1c}
.pill-media{background:#fef3c7;color:#92400e}
.pill-semresp{background:#dbeafe;color:#1d4ed8}
.pill-tribunal{background:#e0f2fe;color:#0369a1}
#detail-panel{background:var(--surface);border-radius:10px;padding:1.1rem;
              margin-top:1rem;display:none;border:1px solid var(--border);
              box-shadow:0 2px 8px rgba(13,33,55,.08)}
#detail-panel h3{font-size:.9rem;color:var(--navy);font-weight:700;margin-bottom:.75rem}

/* ── FILTROS ── */
.filter-bar{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1rem}
.filter-btn{background:var(--surface);border:1px solid var(--border);color:var(--muted);
            padding:.32rem .75rem;border-radius:99px;cursor:pointer;font-size:.75rem;font-weight:600;transition:.12s}
.filter-btn.active,
.filter-btn:hover{background:var(--navy);color:var(--gold);border-color:var(--navy)}
"""

NAV_HTML_TPL = """
<div class="aviso">⛔ É EXPRESSAMENTE PROIBIDO marcar e-mails como lidos — o sistema opera apenas em modo leitura</div>
<nav>
  <span class="logo">⚖️ Gmail Monitor</span>
  <button class="active" onclick="showPage('dashboard',this)">Dashboard</button>
  <button onclick="showPage('tribunal',this)">Tribunal <span class="nav-badge gold">{n_trib}</span></button>
  <button onclick="showPage('duvidas',this)">Dúvidas <span class="nav-badge">{n_duv}</span></button>
  <button onclick="showPage('defesa',this)">Documentos Defesa <span class="nav-badge">{n_def}</span></button>
  <button onclick="showPage('calendario',this)">Calendário</button>
</nav>
"""

JS_BASE = """
function showPage(id, btn) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + id).classList.add('active');
  if (btn) btn.classList.add('active');
}
function filterCards(tipo) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('.card[data-tipo]').forEach(c => {
    c.style.display = (tipo === 'TODOS' || c.dataset.tipo === tipo) ? '' : 'none';
  });
}
"""


def _card(t: Dict, show_risk=False, show_hours=True, show_projuris=False) -> str:
    hours_badge = f'<span class="badge badge-time">{_fmt_hours(t["hours_since_last"])}</span>' if show_hours else ""
    risk = (t.get("dissatisfaction_risk") or "").lower()
    risk_badge = f'<span class="badge badge-risk-{risk}">{t["dissatisfaction_risk"]}</span>' if show_risk and t.get("dissatisfaction_risk") else ""
    tipo = t.get("tipo", "CLIENTE")
    tipo_badge = f'<span class="badge badge-tipo-{tipo}">{tipo}</span>'
    snippet = f'<p class="snippet">"{(t["snippet"] or "")[:150]}…"</p>' if t.get("snippet") else ""
    projuris = '<div class="projuris-badge">⚠️ Verificar no Projuris — cadastrar como tarefa</div>' if show_projuris else ""
    return f"""
    <div class="card" data-tipo="{tipo}">
      <div class="card-header">
        <span class="sender">{t['sender']}</span>
        {hours_badge}{risk_badge}{tipo_badge}
      </div>
      <div class="subject">{t['subject']}</div>
      <div class="reason">{t.get('reason') or ''}</div>
      {snippet}
      {projuris}
    </div>"""


def _cards(threads, show_risk=False, show_hours=True, show_projuris=False):
    if not threads:
        return '<p class="empty">Nenhuma conversa nesta categoria.</p>'
    return "".join(_card(t, show_risk, show_hours, show_projuris) for t in threads)


def _build_calendar_js(all_exec_by_date: Dict) -> str:
    data_js = "{"
    for d, row in all_exec_by_date.items():
        data_js += (f'"{d}":{{alta:{row["total_alta"]},media:{row["total_media"]},'
                    f'semresp:{row["total_sem_resposta_48h"]},'
                    f'tribunal:{row.get("total_tribunal",0)}}},' )
    data_js += "}"
    return f"""
const CAL_DATA = {data_js};
let calYear, calMonth;
function initCal(){{const t=new Date();calYear=t.getFullYear();calMonth=t.getMonth();renderCal();}}
function renderCal(){{
  const mn=['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
  document.getElementById('cal-title').textContent=mn[calMonth]+' '+calYear;
  const today=new Date();
  const first=new Date(calYear,calMonth,1).getDay();
  const dim=new Date(calYear,calMonth+1,0).getDate();
  let html=['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'].map(d=>`<div class="cal-dow">${{d}}</div>`).join('');
  for(let i=0;i<first;i++) html+='<div class="cal-day empty"></div>';
  for(let d=1;d<=dim;d++){{
    const mm=String(calMonth+1).padStart(2,'0'),dd=String(d).padStart(2,'0');
    const key=`${{calYear}}-${{mm}}-${{dd}}`;
    const isToday=(calYear===today.getFullYear()&&calMonth===today.getMonth()&&d===today.getDate());
    const data=CAL_DATA[key];
    let pills='',cls='';
    if(data){{
      cls='has-data';
      if(data.alta>0)    pills+=`<div class="cal-pill pill-alta">🔴 ${{data.alta}} alta</div>`;
      if(data.media>0)   pills+=`<div class="cal-pill pill-media">🟡 ${{data.media}} média</div>`;
      if(data.tribunal>0)pills+=`<div class="cal-pill pill-tribunal">⚖️ ${{data.tribunal}} tribunal</div>`;
      if(data.semresp>0) pills+=`<div class="cal-pill pill-semresp">🔵 ${{data.semresp}} sem resp</div>`;
    }}
    const tc=isToday?' is-today':'';
    const oc=data?`onclick="showDayDetail('${{key}}')"` :'';
    html+=`<div class="cal-day ${{cls}}${{tc}}" ${{oc}}><div class="day-num">${{d}}</div><div class="cal-pills">${{pills}}</div></div>`;
  }}
  document.getElementById('cal-grid').innerHTML=html;
  document.getElementById('detail-panel').style.display='none';
}}
function calPrev(){{calMonth--;if(calMonth<0){{calMonth=11;calYear--;}}renderCal();}}
function calNext(){{calMonth++;if(calMonth>11){{calMonth=0;calYear++;}}renderCal();}}
function showDayDetail(k){{
  const d=CAL_DATA[k];if(!d)return;
  const[y,m,day]=k.split('-');
  document.getElementById('detail-panel').style.display='block';
  document.getElementById('detail-title').textContent='Resumo — '+day+'/'+m+'/'+y;
  document.getElementById('detail-body').innerHTML=`
    <div style="display:flex;gap:.6rem;flex-wrap:wrap;margin-top:.5rem">
      <span class="badge badge-risk-alto" style="font-size:.78rem;padding:.25rem .6rem">🔴 Alta: ${{d.alta}}</span>
      <span class="badge badge-risk-médio" style="font-size:.78rem;padding:.25rem .6rem">🟡 Média: ${{d.media}}</span>
      <span class="badge badge-tipo-TRIBUNAL" style="font-size:.78rem;padding:.25rem .6rem">⚖️ Tribunal: ${{d.tribunal}}</span>
      <span class="badge badge-time" style="font-size:.78rem;padding:.25rem .6rem">🔵 Sem resp: ${{d.semresp}}</span>
    </div>
    <p style="margin-top:.7rem;font-size:.8rem;color:var(--muted)">
      <a href="dashboard.html" style="color:var(--navy2);text-decoration:underline">Abrir dashboard</a>
    </p>`;
  document.getElementById('detail-panel').scrollIntoView({{behavior:'smooth',block:'nearest'}});
}}
initCal();
"""


# ─── DASHBOARD PRINCIPAL ──────────────────────────────────────────────────────

def save_dashboard(today: date = None) -> str:
    if today is None: today = date.today()
    os.makedirs(REPORTS_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM execucoes WHERE data=? ORDER BY id DESC LIMIT 1", (today.isoformat(),))
    _row = c.fetchone()
    if not _row:
        conn.close(); return ""
    ex = dict(_row)

    eid = ex["id"]; gerado_em = ex["gerado_em"]

    def gt(cat):
        c.execute("SELECT * FROM threads WHERE execucao_id=? AND category=? ORDER BY hours_since_last DESC", (eid, cat))
        return [dict(r) for r in c.fetchall()]

    alta      = gt("ALTA");      media    = gt("MEDIA");  baixa   = gt("BAIXA")
    insat     = gt("INSATISFEITO"); sem_r = gt("SEM_RESPOSTA_48H")
    tribunal  = gt("TRIBUNAL"); duvida   = gt("DUVIDA"); defesa  = gt("DEFESA")

    c.execute("SELECT * FROM execucoes ORDER BY id DESC LIMIT 14")
    hist = list(reversed([dict(r) for r in c.fetchall()]))

    c.execute("SELECT * FROM execucoes ORDER BY data")
    all_exec = {r["data"]: dict(r) for r in c.fetchall()}
    conn.close()

    hl = [r["data"] for r in hist]
    ha = [r["total_alta"] for r in hist]
    hm = [r["total_media"] for r in hist]
    hs = [r["total_sem_resposta_48h"] for r in hist]
    ht = [r.get("total_tribunal", 0) for r in hist]

    nav = NAV_HTML_TPL.format(
        n_trib=len(tribunal), n_duv=len(duvida), n_def=len(defesa)
    )

    # filtros para dashboard
    tipos_present = sorted({t.get("tipo","CLIENTE") for t in (alta+media+baixa)})
    filter_bar = '<div class="filter-bar"><button class="filter-btn active" onclick="filterCards(\'TODOS\')">Todos</button>'
    labels_tipo = {"TRIBUNAL":"⚖️ Tribunal","DUVIDA":"❓ Dúvida","DEFESA":"📄 Defesa","CLIENTE":"👤 Cliente"}
    for tp in tipos_present:
        filter_bar += f'<button class="filter-btn" onclick="filterCards(\'{tp}\')">{labels_tipo.get(tp,tp)}</button>'
    filter_bar += '</div>'

    cal_js = _build_calendar_js(all_exec)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Gmail Monitor — {today.strftime('%d/%m/%Y')}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>{CSS}</style>
</head>
<body>
{nav}

<!-- ═══ DASHBOARD ═══ -->
<div id="page-dashboard" class="page active">
  <div class="page-header">
    <h1>Dashboard Diário</h1>
    <div class="meta">Gerado em {gerado_em} &nbsp;·&nbsp; {today.strftime('%d/%m/%Y')}</div>
  </div>
  <div class="gold-line"></div>

  <div class="kpis">
    <div class="kpi alta"><div class="kpi-num">{ex['total_alta']}</div><div class="kpi-label">Prioridade Alta</div></div>
    <div class="kpi media"><div class="kpi-num">{ex['total_media']}</div><div class="kpi-label">Prioridade Média</div></div>
    <div class="kpi tribunal"><div class="kpi-num">{ex.get('total_tribunal',0)}</div><div class="kpi-label">Tribunal</div></div>
    <div class="kpi duvida"><div class="kpi-num">{ex.get('total_duvida',0)}</div><div class="kpi-label">Dúvidas</div></div>
    <div class="kpi defesa"><div class="kpi-num">{ex.get('total_defesa',0)}</div><div class="kpi-label">Doc. Defesa</div></div>
    <div class="kpi insat"><div class="kpi-num">{ex['total_insatisfeitos']}</div><div class="kpi-label">Insatisfeitos</div></div>
    <div class="kpi semresp"><div class="kpi-num">{ex['total_sem_resposta_48h']}</div><div class="kpi-label">Sem resp. +48h</div></div>
  </div>

  <div class="section">
    <h2>📈 Tendência (últimas execuções)</h2>
    <div class="chart-wrap"><canvas id="chart"></canvas></div>
  </div>

  {filter_bar}

  <div class="grid" style="margin-top:.5rem">
    <div class="section">
      <h2><span class="dot" style="background:var(--alta)"></span> Prioridade Alta ({len(alta)})</h2>
      {_cards(alta)}
    </div>
    <div class="section">
      <h2><span class="dot" style="background:var(--media)"></span> Prioridade Média ({len(media)})</h2>
      {_cards(media)}
    </div>
  </div>

  <div class="grid">
    <div class="section">
      <h2><span class="dot" style="background:var(--insat)"></span> Insatisfeitos</h2>
      {_cards(insat, show_risk=True, show_hours=False)}
    </div>
    <div class="section">
      <h2><span class="dot" style="background:var(--semresp)"></span> Sem Resposta +48h</h2>
      {_cards(sem_r)}
    </div>
  </div>

  <div class="section">
    <h2><span class="dot" style="background:var(--baixa)"></span> Prioridade Baixa ({len(baixa)})</h2>
    {_cards(baixa[:20], show_hours=False)}
    {'<p class="empty" style="margin-top:.5rem">... e mais '+str(len(baixa)-20)+' conversas.</p>' if len(baixa)>20 else ''}
  </div>
</div>

<!-- ═══ TRIBUNAL ═══ -->
<div id="page-tribunal" class="page">
  <div class="page-header">
    <h1>⚖️ Notificações do Tribunal</h1>
    <div class="meta">Push de processo / movimentações judiciais — {today.strftime('%d/%m/%Y')}</div>
  </div>
  <div class="gold-line"></div>
  <div class="section" style="background:#fffbeb;border:1px solid #fbbf24;margin-bottom:1rem">
    <h2 style="color:#92400e;border-color:#fde68a">⚠️ Ação necessária</h2>
    <p style="font-size:.82rem;color:#78350f;margin-top:.25rem">
      Cada notificação abaixo deve ser verificada no <strong>Projuris</strong>.<br>
      Se ainda <strong>não houver tarefa cadastrada</strong>, cadastre imediatamente com prazo correspondente.
    </p>
  </div>
  <div class="section">
    <h2><span class="dot" style="background:var(--tribunal)"></span> Movimentações ({len(tribunal)})</h2>
    {_cards(tribunal, show_projuris=True)}
  </div>
</div>

<!-- ═══ DÚVIDAS ═══ -->
<div id="page-duvidas" class="page">
  <div class="page-header">
    <h1>❓ Dúvidas de Processo</h1>
    <div class="meta">Clientes aguardando informação sobre andamento — {today.strftime('%d/%m/%Y')}</div>
  </div>
  <div class="gold-line"></div>
  <div class="section">
    <h2><span class="dot" style="background:var(--duvida)"></span> Dúvidas ({len(duvida)})</h2>
    {_cards(duvida)}
  </div>
</div>

<!-- ═══ DEFESA ═══ -->
<div id="page-defesa" class="page">
  <div class="page-header">
    <h1>📄 Documentos de Defesa</h1>
    <div class="meta">Petições, contestações, recursos e documentos — {today.strftime('%d/%m/%Y')}</div>
  </div>
  <div class="gold-line"></div>
  <div class="section">
    <h2><span class="dot" style="background:var(--defesa)"></span> Documentos ({len(defesa)})</h2>
    {_cards(defesa)}
  </div>
</div>

<!-- ═══ CALENDÁRIO ═══ -->
<div id="page-calendario" class="page">
  <div class="page-header">
    <h1>📅 Calendário</h1>
    <div class="meta">Histórico de execuções — clique em um dia para ver o resumo</div>
  </div>
  <div class="gold-line"></div>
  <div class="section">
    <div class="cal-nav">
      <button onclick="calPrev()">‹ Anterior</button>
      <span class="cal-title" id="cal-title"></span>
      <button onclick="calNext()">Próximo ›</button>
    </div>
    <div class="cal-grid" id="cal-grid"></div>
    <div id="detail-panel">
      <h3 id="detail-title"></h3>
      <div id="detail-body"></div>
    </div>
  </div>
</div>

<script>
{JS_BASE}

new Chart(document.getElementById('chart'),{{
  type:'line',
  data:{{
    labels:{hl},
    datasets:[
      {{label:'Alta',     data:{ha},borderColor:'#dc2626',tension:.3,fill:false,pointRadius:4,pointBackgroundColor:'#dc2626'}},
      {{label:'Média',    data:{hm},borderColor:'#d97706',tension:.3,fill:false,pointRadius:4,pointBackgroundColor:'#d97706'}},
      {{label:'Tribunal', data:{ht},borderColor:'#0891b2',tension:.3,fill:false,pointRadius:4,pointBackgroundColor:'#0891b2'}},
      {{label:'Sem resp +48h',data:{hs},borderColor:'#2563eb',tension:.3,fill:false,pointRadius:4,pointBackgroundColor:'#2563eb'}}
    ]
  }},
  options:{{
    responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{labels:{{color:'#4b6280',font:{{size:11}}}}}}}},
    scales:{{
      x:{{ticks:{{color:'#4b6280'}},grid:{{color:'#e2e8f0'}}}},
      y:{{ticks:{{color:'#4b6280'}},grid:{{color:'#e2e8f0'}}}}
    }}
  }}
}});

{cal_js}
</script>
</body>
</html>"""

    path = os.path.join(REPORTS_DIR, "dashboard.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


# ─── INDEX ────────────────────────────────────────────────────────────────────

def save_index():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM execucoes ORDER BY data DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    seen = {}
    for r in rows:
        if r["data"] not in seen: seen[r["data"]] = r

    items = ""
    for d, r in seen.items():
        fmt = datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m/%Y")
        items += f"""
        <a href="dashboard.html" class="row">
          <span class="date">{fmt}</span>
          <span class="pill pill-alta">🔴 {r['total_alta']}</span>
          <span class="pill pill-media">🟡 {r['total_media']}</span>
          <span class="pill pill-tribunal">⚖️ {r.get('total_tribunal',0)}</span>
          <span class="pill pill-semresp">🔵 {r['total_sem_resposta_48h']}</span>
          <span class="gen">{r['gerado_em']}</span>
        </a>"""

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Gmail Monitor — Histórico</title>
<style>
:root{{--bg:#f0f4f8;--surface:#fff;--navy:#0d2137;--gold:#c9a84c;--muted:#4b6280;--border:#cbd5e1}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--navy);font-family:'Segoe UI',system-ui,sans-serif;padding:2rem}}
h1{{font-size:1.3rem;font-weight:800;margin-bottom:.2rem}}
.sub{{color:var(--muted);font-size:.8rem;margin-bottom:1.5rem}}
.row{{display:flex;align-items:center;gap:.65rem;background:var(--surface);border-radius:9px;
      padding:.75rem 1rem;margin-bottom:.45rem;border:1px solid var(--border);
      transition:.12s;flex-wrap:wrap}}
.row:hover{{border-color:var(--gold);box-shadow:0 2px 8px rgba(201,168,76,.2)}}
.date{{font-weight:700;font-size:.88rem;min-width:95px}}
.pill{{font-size:.7rem;padding:.18rem .48rem;border-radius:6px;font-weight:700}}
.pill-alta{{background:#fee2e2;color:#b91c1c}}
.pill-media{{background:#fef3c7;color:#92400e}}
.pill-tribunal{{background:#e0f2fe;color:#0369a1}}
.pill-semresp{{background:#dbeafe;color:#1d4ed8}}
.gen{{margin-left:auto;font-size:.72rem;color:var(--muted)}}
</style>
</head>
<body>
<h1>⚖️ Gmail Monitor — Histórico</h1>
<p class="sub">Clique em qualquer dia para abrir o dashboard atualizado</p>
{items}
</body>
</html>"""

    with open(os.path.join(REPORTS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
