/* MarquesPro Mail — interface local espelhada do Gmail.
 * Abrir mensagens aqui NÃO altera o status de leitura no Gmail.
 */
(() => {
"use strict";

const TOKEN = window.GESTOR_TOKEN;
const PAGE = 50;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const ic = (name, cls = "") => `<span class="ms ${cls}">${name}</span>`;

const FOLDERS = [
  {id: "INBOX", name: "Caixa de entrada", icon: "inbox"},
  {id: "SENT", name: "Enviados", icon: "send"},
];
// Pastas menos usadas: ficam no menu "Mais" da barra de atalhos, fora da lateral
const OUTRAS_PASTAS = [
  {id: "STARRED", name: "Com estrela", icon: "star"},
  {id: "IMPORTANT", name: "Importante", icon: "label_important"},
  {id: "ANUNCIOS", name: "Anúncios e promoções", icon: "campaign"},
  {id: "ALL", name: "Todos os e-mails", icon: "mail"},
];


const state = {
  novos: false, pendAba: "pendente",
  accounts: [], account: "", folder: {id: "INBOX"}, grupo: "", offset: 0, total: 0, hlCount: 0,
  labels: [], threads: [], selected: new Set(), sendAs: [], settings: {},
  lastNotif: null, notifHoje: null, status: null, search: "", searchGmail: false, current: null,
};

// ─── Período dos Destaques ───────────────────────────────────────────────
const PERIODOS = [
  {id: "hoje", nome: "Hoje", dias: 1}, {id: "2d", nome: "2 dias", dias: 2}, {id: "3d", nome: "3 dias", dias: 3},
  {id: "7d", nome: "1 semana", dias: 7}, {id: "30d", nome: "1 mês", dias: 30},
];
function lerPeriodo() {
  try { const v = JSON.parse(localStorage.getItem("mp_periodo") || "null"); if (v && v.tipo) return v; } catch (_) {}
  return {tipo: "hoje", de: "", ate: "", so: false};
}
function salvarPeriodo() { try { localStorage.setItem("mp_periodo", JSON.stringify(state.periodo)); } catch (_) {} }
const fmtD = (d) => d.toLocaleDateString("pt-BR", {day: "2-digit", month: "2-digit"});
function janelaPeriodo() {
  const p = state.periodo, base = new Date(); base.setHours(0, 0, 0, 0);
  if (p.tipo === "custom" && p.de) {
    const de = new Date(p.de + "T00:00:00"), ate = new Date((p.ate || p.de) + "T23:59:59.999");
    return {desde: de.getTime(), ate: ate.getTime(), rotulo: `${fmtD(de)} a ${fmtD(ate)}`, soPeriodo: true};
  }
  const def = PERIODOS.find(x => x.id === p.tipo) || PERIODOS[0];
  base.setDate(base.getDate() - (def.dias - 1));
  return {desde: base.getTime(), ate: null, rotulo: def.nome, soPeriodo: !!p.so};
}
state.periodo = lerPeriodo();
function menuPeriodo() {
  const menu = $("#menu-periodo"); closeMenus(menu);
  const p = state.periodo;
  menu.innerHTML = PERIODOS.map(x => `<label><input type="radio" name="per" value="${x.id}" ${p.tipo === x.id ? "checked" : ""}> ${x.nome}</label>`).join("") +
    `<label><input type="radio" name="per" value="custom" ${p.tipo === "custom" ? "checked" : ""}> Período específico</label>
     <div class="per-custom"><input type="date" id="per-de" value="${esc(p.de || "")}" aria-label="De"><span>a</span><input type="date" id="per-ate" value="${esc(p.ate || "")}" aria-label="Até"></div>
     <label><input type="checkbox" id="per-so" ${p.so ? "checked" : ""}> Mostrar só este período (ocultar anteriores)</label>
     <div class="menu-foot"><button data-ok>Aplicar</button></div>`;
  menu.classList.remove("hidden");
  menu.onclick = (e) => e.stopPropagation();
  $("[data-ok]", menu).onclick = guard(async () => {
    const tipo = $("input[name=per]:checked", menu).value, de = $("#per-de").value, ate = $("#per-ate").value;
    if (tipo === "custom" && !de) { toast("Informe a data inicial do período.", true); return; }
    if (tipo === "custom" && ate && ate < de) { toast("A data final é anterior à inicial.", true); return; }
    state.periodo = {tipo, de, ate, so: $("#per-so").checked}; salvarPeriodo();
    menu.classList.add("hidden"); state.offset = 0; await loadThreads();
  });
}

// ─── API ─────────────────────────────────────────────────────────────────
async function apiRaw(path, opts = {}) {
  const headers = Object.assign({"X-Gestor-Token": TOKEN}, opts.headers || {});
  let body = opts.body;
  if (body && !(body instanceof FormData)) { headers["Content-Type"] = "application/json"; body = JSON.stringify(body); }
  const r = await fetch(path, {method: opts.method || (body ? "POST" : "GET"), headers, body});
  let data = null;
  try { data = await r.json(); } catch (_) {}
  if (!r.ok) throw new Error((data && data.erro) || `Erro ${r.status}`);
  return {data, headers: r.headers};
}
const api = async (path, opts) => (await apiRaw(path, opts)).data;
const qs = (o) => Object.entries(o).filter(([, v]) => v !== "" && v != null).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
const attUrl = (acc, mid, a, inline) =>
  `/api/attachment/${encodeURIComponent(acc)}/${mid}/${encodeURIComponent(a.attachment_id)}?` +
  qs({t: TOKEN, nome: a.filename, tipo: a.mime_type, inline: inline ? 1 : ""});

function toast(msg, err) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.textContent = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), err ? 7000 : 4000);
}
const guard = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { toast(e.message, true); } };

// ─── Utilidades ──────────────────────────────────────────────────────────
function fmtDate(ms) {
  const d = new Date(ms), now = new Date();
  if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit"});
  if (d.getFullYear() === now.getFullYear()) return d.toLocaleDateString("pt-BR", {day: "numeric", month: "short"}).replace(".", "");
  return d.toLocaleDateString("pt-BR");
}
function fmtLong(ms) {
  const d = new Date(ms), mins = Math.round((Date.now() - ms) / 60000);
  const rel = mins < 1 ? "agora" : mins < 60 ? `há ${mins} minuto${mins > 1 ? "s" : ""}` : mins < 1440 ? `há ${Math.round(mins / 60)} hora${mins >= 120 ? "s" : ""}` : `há ${Math.round(mins / 1440)} dia${mins >= 2880 ? "s" : ""}`;
  return `${d.toLocaleDateString("pt-BR", {day: "numeric", month: "short", year: d.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined}).replace(".", "")}, ${d.toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit"})} (${rel})`;
}
function colorFor(s) {
  const pal = ["#1a73e8", "#d93025", "#188038", "#e37400", "#9334e6", "#007b83", "#c5221f", "#5f6368", "#b06000", "#3949ab"];
  let h = 0; for (const c of s || "") h = (h * 31 + c.charCodeAt(0)) | 0;
  return pal[Math.abs(h) % pal.length];
}
const initial = (s) => esc(((s || "?").trim()[0] || "?").toUpperCase());
function labelsOf(acc) { return state.labels.filter(l => l.account === acc); }
function labelById(acc, id) { return state.labels.find(l => l.account === acc && l.id === id); }
function userLabels(acc) { return labelsOf(acc).filter(l => l.type === "user"); }
function chipHtml(l, removable) {
  // Igual ao Gmail: retângulo arredondado com a cor de fundo e de texto do marcador
  const st = l.bg_color ? ` style="background:${esc(l.bg_color)};color:${esc(l.text_color || "#fff")}"` : "";
  return `<span class="chip"${st} data-label="${esc(l.id)}">${esc(l.name)}${removable ? `<span class="ms x" title="Remover marcador">close</span>` : ""}</span>`;
}

// Sanitiza HTML de terceiros antes de inseri-lo no editor (resposta/encaminhamento)
const BLOCKED_TAGS = "script,iframe,frame,frameset,object,embed,applet,link,meta,base,form,input,button,textarea,select,option,svg,math,template,noscript,style";
function sanitizeHtml(src) {
  const doc = new DOMParser().parseFromString(`<body>${src || ""}</body>`, "text/html");
  doc.body.querySelectorAll(BLOCKED_TAGS).forEach(n => n.remove());
  doc.body.querySelectorAll("*").forEach(el => {
    for (const a of Array.from(el.attributes)) {
      const name = a.name.toLowerCase(), val = a.value.trim().toLowerCase();
      if (name.startsWith("on") || name === "srcdoc" || name === "formaction") el.removeAttribute(a.name);
      else if (["href", "src", "action", "xlink:href", "background"].includes(name) &&
               (val.startsWith("javascript:") || val.startsWith("vbscript:") || (val.startsWith("data:") && !val.startsWith("data:image/"))))
        el.removeAttribute(a.name);
      else if (name === "style" && /expression\s*\(|javascript:/i.test(val)) el.removeAttribute(a.name);
    }
  });
  return doc.body.innerHTML;
}

// ─── Carregamento ────────────────────────────────────────────────────────
async function loadAccounts() {
  state.accounts = await api("/api/accounts");
  renderAccountButton();
  if (!state.accounts.length) openSettings("tab-accounts");
}
async function loadLabels() { state.labels = await api("/api/labels"); renderSidebar(); }
async function loadSendAs() { state.sendAs = await api("/api/send-as"); }
async function loadSettings() { state.settings = await api("/api/settings"); }

function renderAccountButton() {
  const cur = state.account || (state.accounts.length === 1 ? state.accounts[0].email : "");
  const b = $("#btn-account");
  $("#account-initial").textContent = cur ? cur[0].toUpperCase() : (state.accounts.length ? "★" : "?");
  b.style.background = cur ? colorFor(cur) : "#5f6368";
  b.title = cur ? `Conta: ${cur}` : "Todas as contas";
}
function renderAccountMenu() {
  const m = $("#account-menu");
  const item = (email, label) => `<div class="acc ${state.account === email ? "on" : ""}" data-acc="${esc(email)}">
      <span class="av" style="background:${email ? colorFor(email) : "#5f6368"}">${email ? initial(email) : "★"}</span><span>${esc(label)}</span></div>`;
  m.innerHTML = (state.accounts.length > 1 ? item("", "Todas as contas") : "") +
    state.accounts.map(a => item(a.email, a.email)).join("") +
    `<div class="menu-foot"><button data-add>Adicionar outra conta</button></div>`;
  $$(".acc", m).forEach(d => d.onclick = guard(async () => {
    m.classList.add("hidden");
    state.account = d.dataset.acc; state.lastNotif = null; state.notifHoje = null; state.offset = 0;
    if (state.folder.name) state.folder = {id: "INBOX"};
    renderAccountButton(); renderSidebar(); await refreshStatus(); await loadThreads();
  }));
  $("[data-add]", m).onclick = () => { m.classList.add("hidden"); openSettings("tab-accounts"); };
}

function renderSidebar() {
  const st = state.status || {};
  const counts = {INBOX: st.nao_lidas_local || 0};
  const isFolder = (id) => state.folder.id === id && !state.folder.name;
  $("#folders").innerHTML = FOLDERS.map(f => `
    <li data-folder="${f.id}" class="${isFolder(f.id) ? "active" : ""} ${counts[f.id] ? "has-unread" : ""} " title="${esc(f.name)}">
      ${ic(f.icon, isFolder(f.id) ? "fill" : "")}<span class="name">${f.name}</span>
      ${counts[f.id] ? `<span class="count">${counts[f.id]}</span>` : ""}</li>`).join("");
  const src = state.account ? userLabels(state.account) : state.labels.filter(l => l.type === "user");
  const byName = new Map();
  src.forEach(l => { if (!byName.has(l.name)) byName.set(l.name, l); });
  const unreadBy = st.nao_lidas_etiqueta || {};
  const names = [...byName.keys()].sort((a, b) => a.localeCompare(b, "pt-BR"));
  $("#label-list").innerHTML = names.map(n => {
    const parts = n.split("/"), parent = parts.slice(0, -1).join("/");
    const nested = parts.length > 1 && byName.has(parent);
    const l = byName.get(n), depth = nested ? parts.length - 1 : 0, short = nested ? parts[parts.length - 1] : n;
    const on = state.folder.name === n, cnt = unreadBy[n] || 0;
    return `<li data-label-name="${esc(n)}" data-label-id="${esc(l.id)}" style="padding-left:${26 + depth * 18}px"
      class="${on ? "active" : ""} ${cnt ? "has-unread" : ""}" title="${esc(n)}">
      <span class="ms ${l.bg_color ? "fill" : ""} lab-ic" style="${l.bg_color ? `color:${esc(l.bg_color)}` : ""}">label</span>
      <span class="name">${esc(short)}</span>${cnt ? `<span class="count">${cnt}</span>` : ""}</li>`;
  }).join("") || `<li class="muted"><span class="name">Nenhum marcador</span></li>`;
}

function renderTabs() {
  const show = ["INBOX", "PEND"].includes(state.folder.id) && !state.folder.name && !state.search;
  const box = $("#tabs-inbox");
  box.classList.toggle("hidden", !show);
  if (!show) return;
  if (state.folder.id !== "INBOX") state.novos = false;
  const st = state.status || {}, pg = (st.notificacoes && st.notificacoes.pendentes_por_grupo) || {};
  const judic = pg.judiciais || 0, nn = st.novos_hoje || 0, pn = st.pendencias ? st.pendencias.abertas + st.pendencias.em_execucao : 0;
  const naCaixa = state.folder.id === "INBOX";
  const ativa = state.folder.id === "PEND" ? "pend" : naCaixa && state.grupo === "judiciais" ? "judiciais" : naCaixa && state.novos ? "novos" : "todas";
  const detalhe = `Não abertas no MarquesPro: intimações ${pg.intimacoes || 0} · citações ${pg.citacoes || 0} · notificações ${pg.notificacoes || 0}`;
  const tab = (id, icone, nome, n, tip, cls = "") => `<button class="gtab ${ativa === id ? "on" : ""}" data-q="${id}" title="${esc(tip)}">${ic(icone, ativa === id ? "fill" : "")}<span>${nome}</span>${n ? `<span class="gn ${cls}">${n}</span>` : ""}</button>`;
  box.innerHTML = `<div class="gtabs">
    ${tab("todas", "inbox", "Principal", 0, "Toda a caixa de entrada")}
    ${tab("judiciais", "gavel", "Intimações, citações e notificações", judic, detalhe, "red")}
    ${tab("novos", "fiber_new", "Novos hoje", nn, "Conversas novas de hoje, fora da cadeia de e-mails")}
    ${tab("pend", "pending_actions", "Pendências", pn, "Clientes que perguntaram e ainda não foram respondidos")}
    <span class="spacer"></span>
    ${naCaixa ? `<div class="dropdown periodo"><button class="gbtn" id="btn-periodo" title="Período dos Destaques">${ic("date_range", "sm")}<span>${esc(janelaPeriodo().rotulo)}</span>${ic("arrow_drop_down", "sm")}</button><div class="menu hidden" id="menu-periodo"></div></div>` : ""}
    <div class="dropdown"><button class="icon-btn" id="btn-mais-pastas" title="Outras pastas">${ic("more_vert")}</button><div class="menu hidden" id="menu-mais-pastas">${OUTRAS_PASTAS.map(f => `<div class="mi" data-pasta="${f.id}">${ic(f.icon, "sm")}${f.name}</div>`).join("")}</div></div>
  </div>`;
  $$("button[data-q]", box).forEach(b => b.onclick = guard(async () => {
    const q = b.dataset.q;
    state.search = ""; state.offset = 0;
    if (q === "pend") { state.folder = {id: "PEND"}; state.novos = false; state.grupo = ""; }
    else {
      state.folder = {id: "INBOX"};
      state.grupo = q === "judiciais" ? "judiciais" : ""; state.novos = q === "novos";
    }
    renderSidebar(); await loadThreads();
  }));
  if (naCaixa) $("#btn-periodo").onclick = (e) => { e.stopPropagation(); menuPeriodo(); };
  $("#btn-mais-pastas").onclick = (e) => { e.stopPropagation(); const m = $("#menu-mais-pastas"), hid = m.classList.contains("hidden"); closeMenus(); if (hid) m.classList.remove("hidden"); };
  $$("[data-pasta]", box).forEach(d => d.onclick = guard(async () => {
    state.folder = {id: d.dataset.pasta}; state.grupo = ""; state.novos = false; state.search = ""; state.offset = 0; renderSidebar(); await loadThreads();
  }));
}

async function loadThreads() {
  const list = $("#thread-list");
  showList();
  renderTabs();
  if (state.folder.id === "PEND" && !state.folder.name && !state.search) { state.threads = []; state.hlCount = 0; renderPager(); return renderPendencias(); }
  let data, total, highlights = [];
  if (state.search && state.searchGmail) {
    if (!state.account) { list.innerHTML = `<div class="empty">${ic("person_search")}Escolha uma conta (no círculo do canto superior direito) para buscar no Gmail.</div>`; return; }
    data = await api(`/api/search?${qs({account: state.account, q: state.search})}`);
    total = data.length;
  } else {
    const p = {account: state.account, q: state.search, nao_lidas: $("#only-unread").checked ? 1 : "", limit: PAGE, offset: state.offset};
    if (state.folder.name) { if (state.account) p.label = state.folder.id; else p.label_nome = state.folder.name; }
    else p.label = state.folder.id;
    if (state.grupo && state.folder.id === "INBOX" && !state.folder.name) p.grupo = state.grupo;
    // Caixa de entrada: Destaques do período escolhido, por prioridade (intimações/citações não abertas primeiro)
    if (state.novos && state.folder.id === "INBOX") p.novos = 1;
    const withHl = state.folder.id === "INBOX" && !state.folder.name && !state.search && !state.grupo && !p.nao_lidas && !state.novos;
    state.jan = withHl ? janelaPeriodo() : null;
    if (withHl) {
      const j = state.jan;
      if (state.offset === 0 || j.soPeriodo) highlights = await api(`/api/threads?${qs(Object.assign({}, p, {destaque: 1, desde: j.desde, ate: j.ate || "", prioridade: 1, limit: 200, offset: 0}))}`);
      p.destaque = 0; p.desde = j.desde;
    }
    if (state.jan && state.jan.soPeriodo) { data = []; total = 0; }
    else { const r = await apiRaw(`/api/threads?${qs(p)}`); data = r.data; total = +(r.headers.get("X-Total-Count") || data.length); }
  }
  state.hlCount = highlights.length;
  state.threads = highlights.concat(data); state.total = total;
  state.selected.clear();
  $("#select-all").checked = false;
  renderThreads();
}

function renderPager() {
  const n = state.threads.length - state.hlCount;
  $("#pager").textContent = n ? `${state.offset + 1}–${state.offset + n} de ${state.total.toLocaleString("pt-BR")}` : "";
  $("#btn-prev").disabled = state.offset === 0;
  $("#btn-next").disabled = state.offset + n >= state.total;
  const sel = state.selected.size > 0;
  $$(".sel-tools").forEach(e => e.classList.toggle("hidden", !sel));
}

function renderThreads() {
  const list = $("#thread-list");
  renderPager();
  if (!state.threads.length) {
    const msg = state.search ? "Nenhuma mensagem corresponde à sua pesquisa." :
      state.jan && state.jan.soPeriodo ? `Nenhum e-mail no período (${state.jan.rotulo}).` :
      state.novos ? "Nenhum e-mail novo (fora da cadeia) hoje." : state.grupo === "judiciais" ? "Nenhuma intimação, citação ou notificação por aqui." : state.folder.id === "ANUNCIOS" ? "Nenhum anúncio ou promoção." : "Nenhuma conversa nesta pasta.";
    list.innerHTML = `<div class="empty">${ic(state.folder.id === "NOTIF" ? "gavel" : "inbox")}${msg}</div>`; return;
  }
  const multi = !state.account && state.accounts.length > 1;
  const rot = state.jan ? state.jan.rotulo : "hoje";
  const secHl = `<div class="sec-head hl" title="E-mails do período, com os de prioridade de leitura primeiro">Destaques · ${esc(rot)}<span class="n">${state.hlCount}</span></div>`;
  const soPer = state.jan && state.jan.soPeriodo;
  const secRest = soPer ? "" : `<div class="sec-head">Anteriores</div>`;
  list.innerHTML = state.threads.map((t, i) => (state.hlCount && i === 0 ? secHl : "") + (state.hlCount && i === state.hlCount ? secRest : "") + rowHtml(t, i, multi)).join("")
    + (!soPer && state.hlCount && state.threads.length === state.hlCount ? secRest + `<div class="empty">Nenhuma outra conversa nesta página.</div>` : "");
}

// Destaca (sem diferenciar acentos) as palavras de atenção dentro de um texto
const _acentos = {a: "aàáâãä", e: "eèéêë", i: "iìíîï", o: "oòóôõö", u: "uùúûü", c: "cç"};
function realce(texto, palavras) {
  texto = String(texto ?? "");
  if (!palavras || !palavras.length) return esc(texto);
  const pad = palavras.map(p => String(p).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").split("")
    .map(ch => /[a-z]/.test(ch) ? (_acentos[ch] ? `[${_acentos[ch]}]` : ch) : ch.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("")).join("|");
  const re = new RegExp(`(${pad})`, "gi");
  return texto.split(re).map((parte, k) => k % 2 ? `<mark class="kw">${esc(parte)}</mark>` : esc(parte)).join("");
}

// ─── Pendências (tratativas sem resposta) ─────────────────────────────────
const PEND_ABAS = [{id: "pendente", nome: "Sem resposta", icon: "reply"}, {id: "em_execucao", nome: "Em execução", icon: "pending"}, {id: "concluida", nome: "Concluídas", icon: "task_alt"}];
async function renderPendencias() {
  const list = $("#thread-list");
  const itens = await api(`/api/pendencias?${qs({account: state.account})}`);
  const cont = (id) => itens.filter(i => i.status === id).length;
  const vis = itens.filter(i => i.status === state.pendAba);
  const abas = PEND_ABAS.map(a => `<button class="filter-chip ${state.pendAba === a.id ? "on" : ""} ${a.id === "pendente" ? "hl" : ""}" data-pabas="${a.id}">${ic(state.pendAba === a.id ? "check" : a.icon, "sm")}<span>${a.nome}</span><b class="n">${cont(a.id)}</b></button>`).join("");
  const vazio = {pendente: "Nenhuma pergunta de cliente aguardando resposta. Tudo em dia.", em_execucao: "Nenhuma tratativa em execução.", concluida: "Nenhuma tratativa concluída ainda."}[state.pendAba];
  list.innerHTML = `<div class="pend-head"><div><b>Tratativas pendentes</b><div class="muted">Perguntas ou pedidos de clientes que ainda não foram respondidos. Somem sozinhas quando o e-mail é respondido, ou conclua manualmente.</div></div><div class="tabs-inbox pend-tabs">${abas}</div></div>`
    + (vis.length ? vis.map((p, k) => pendCard(p, k)).join("") : `<div class="empty">${ic("task_alt")}${vazio}</div>`);
  $$("[data-pabas]", list).forEach(b => b.onclick = guard(async () => { state.pendAba = b.dataset.pabas; await renderPendencias(); }));
  $$(".pend-card", list).forEach(c => {
    const p = vis[+c.dataset.k];
    const set = async (status, pedeNota) => {
      let nota = p.nota || "";
      if (pedeNota) { const r = prompt(status === "concluida" ? "Como foi resolvido? (opcional)" : "O que está sendo feito? (opcional)", nota); if (r === null) return; nota = r; }
      await api(`/api/pendencias/${encodeURIComponent(p.account)}/${p.thread_id}`, {body: {status, nota, message_id: p.message_id}});
      await refreshStatus(); await renderPendencias();
    };
    $("[data-abrir]", c).onclick = guard(() => openThread(p.account, p.thread_id));
    const b = (a) => $(`[data-${a}]`, c);
    if (b("exec")) b("exec").onclick = guard(() => set("em_execucao", true));
    if (b("voltar")) b("voltar").onclick = guard(() => set("pendente", false));
    if (b("concluir")) b("concluir").onclick = guard(() => set("concluida", true));
    if (b("reabrir")) b("reabrir").onclick = guard(() => set("pendente", false));
  });
}
function pendCard(p, k) {
  const espera = p.status === "concluida" ? "" : p.dias_espera ? `aguardando há ${p.dias_espera} dia${p.dias_espera > 1 ? "s" : ""}` : "chegou hoje";
  const urgente = p.status === "pendente" && p.dias_espera >= 2;
  const por = p.status === "concluida" ? (p.concluido_por === "resposta" ? "Respondido pelo MarquesPro" : "Concluído manualmente") : "";
  return `<div class="pend-card ${p.status} ${urgente ? "atraso" : ""}" data-k="${k}">
    <div class="pend-main">
      <div class="pend-top"><b>${esc(p.de_nome || p.de_email || "Cliente")}</b><span class="muted">${esc(p.de_email && p.de_nome ? `<${p.de_email}>` : "")}</span>
        ${espera ? `<span class="chip pend ${urgente ? "pendente" : "leve"}">${ic("schedule", "sm")}${espera}</span>` : ""}
        ${p.origem === "manual" ? `<span class="chip">marcada por você</span>` : ""}${por ? `<span class="chip">${ic("task_alt", "sm")}${por}</span>` : ""}</div>
      <div class="pend-subj">${esc(p.assunto)}</div>
      ${p.trecho ? `<blockquote class="pend-q">${esc(p.trecho)}</blockquote>` : ""}
      ${p.nota ? `<div class="pend-nota">${ic("sticky_note_2", "sm")}${esc(p.nota)}</div>` : ""}
    </div>
    <div class="pend-acts">
      <button class="btn" data-abrir>${ic("open_in_new", "sm")} Abrir</button>
      ${p.status === "pendente" ? `<button class="btn" data-exec>${ic("pending", "sm")} Em execução</button><button class="btn primary" data-concluir>${ic("check", "sm")} Concluir</button>` : ""}
      ${p.status === "em_execucao" ? `<button class="btn" data-voltar>Voltar a pendente</button><button class="btn primary" data-concluir>${ic("check", "sm")} Concluir</button>` : ""}
      ${p.status === "concluida" ? `<button class="btn" data-reabrir>Reabrir</button>` : ""}
    </div></div>`;
}

function rowHtml(t, i, multi) {
  {
    const chips = t.label_ids.map(id => labelById(t.account, id)).filter(l => l && l.type === "user")
      .filter(l => !(state.folder.name && l.name === state.folder.name));
    const chipsHtml = chips.slice(0, 2).map(l => chipHtml(l, false, false)).join("") +
      (chips.length > 2 ? `<span class="chip mais-n" title="${esc(chips.slice(2).map(l => l.name).join(", "))}">+${chips.length - 2}</span>` : "");
    const atts = (t.anexos || []).map(n => `<span class="att-chip">${ic("description", "sm")}${esc(n)}</span>`).join("");
    const starred = t.label_ids.includes("STARRED");
    const prio = t.prioridade || [];
    const hl = false;
    const pal = t.palavras || [];
    const pend = t.pendencia;
    // Etiquetas do sistema no mesmo formato das do Gmail: vermelha só para prioridade de leitura, cinza para o resto
    const lb = (cls, texto, titulo) => `<span class="chip ${cls}" title="${esc(titulo)}">${esc(texto)}</span>`;
    const prioChips = prio.slice(0, 2).map(p => lb("g-prio", p, `Prioridade de leitura: ${p}`)).join("");
    const sys = [];
    if (pend) sys.push(lb("g-sys", pend.status === "em_execucao" ? "Em execução" : `Sem resposta${pend.dias >= 1 ? ` · ${pend.dias}d` : ""}`,
      `${pend.status === "em_execucao" ? "Tratativa em execução" : "Cliente perguntou e ainda não foi respondido"}: ${pend.trecho}`));
    if (t.resgatado) sys.push(lb("g-sys", "Veio do spam", `Estava no spam do Gmail (${t.resgatado === "cliente" ? "remetente conhecido" : "parece notificação judicial"}). Confira o remetente.`));
    if (t.notificacao && !prio.length && !sys.length) sys.push(lb("g-sys", t.notificacao, "Notificação judicial"));
    const sysChips = sys.slice(0, 2).join("");
    const novoChip = "", pendChip = "", spamChip = "", notifChip = "";
    return `<div class="row-t ${t.read_local ? "" : "unread"} ${hl ? "hl" : ""}  ${state.selected.has(i) ? "selected" : ""}" data-i="${i}">
      <div class="lead">
        <span class="cell"><input type="checkbox" class="sel" ${state.selected.has(i) ? "checked" : ""} aria-label="Selecionar"></span>
        <button class="star ${starred ? "on" : ""}" title="${starred ? "Com estrela" : "Sem estrela"}">${ic("star", starred ? "fill" : "")}</button>
        <button class="imp ${t.important ? "on" : ""}" title="${t.important ? "Importante" : "Marcar como importante"}">${ic("label_important", t.important ? "fill" : "")}</button>
      </div>
      <div class="from">${esc(t.senders)}${t.count > 1 ? `<span class="cnt">${t.count}</span>` : ""}</div>
      <div class="mid">
        <div class="line1">${prioChips}${sysChips}${chipsHtml}${t.sem_envio ? `<span class="alerta-envio" title="Nenhum e-mail enviado sobre esta notificação">${ic("error", "sm")}</span>` : ""}
          <span class="subj"><span class="subj-t">${realce(t.subject, pal)}</span><span class="snip"> - ${realce(t.snippet, pal)}</span></span></div>
        ${atts ? `<div class="att-chips">${atts}</div>` : ""}
      </div>
      ${t.unread_gmail ? `<span class="gm" title="Ainda não lida no Gmail (status preservado para a controladoria)">${ic("mark_email_unread", "sm")}</span>` : ""}
      ${multi ? `<span class="acc">${esc(t.account.split("@")[0])}</span>` : ""}
      ${t.has_attachments && !atts ? `<span class="ms sm" style="color:#5e5e5e;margin-left:8px" title="Possui anexo">attach_file</span>` : ""}
      <div class="date">${fmtDate(t.last_date)}</div>
      <div class="hover-acts">
        <button class="icon-btn small" data-toggle-read title="${t.read_local ? "Marcar como não lida (somente no MarquesPro)" : "Marcar como lida (somente no MarquesPro)"}">${ic(t.read_local ? "mark_email_unread" : "drafts")}</button>
      </div></div>`;
  }
}

// ─── Leitura ─────────────────────────────────────────────────────────────
function showList() { $("#thread-view").classList.add("hidden"); $("#thread-list").classList.remove("hidden"); $("#list-toolbar").classList.remove("hidden"); }
function showView() { $("#thread-view").classList.remove("hidden"); $("#thread-list").classList.add("hidden"); $("#list-toolbar").classList.add("hidden"); $("#tabs-inbox").classList.add("hidden"); }

async function openThread(account, threadId) {
  const data = await api(`/api/threads/${encodeURIComponent(account)}/${threadId}`);
  state.current = data;
  const t = state.threads.find(x => x.thread_id === threadId && x.account === account);
  if (t) t.read_local = true;
  renderThreadView();
  showView();
  $("#thread-view").scrollTop = 0;
  refreshStatus();
}

function pendBanner(d) {
  const p = d.pendencia;
  if (p && p.status !== "concluida") {
    return `<div class="pend-banner ${p.status}">${ic(p.status === "em_execucao" ? "pending" : "reply", "sm")}<span><b>${p.status === "em_execucao" ? "Tratativa em execução" : "Pergunta do cliente sem resposta"}</b>${p.dias_espera ? ` · há ${p.dias_espera} dia(s)` : ""}${p.trecho ? ` — “${esc(p.trecho)}”` : ""}${p.nota ? ` <i>(${esc(p.nota)})</i>` : ""}</span>
      <span class="spacer"></span>${p.status === "pendente" ? `<button class="link-btn" data-pend="em_execucao">Em execução</button>` : `<button class="link-btn" data-pend="pendente">Voltar a pendente</button>`}<button class="link-btn" data-pend="concluida">Concluir</button></div>`;
  }
  return "";
}
function renderThreadView() {
  const d = state.current, v = $("#thread-view"), msgs = d.messages;
  const notif = msgs.find(m => m.tipo === "TRIBUNAL");
  const labelChips = d.label_ids.map(id => labelById(d.account, id)).filter(l => l && l.type === "user").map(l => chipHtml(l, true)).join("");
  const lastUnreadIdx = msgs.length - 1;
  const spamMsg = msgs.find(m => (m.triagem || "").startsWith("resgatado") && m.label_ids.includes("SPAM"));
  const spamInfo = spamMsg ? spamMsg.triagem.split(":")[1] : "";
  const anuncio = msgs.some(m => m.triagem === "anuncio");
  v.innerHTML = `
    <div class="tv-tools">
      <button class="icon-btn" id="tv-back" title="Voltar para a lista">${ic("arrow_back")}</button>
      <button class="icon-btn" id="tv-unread" title="Marcar como não lida (somente no MarquesPro)">${ic("mark_email_unread")}</button>
      <div class="dropdown"><button class="icon-btn" id="tv-labels-btn" title="Marcadores">${ic("label")}</button><div class="menu hidden" id="tv-label-menu"></div></div>
      ${anuncio ? `<button class="tool-btn" id="tv-triagem" data-v="inbox">${ic("inbox", "sm")} Não é anúncio</button>` : `<button class="icon-btn" id="tv-triagem" data-v="anuncio" title="Marcar como anúncio (some da caixa de entrada; o Gmail não é alterado)">${ic("campaign")}</button>`}
      ${!(d.pendencia && d.pendencia.status !== "concluida") ? `<button class="icon-btn" id="tv-marcar-pend" title="Marcar como pendência (acompanhar até responder)">${ic("pending_actions")}</button>` : ""}
      <span class="local-note" title="Abrir aqui não marca a mensagem como lida no Gmail (${esc(d.account)})">${ic("visibility", "sm")}</span>
    </div>
    ${spamInfo ? `<div class="spam-banner">${ic("report")}<div><b>Esta conversa estava no spam do Gmail.</b> Foi trazida para a caixa de entrada porque ${spamInfo === "cliente" ? "o remetente é conhecido (já trocamos mensagens)" : "parece uma notificação judicial"}. Confira o remetente antes de abrir links ou anexos.</div><button class="btn" id="tv-nao-spam">Não é spam</button></div>` : ""}
    ${pendBanner(d)}
    ${d.sem_envio ? `<div class="envio-aviso">${ic("error", "sm")}<span>Nenhum e-mail enviado sobre esta notificação.</span><button class="link-btn" id="tv-escrever">Escrever e-mail ao cliente</button></div>` : ""}
    <div class="tv-head">
      <h2 class="tv-subject">${esc(msgs[0].subject)}${notif ? `<span class="chip notif">${ic("gavel", "sm")}${esc(notif.subtipo || "Notificação")}</span>` : ""}<span id="tv-labels">${labelChips}</span></h2>
    </div>
    ${msgs.map((m, i) => msgHtml(m, i, i === lastUnreadIdx || m.unread_gmail && i > msgs.length - 3)).join("")}
    <div class="reply-bar">
      <button class="pill" data-act="responder" data-mid="${msgs[msgs.length - 1].id}">${ic("reply")}Responder</button>
      ${replyAllUseful(msgs[msgs.length - 1]) ? `<button class="pill" data-act="responder_todos" data-mid="${msgs[msgs.length - 1].id}">${ic("reply_all")}Responder a todos</button>` : ""}
      <button class="pill" data-act="encaminhar" data-mid="${msgs[msgs.length - 1].id}">${ic("forward")}Encaminhar</button>
    </div>`;
  msgs.forEach((m, i) => renderBody(m, $(`#body-${i}`), false));
  $("#tv-back").onclick = () => { showList(); renderTabs(); renderThreads(); };
  $("#tv-unread").onclick = guard(async () => {
    await api(`/api/threads/${encodeURIComponent(d.account)}/${d.thread_id}/nao-lida`, {method: "POST"});
    const t = state.threads.find(x => x.thread_id === d.thread_id); if (t) t.read_local = false;
    showList(); renderTabs(); renderThreads(); refreshStatus();
  });
  if ($("#tv-escrever")) $("#tv-escrever").onclick = guard(async () => {
    // Abre o encaminhamento e já lê o documento/e-mail desta notificação (primeiro no computador, IA só se faltar)
    await startReply("encaminhar", d.account, msgs[msgs.length - 1].id);
    await abrirPainel("ia", "");
    executarIA();
  });
  const setPend = async (status, nota) => {
    await api(`/api/pendencias/${encodeURIComponent(d.account)}/${d.thread_id}`, {body: {status, nota: nota || "", message_id: d.pendencia ? d.pendencia.message_id : undefined}});
    await openThread(d.account, d.thread_id); toast(status === "concluida" ? "Tratativa concluída." : "Tratativa atualizada.");
  };
  $$("[data-pend]", v).forEach(b => b.onclick = guard(async () => {
    let nota = d.pendencia ? d.pendencia.nota : "";
    if (b.dataset.pend !== "pendente") { const r = prompt(b.dataset.pend === "concluida" ? "Como foi resolvido? (opcional)" : "O que está sendo feito? (opcional)", nota); if (r === null) return; nota = r; }
    await setPend(b.dataset.pend, nota);
  }));
  if ($("#tv-marcar-pend")) $("#tv-marcar-pend").onclick = guard(async () => { const r = prompt("Lembrete da pendência (opcional)", ""); if (r === null) return; await setPend("pendente", r); });
  if ($("#tv-nao-spam")) $("#tv-nao-spam").onclick = guard(async () => {
    await api(`/api/threads/${encodeURIComponent(d.account)}/${d.thread_id}/nao-spam`, {method: "POST"});
    toast("Conversa devolvida à caixa de entrada também no Gmail."); await openThread(d.account, d.thread_id);
  });
  $("#tv-triagem").onclick = guard(async (e) => {
    const v = e.currentTarget.dataset.v;
    await api(`/api/threads/${encodeURIComponent(d.account)}/${d.thread_id}/triagem`, {body: {valor: v}});
    toast(v === "anuncio" ? "Marcado como anúncio. Está em Mais > Anúncios e promoções." : "Voltou para a caixa de entrada."); await openThread(d.account, d.thread_id); refreshStatus();
  });
  $("#tv-labels-btn").onclick = (e) => { e.stopPropagation(); labelMenu($("#tv-label-menu"), d.account, d.label_ids, async (add, remove) => {
    await api("/api/threads/labels", {body: {account: d.account, thread_ids: [d.thread_id], add, remove}});
    await openThread(d.account, d.thread_id); toast("Marcadores atualizados no Gmail");
  }); };
  $$("#tv-labels .x").forEach(x => x.onclick = guard(async (e) => {
    e.stopPropagation();
    await api("/api/threads/labels", {body: {account: d.account, thread_ids: [d.thread_id], remove: [x.parentElement.dataset.label]}});
    await openThread(d.account, d.thread_id);
  }));
  $$(".msg-head", v).forEach(h => h.onclick = (e) => { if (!e.target.closest("button")) h.parentElement.classList.toggle("collapsed"); });
  $$("[data-act]", v).forEach(b => b.onclick = guard((e) => { e.stopPropagation(); return startReply(b.dataset.act, d.account, b.dataset.mid); }));
}

function replyAllUseful(m) {
  const n = (m.to_raw + "," + (m.cc_raw || "")).split(",").filter(x => x.includes("@")).length;
  return n > 1;
}

function toLine(m) {
  const me = new Set([state.current.account, ...state.sendAs.filter(s => s.account === state.current.account).map(s => s.email)]);
  const names = (m.to_raw || "").split(",").map(x => x.trim()).filter(Boolean).map(x => {
    const em = ((x.match(/<([^>]+)>/) || [, x])[1] || "").toLowerCase().trim();
    return me.has(em) ? "mim" : x.replace(/\s*<.*>/, "").replace(/"/g, "") || em;
  });
  return `para ${esc(names.join(", ") || "(sem destinatário)")}${m.cc_raw ? `, cc: ${esc(m.cc_raw.replace(/<[^>]+>/g, "").replace(/"/g, ""))}` : ""}`;
}

function msgHtml(m, i, expanded) {
  const name = m.from_name || m.from_email;
  const attsList = (m.body && m.body.attachments) || [];
  const atts = attsList.map(a =>
    `<a class="att-card" href="${attUrl(state.current.account, m.id, a)}" title="Baixar ${esc(a.filename)}">
      <span class="ic">${ic(/image/.test(a.mime_type) ? "image" : "description")}</span>
      <span class="nm">${ic("picture_as_pdf", "sm")}${esc(a.filename)}</span></a>`).join("");
  return `<div class="msg ${expanded ? "" : "collapsed"}">
    <div class="msg-head">
      <div class="avatar" style="background:${colorFor(m.from_email)}">${initial(name)}</div>
      <div class="msg-meta">
        <div class="msg-from"><b>${esc(name)}</b><span class="em">&lt;${esc(m.from_email)}&gt;</span>
          ${m.unread_gmail ? `<span class="chip notif" title="Status preservado para a controladoria">${ic("mark_email_unread", "sm")}não lida no Gmail</span>` : ""}</div>
        <div class="msg-to">${toLine(m)}</div>
        <div class="msg-snip">${esc(m.snippet)}</div>
      </div>
      <div class="msg-right">${fmtLong(m.internal_date)}
        <button class="icon-btn small" data-act="responder" data-mid="${m.id}" title="Responder">${ic("reply")}</button>
      </div>
    </div>
    <div class="msg-body"><div id="body-${i}"></div>
      ${atts ? `<div class="atts"><div class="atts-title">${attsList.length} anexo${attsList.length > 1 ? "s" : ""}</div>${atts}</div>` : ""}
    </div></div>`;
}

function renderBody(m, holder, showImages) {
  const b = m.body || {html: "", text: ""};
  let content = b.html || `<pre style="white-space:pre-wrap;font-family:inherit;margin:0">${esc(b.text)}</pre>`;
  content = content.replace(/<script[\s\S]*?<\/script>/gi, "").replace(/<meta[^>]+http-equiv[^>]*>/gi, "");
  const inline = b.inline || {};
  content = content.replace(/cid:([^"'\s)>]+)/gi, (s, cid) => {
    const id = inline[cid]; if (!id) return s;
    return attUrl(state.current.account, m.id, {attachment_id: id, filename: cid, mime_type: "image/png"}, true);
  });
  const hasRemote = /<img[^>]+src\s*=\s*["']?https?:/i.test(content) || /url\(\s*["']?https?:/i.test(content);
  const remote = showImages ? " https: http:" : "";
  const csp = `default-src 'none'; style-src 'unsafe-inline'${remote}; img-src data: ${location.origin}${remote}; font-src data:${remote}`;
  const doc = `<!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${csp}">
    <meta name="referrer" content="no-referrer"><base target="_blank"><style>body{font-family:Arial,Helvetica,sans-serif;font-size:14px;margin:0;word-wrap:break-word;color:#222}img{max-width:100%;height:auto}</style></head><body>${content}</body></html>`;
  holder.innerHTML = (hasRemote && !showImages)
    ? `<div class="img-warn">As imagens não são exibidas (evita aviso de leitura ao remetente). <button>Exibir imagens abaixo</button></div>` : "";
  const fr = document.createElement("iframe");
  fr.setAttribute("sandbox", "allow-same-origin allow-popups allow-popups-to-escape-sandbox");
  fr.srcdoc = doc;
  const fit = () => { try { fr.style.height = (fr.contentDocument.body.scrollHeight + 12) + "px"; } catch (_) {} };
  fr.onload = () => {
    try {
      const d = fr.contentDocument;
      d.querySelectorAll("a[href]").forEach(a => { a.target = "_blank"; a.rel = "noopener noreferrer"; });
      d.querySelectorAll("img").forEach(im => im.addEventListener("load", fit));
    } catch (_) {}
    fit();
  };
  holder.appendChild(fr);
  const btn = $(".img-warn button", holder);
  if (btn) btn.onclick = () => renderBody(m, holder, true);
}

// ─── Menu de marcadores ──────────────────────────────────────────────────
function labelMenu(menu, account, currentIds, onApply, opts = {}) {
  closeMenus(menu);
  if (!account) { toast("Escolha uma conta para gerenciar marcadores", true); return; }
  const labels = userLabels(account).sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
  const cur = new Set(currentIds || []);
  menu.innerHTML = `<div class="menu-title">Marcar como:</div>` + labels.map(l => `<label><input type="checkbox" value="${esc(l.id)}" ${cur.has(l.id) ? "checked" : ""}>
      <span class="dot" style="background:${esc(l.bg_color || "#c4c7c5")}"></span>${esc(l.name)}</label>`).join("")
    + `<div class="menu-foot"><button data-new>Criar novo</button><button data-ok>${opts.applyText || "Aplicar"}</button></div>`;
  menu.classList.remove("hidden");
  menu.onclick = (e) => e.stopPropagation();
  $("[data-ok]", menu).onclick = guard(async () => {
    const checked = new Set($$("input:checked", menu).map(i => i.value));
    const add = [...checked].filter(id => !cur.has(id));
    const remove = [...cur].filter(id => !checked.has(id) && labels.some(l => l.id === id));
    menu.classList.add("hidden");
    await onApply(add, remove, [...checked]);
  });
  $("[data-new]", menu).onclick = guard(async () => {
    const name = prompt("Nome do novo marcador (use / para aninhar, ex.: MarquesPro/Tribunal):");
    if (!name) return;
    await api("/api/labels", {body: {account, name}});
    await loadLabels();
    labelMenu(menu, account, currentIds, onApply, opts);
  });
}
function closeMenus(except) {
  $$(".menu").forEach(m => { if (m !== except) m.classList.add("hidden"); });
  $$(".ac").forEach(a => a.classList.add("hidden"));
}

// ─── Nova mensagem ───────────────────────────────────────────────────────
const compose = {mode: "novo", account: "", ref: null, files: [], labels: [], fwdAtts: []};

function fromOptions(onlyAccount) {
  const list = state.sendAs.filter(s => !onlyAccount || s.account === onlyAccount);
  state.accounts.map(a => a.email).filter(a => !onlyAccount || a === onlyAccount).forEach(a => {
    if (!list.some(s => s.account === a && s.email === a)) list.push({account: a, email: a, display_name: "", signature: ""});
  });
  return list;
}

function openCompose(ctx = {}) {
  if (!state.accounts.length) { toast("Conecte uma conta primeiro", true); openSettings("tab-accounts"); return; }
  Object.assign(compose, {refSubject: ctx.subject || "", mode: ctx.mode || "novo", account: ctx.account || "", ref: ctx.ref || null, files: [],
    labels: ctx.labels || [], fwdAtts: ctx.attachments || []});
  const opts = fromOptions(ctx.account || "");
  const sel = $("#c-from");
  sel.innerHTML = opts.map(s => `<option value="${esc(s.account + "|" + s.email)}">${esc(s.display_name ? `${s.display_name} <${s.email}>` : s.email)}</option>`).join("");
  const pref = (ctx.fromEmail && opts.find(s => s.email === ctx.fromEmail))
    || opts.find(s => s.account === (state.account || s.account) && s.is_default) || opts[0];
  if (pref) sel.value = pref.account + "|" + pref.email;
  $("#c-to").value = ctx.to || "";
  $("#c-cc").value = ctx.cc || ""; $("#c-bcc").value = "";
  $("#c-cc-row").classList.toggle("hidden", !ctx.cc); $("#c-bcc-row").classList.add("hidden");
  $("#c-subject").value = ctx.subject || "";
  $("#compose-title").textContent = ctx.subject || "Nova mensagem";
  const ed = $("#c-editor");
  ed.innerHTML = `<div><br></div><div class="sig" data-sig></div>${ctx.quoted ? `<div data-quoted>${sanitizeHtml(ctx.quoted)}</div>` : ""}`;
  applySignature();
  $("#c-fwd-att").classList.toggle("hidden", !(compose.mode === "encaminhar" && compose.fwdAtts.length));
  $("#c-fwd-att-list").textContent = compose.fwdAtts.map(a => a.filename).join(", ");
  $("#c-fwd-att-chk").checked = true;
  renderComposeFiles(); renderComposeLabels();
  $("#c-status").textContent = "";
  $("#compose").classList.remove("hidden", "min", "max");
  const range = document.createRange(); range.setStart(ed.firstChild, 0); range.collapse(true);
  if (ctx.to) { ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(range); } else $("#c-to").focus();
}

function currentFrom() {
  const [account, email] = ($("#c-from").value || "|").split("|");
  return {account, email, info: state.sendAs.find(s => s.account === account && s.email === email)};
}
function applySignature() {
  const {info, account} = currentFrom();
  const sig = $("#c-editor [data-sig]");
  if (sig) sig.innerHTML = info && info.signature ? `<br>${sanitizeHtml(info.signature)}` : "";
  if (compose.account && compose.account !== account) compose.labels = [];
  compose.account = account;
  renderComposeLabels();
}
function renderComposeFiles() {
  $("#c-files").innerHTML = compose.files.map((f, i) => `<span class="att-chip">${ic("description", "sm")}${esc(f.name)} <span class="ms sm x" data-i="${i}" title="Remover">close</span></span>`).join("");
  $$("#c-files .x").forEach(x => x.onclick = () => { compose.files.splice(+x.dataset.i, 1); renderComposeFiles(); });
}
function renderComposeLabels() {
  const acc = currentFrom().account;
  const chips = compose.labels.map(id => labelById(acc, id)).filter(Boolean).map(l => chipHtml(l, true)).join("");
  $("#c-labels-row").classList.toggle("hidden", !chips);
  $("#c-label-chips").innerHTML = chips;
  $$("#c-label-chips .x").forEach(x => x.onclick = () => { compose.labels = compose.labels.filter(id => id !== x.parentElement.dataset.label); renderComposeLabels(); });
}

async function startReply(mode, account, messageId) {
  const c = await api(`/api/compose-context/${encodeURIComponent(account)}/${messageId}?mode=${mode}`);
  openCompose({mode, account, ref: messageId, to: c.to, cc: c.cc, subject: c.subject, quoted: c.quoted,
    fromEmail: c.from_email, labels: c.label_ids, attachments: c.attachments});
}

async function sendCompose() {
  const {account, email} = currentFrom();
  if ($("#c-editor mark.ph") || /\[PREENCHER/.test($("#c-subject").value)) {
    if (!confirm("Ainda há campos [PREENCHER] sem preencher no e-mail. Enviar mesmo assim?")) return;
  }
  const fd = new FormData();
  fd.append("account", account); fd.append("from_email", email);
  fd.append("to", $("#c-to").value); fd.append("cc", $("#c-cc").value); fd.append("bcc", $("#c-bcc").value);
  fd.append("subject", $("#c-subject").value);
  fd.append("html", $("#c-editor").innerHTML);
  fd.append("mode", compose.mode);
  if (compose.ref) fd.append("ref_message_id", compose.ref);
  fd.append("incluir_anexos", $("#c-fwd-att-chk").checked ? "1" : "0");
  fd.append("labels", JSON.stringify(compose.labels));
  compose.files.forEach(f => fd.append("anexos", f, f.name));
  const btn = $("#c-send");
  btn.disabled = true; $("#c-status").textContent = "Enviando…";
  try {
    await api("/api/send", {body: fd});
    $("#compose").classList.add("hidden");
    toast("Mensagem enviada.");
    if (state.current && !$("#thread-view").classList.contains("hidden")) await openThread(state.current.account, state.current.thread_id);
    else await loadThreads();
  } catch (e) { $("#c-status").textContent = ""; toast(e.message, true); }
  finally { btn.disabled = false; }
}

// Autocompletar destinatários (nome aparece junto ao e-mail)
// Grupos de empresas / subgrupos de destinatários
function mesclarEmails(input, lista) {
  const atual = input.value.split(",").map(x => x.trim()).filter(Boolean);
  const ja = new Set(atual.map(x => ((x.match(/<([^>]+)>/) || [, x])[1] || "").toLowerCase()));
  (lista || "").split(",").map(x => x.trim()).filter(Boolean).forEach(e => { if (!ja.has(e.toLowerCase())) { atual.push(e); ja.add(e.toLowerCase()); } });
  input.value = atual.length ? atual.join(", ") + ", " : "";
}
function aplicarGrupo(g, alvo) {
  const juntos = [g.para, g.cc, g.cco].filter(Boolean).join(", ");
  if (alvo === "c-cc") { $("#c-cc-row").classList.remove("hidden"); mesclarEmails($("#c-cc"), juntos); }
  else if (alvo === "c-bcc") { $("#c-bcc-row").classList.remove("hidden"); mesclarEmails($("#c-bcc"), juntos); }
  else {
    mesclarEmails($("#c-to"), g.para || (g.cc || g.cco ? "" : ""));
    if (g.cc) { $("#c-cc-row").classList.remove("hidden"); mesclarEmails($("#c-cc"), g.cc); }
    if (g.cco) { $("#c-bcc-row").classList.remove("hidden"); mesclarEmails($("#c-bcc"), g.cco); }
  }
  toast(`E-mails padrão de ${g.name} adicionados.`);
}
async function menuGrupos() {
  const menu = $("#c-grupos-menu"); closeMenus(menu);
  const gs = await api("/api/grupos");
  const n = (sg) => [sg.para, sg.cc, sg.cco].filter(Boolean).join(",").split(",").filter(Boolean).length;
  menu.innerHTML = (gs.length ? gs.map(e => `<div class="menu-title">${esc(e.nome)}</div>` + (e.subgrupos.length
      ? e.subgrupos.map(sg => `<div class="mi" data-e="${e.id}" data-s="${sg.id}">${ic("groups", "sm")}<span>${esc(sg.nome)}</span><small>${n(sg)} e-mail(s)</small></div>`).join("")
      : `<div class="mi off">Sem subgrupos</div>`)).join("") : `<div class="menu-title">Nenhum grupo cadastrado</div>`)
    + `<div class="menu-foot"><button data-gerir>Gerenciar grupos…</button></div>`;
  menu.classList.remove("hidden");
  menu.onclick = (e) => e.stopPropagation();
  $$(".mi[data-s]", menu).forEach(d => d.onclick = () => {
    const e = gs.find(x => x.id == d.dataset.e), sg = e.subgrupos.find(x => x.id == d.dataset.s);
    menu.classList.add("hidden"); aplicarGrupo({name: `${e.nome} › ${sg.nome}`, para: sg.para, cc: sg.cc, cco: sg.cco}, "c-to");
  });
  $("[data-gerir]", menu).onclick = () => { menu.classList.add("hidden"); openSettings("tab-grupos"); };
}
async function renderGrupos() {
  const gs = await api("/api/grupos"), box = $("#g-lista");
  box.innerHTML = gs.map(e => `<div class="card" data-eid="${e.id}">
    <div class="g-head"><b>${esc(e.nome)}</b>${e.observacao ? `<span class="muted"> · ${esc(e.observacao)}</span>` : ""}<span class="spacer"></span>
      <button class="btn danger" data-del-emp="${e.id}">Excluir empresa</button></div>
    <table class="rules"><thead><tr><th>Subgrupo</th><th>Para</th><th>Cc</th><th>Cco</th><th></th></tr></thead><tbody>
      ${e.subgrupos.map(sg => `<tr><td>${esc(sg.nome)}</td><td>${esc(sg.para)}</td><td>${esc(sg.cc)}</td><td>${esc(sg.cco)}</td>
        <td><button class="btn" data-edit-sg='${esc(JSON.stringify(sg))}'>Editar</button> <button class="btn danger" data-del-sg="${sg.id}">Excluir</button></td></tr>`).join("")
        || `<tr><td colspan="5" class="muted">Nenhum subgrupo ainda.</td></tr>`}</tbody></table>
    <div class="g-form" data-form="${e.id}"><input data-f="nome" placeholder="Subgrupo (ex.: RH, Jurídico, Diretoria)"><input data-f="para" placeholder="Para (e-mails separados por vírgula)">
      <input data-f="cc" placeholder="Cc"><input data-f="cco" placeholder="Cco"><input type="hidden" data-f="id">
      <button class="btn primary" data-save-sg="${e.id}">Salvar subgrupo</button></div></div>`).join("") || `<p class="muted">Nenhuma empresa cadastrada.</p>`;
}

function setupAutocomplete(input) {
  const box = $(".ac", input.parentElement);
  let timer, items = [], on = -1;
  const pick = (c) => {
    if (c.grupo) {  // grupo cadastrado: troca o texto digitado pelos e-mails padrão
      const resto = input.value.split(",").slice(0, -1).join(",").trim();
      input.value = resto ? resto + ", " : "";
      box.classList.add("hidden"); aplicarGrupo(c, input.id); input.focus(); return;
    }
    const parts = input.value.split(",");
    parts[parts.length - 1] = " " + (c.name ? `${c.name} <${c.email}>` : c.email);
    input.value = parts.join(",").replace(/^\s+/, "") + ", ";
    box.classList.add("hidden"); input.focus();
  };
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const term = input.value.split(",").pop().trim();
    if (term.length < 2) { box.classList.add("hidden"); return; }
    timer = setTimeout(guard(async () => {
      items = await api(`/api/contacts?q=${encodeURIComponent(term)}`); on = -1;
      if (!items.length) { box.classList.add("hidden"); return; }
      box.innerHTML = items.map((c, i) => `<div data-i="${i}"><span class="av" style="background:${c.grupo ? "#188038" : colorFor(c.email)}">${c.grupo ? ic("groups", "sm") : initial(c.name || c.email)}</span>
        <span>${esc(c.name || c.email)}<small>${esc(c.email)}</small></span></div>`).join("");
      $$("div[data-i]", box).forEach(d => d.onmousedown = (e) => { e.preventDefault(); pick(items[+d.dataset.i]); });
      box.classList.remove("hidden");
    }), 200);
  });
  input.addEventListener("keydown", (e) => {
    if (box.classList.contains("hidden")) return;
    const ds = $$("div[data-i]", box);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); on = (on + (e.key === "ArrowDown" ? 1 : -1) + ds.length) % ds.length;
      ds.forEach((d, i) => d.classList.toggle("on", i === on));
    } else if (e.key === "Enter" && on >= 0) { e.preventDefault(); pick(items[on]); }
    else if (e.key === "Escape") box.classList.add("hidden");
  });
  input.addEventListener("blur", () => setTimeout(() => box.classList.add("hidden"), 150));
}

// ─── Modelos de e-mail do escritório e preenchimento por IA ─────────────
const MOD = {lista: null, aba: "modelo", arquivos: [], ia: null, slashIdx: 0, slashItens: [], preenchido: null};
const BR_ISO = (v) => (/^\d{2}\/\d{2}\/\d{4}$/.test(v || "") ? v.split("/").reverse().join("-") : (v || ""));
const ORIGEM_TXT = {documento: "do documento", automatico: "automático", ia: "pela IA", verificar: "IA: confira", corrigido: "IA corrigiu: confira", regra: "regra do escritório", derivado: "deduzido", pendente: "preencher"};
const AUTO_ITEM = {codigo: "IA", titulo: "Preencher a partir de um documento ou do e-mail aberto (automático)", grupo: "Automático", auto: true};
const ROTULOS = {PROCESSO: "Nº do processo", RECLAMANTE: "Reclamante", RECLAMADA: "Reclamada", DATA: "Data", HORARIO: "Horário",
  MODALIDADE: "Modalidade (presencial, telepresencial, híbrida)", PERIODO: "Saudação (bom dia / boa tarde)", PRAZO_INTERNO: "Prazo interno para envio",
  LINK: "Link", QUANTIDADE_TESTEMUNHAS: "Quantidade de testemunhas", NOME_CLIENTE: "Nome do cliente", TIPO_AUDIENCIA: "Tipo de audiência"};
const rotulo = (c) => ROTULOS[c] || (c.charAt(0) + c.slice(1).toLowerCase().replace(/_/g, " "));
const ehLongo = (c) => /^(LISTA_|FUNDAMENTOS|BLOCO_|DOCUMENTOS|DESCRICAO|MOTIVO|RESUMO)/.test(c);

async function carregarModelos() {
  if (!MOD.lista) MOD.lista = await api("/api/modelos");
  return MOD.lista;
}
const modeloAtual = () => (MOD.lista || []).find(m => m.codigo === $("#mp-modelo").value);
const ISO_BR = (v) => (/^\d{4}-\d{2}-\d{2}$/.test(v) ? v.split("-").reverse().join("/") : v);

function preencherTexto(t, valores) {
  return t.replace(/\{\{([A-Z0-9_]+)\}\}/g, (_, c) => ((valores[c] || "").trim() || `[PREENCHER: ${c}]`));
}
function montarEmail(m, valores, blocos) {
  let corpo = m.corpo.replace(/\{\{(BLOCO_[A-Z0-9_]+)\}\}/g, (_, b) => { const sel = blocos[b]; return sel && sel.incluir ? sel.texto : ""; });
  corpo = corpo.replace(/\n{3,}/g, "\n\n");
  return {assunto: preencherTexto(m.assunto || "", valores), corpo: preencherTexto(corpo, valores)};
}
function textoParaHtml(t) {
  return t.split(/\n\s*\n/).map(p => `<div>${esc(p).replace(/\n/g, "<br>").replace(/\[PREENCHER: ([^\]]+)\]/g, '<mark class="ph">[PREENCHER: $1]</mark>')}</div>`).join("<div><br></div>");
}
function inserirNoEditor(assunto, corpo) {
  const ed = $("#c-editor");
  ed.querySelectorAll("[data-modelo]").forEach(n => n.remove());
  const box = document.createElement("div"); box.dataset.modelo = "";
  box.innerHTML = textoParaHtml(corpo);
  const first = ed.firstElementChild;
  if (first && !("sig" in first.dataset) && !("quoted" in first.dataset) && first.textContent.trim() === "") first.remove();
  ed.insertBefore(box, ed.querySelector("[data-sig]") || ed.firstChild);
  if (assunto) { $("#c-subject").value = assunto; $("#compose-title").textContent = assunto; }
  ed.focus();
}

function abrirPainel(aba, codigo) {
  MOD.aba = aba || "modelo";
  $("#slash-menu").classList.add("hidden");
  return carregarModelos().then(lista => {
    const sel = $("#mp-modelo");
    const grupos = {};
    lista.forEach(m => (grupos[m.grupo || "Outros"] = grupos[m.grupo || "Outros"] || []).push(m));
    sel.innerHTML = `<option value="">Automático (a IA escolhe o modelo)</option>` + Object.entries(grupos).map(([g, ms]) =>
      `<optgroup label="${esc(g)}">${ms.map(m => `<option value="${m.codigo}">${m.codigo} — ${esc(m.titulo)}</option>`).join("")}</optgroup>`).join("");
    sel.value = codigo || "";
    $("#modelo-panel").classList.remove("hidden");
    $("#mp-usar-email-row").classList.toggle("hidden", !compose.ref);
    trocarAba(MOD.aba);
  }).catch(e => toast(e.message, true));
}
function fecharPainel() { MOD.preenchido = null; $("#modelo-panel").classList.add("hidden"); }
function trocarAba(aba) {
  MOD.aba = aba;
  $$("[data-mtab]").forEach(b => b.classList.toggle("on", b.dataset.mtab === aba));
  $("#mp-modelo-pane").classList.toggle("hidden", aba !== "modelo");
  $("#mp-ia-pane").classList.toggle("hidden", aba !== "ia");
  $("#mp-inserir").classList.toggle("hidden", aba !== "modelo");
  if (aba === "modelo") renderFormModelo(); else renderIA();
}

function renderFormModelo() {
  const pane = $("#mp-modelo-pane"), m = modeloAtual();
  const pre = MOD.preenchido && m && MOD.preenchido.codigo === m.codigo ? MOD.preenchido : null;
  $("#mp-confirma-row").classList.toggle("hidden", !pre);
  $("#mp-confirmo").checked = false;
  $("#mp-inserir").textContent = pre ? "Confirmar e inserir" : "Inserir no e-mail";
  if (!m) { pane.innerHTML = `<p class="muted">Escolha um modelo acima, ou digite <b>/</b> no texto do e-mail para buscar pelo nome. Para escolher e preencher sozinho a partir de um documento, use a aba "Preencher com IA".</p>`; $("#mp-inserir").disabled = true; return; }
  $("#mp-inserir").disabled = !!pre;  // com dados lidos do documento, só habilita depois que o advogado confere
  const processo = ((compose.refSubject || "").match(/\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}/) || [""])[0];
  const campos = m.campos.map(c => {
    const id = `mpc-${c}`, cv = pre && pre.campos[c];
    const origem = cv ? (!cv.valor ? "pendente" : cv.corrigido_de ? "corrigido" : cv.verificar ? "verificar" : cv.origem) : "";
    const valor = cv ? cv.valor : (c === "PROCESSO" ? processo : "");
    const tip = cv && (cv.trecho || cv.corrigido_de) ? ` title="${cv.corrigido_de ? `Leitura local era: ${esc(cv.corrigido_de)}. ` : ""}${cv.trecho ? `No documento: ${esc(cv.trecho)}` : ""}"` : "";
    const tag = origem ? `<span class="orig o-${origem}">${ORIGEM_TXT[origem]}</span>` : "";
    const cls = origem ? `org-${origem}` : "";
    if (c === "DATA") return `<label>${rotulo(c)} ${tag}<input id="${id}" class="${cls}"${tip} data-campo="${c}" type="date" value="${esc(BR_ISO(valor))}"></label>`;
    if (c === "PROCESSO") return `<label class="wide">${rotulo(c)} ${tag}<input id="${id}" class="${cls}"${tip} data-campo="${c}" value="${esc(valor)}" placeholder="0000000-00.0000.0.00.0000"></label>`;
    return ehLongo(c) ? `<label class="wide">${rotulo(c)} ${tag}<textarea id="${id}" class="${cls}"${tip} data-campo="${c}" rows="3">${esc(valor)}</textarea></label>`
      : `<label>${rotulo(c)} ${tag}<input id="${id}" class="${cls}"${tip} data-campo="${c}" value="${esc(valor)}"></label>`;
  }).join("");
  const blocos = Object.entries(m.blocos).map(([b, bl]) => {
    const vazio = !bl.texto.trim(), pb = pre && pre.blocos && pre.blocos[b];
    const incluir = pb ? pb.incluir : (vazio || !bl.condicao);
    const texto = pb && pb.texto != null ? pb.texto : bl.texto;
    return `<div class="mp-bloco" data-bloco="${b}">
      <label class="tit"><input type="checkbox" data-incluir ${incluir ? "checked" : ""}> <span>${rotulo(b.replace(/^BLOCO_/, ""))}${bl.condicao ? `<div class="cond">${esc(bl.condicao)}</div>` : ""}</span></label>
      <textarea data-bloco-texto aria-label="Texto do bloco" placeholder="${vazio ? "Escreva este trecho (o modelo não traz texto-base)." : ""}">${esc(texto)}</textarea></div>`;
  }).join("");
  let banner = "";
  if (pre) {
    const u = pre.uso || {};
    const uso = u.ia ? `IA usada em ${u.chamadas} consulta(s), cerca de ${((u.entrada || 0) + (u.saida || 0)).toLocaleString("pt-BR")} tokens.` : "Lido no seu computador, sem usar a IA (0 tokens).";
    banner = `<div class="mp-confirma"><b>Confira os dados antes de inserir.</b> Modelo ${esc(pre.codigo)} — ${esc(pre.titulo)}${pre.confianca !== "alta" ? " (sugerido: troque acima se não for o certo)" : ""}.
      <div class="leg"><span class="orig o-documento">do documento</span><span class="orig o-ia">pela IA</span><span class="orig o-corrigido">IA corrigiu: confira</span><span class="orig o-verificar">IA: confira</span><span class="orig o-regra">regra do escritório</span><span class="orig o-pendente">preencher</span></div>
      <div class="muted">${uso}${pre.observacoes ? " " + esc(pre.observacoes) : ""}</div>
      ${MOD.semIA ? `<div class="mp-semia"><b>A IA não completou os campos em branco porque não há chave configurada.</b> <button class="link-btn" id="mp-ir-chave">Configurar chave e completar com a IA</button></div>` : ""}</div>`;
  }
  pane.innerHTML = `${banner}<div class="mp-campos">${campos || '<span class="muted">Este modelo não tem campos variáveis.</span>'}</div>${blocos}
    ${m.regras ? `<details class="mp-regras"><summary>Orientações do modelo (não vão no e-mail)</summary>${esc(m.regras).replace(/\n/g, "<br>")}</details>` : ""}`;
  const bc = $("#mp-ir-chave"); if (bc) bc.onclick = () => abrirPainel("ia", "");
}
function lerFormModelo() {
  const valores = {};
  $$("#mp-modelo-pane [data-campo]").forEach(i => { valores[i.dataset.campo] = i.type === "date" ? ISO_BR(i.value) : i.value; });
  const blocos = {};
  $$("#mp-modelo-pane [data-bloco]").forEach(d => { blocos[d.dataset.bloco] = {incluir: $("[data-incluir]", d).checked, texto: $("[data-bloco-texto]", d).value}; });
  return {valores, blocos};
}
function inserirModelo() {
  const m = modeloAtual(); if (!m) return;
  const {valores, blocos} = lerFormModelo();
  const r = montarEmail(m, valores, blocos);
  inserirNoEditor(r.assunto, r.corpo);
  fecharPainel();
  const pend = (r.corpo.match(/\[PREENCHER: [^\]]+\]/g) || []).length;
  toast(pend ? `Modelo ${m.codigo} inserido. ${pend} campo(s) a preencher, destacados em amarelo.` : `Modelo ${m.codigo} inserido.`);
}

async function renderIA() {
  MOD.aguardaChave = !!MOD.semIA;
  MOD.ia = await api("/api/ia/status");
  $("#mp-ia-key").classList.toggle("hidden", MOD.ia.configurada);  // a chave só é necessária para completar o que faltar
  $("#mp-key-remover").classList.toggle("hidden", MOD.ia.origem !== "arquivo local");
  renderArquivosIA();
}
function renderArquivosIA() {
  $("#mp-arquivos-lista").innerHTML = MOD.arquivos.map((f, i) => `<span class="att-chip">${ic("description", "sm")}${esc(f.name)} <span class="ms sm x" data-i="${i}" title="Remover">close</span></span>`).join("");
  $$("#mp-arquivos-lista .x").forEach(x => x.onclick = () => { MOD.arquivos.splice(+x.dataset.i, 1); renderArquivosIA(); });
}
function adicionarArquivosIA(files) {
  for (const f of files) {
    if (!/^(application\/pdf|image\/(png|jpeg|webp|gif))$/.test(f.type)) { toast(`Formato não aceito: ${f.name}. Use PDF, PNG ou JPG.`, true); continue; }
    MOD.arquivos.push(f);
  }
  renderArquivosIA();
}
async function executarIA(aceitarVisao) {
  const btn = $("#mp-ia-run"), res = $("#mp-ia-result");
  const fd = new FormData();
  fd.append("codigo", $("#mp-modelo").value);
  fd.append("instrucoes", $("#mp-instrucoes").value);
  if (aceitarVisao === true) fd.append("aceitar_visao", "1");
  if (compose.ref && $("#mp-usar-email").checked) { fd.append("account", compose.account); fd.append("ref_message_id", compose.ref); }
  MOD.arquivos.forEach(f => fd.append("arquivos", f, f.name));
  btn.disabled = true; $("#mp-status").textContent = "Lendo o documento…"; res.classList.add("hidden");
  try {
    const r = await api("/api/ia/preencher", {body: fd});
    if (r.precisa_visao) {
      if (confirm(`O arquivo ${r.precisa_visao.join(", ")} é imagem ou PDF escaneado (sem texto). Para lê-lo, será enviado à IA, o que gasta mais tokens. Enviar?`)) return await executarIA(true);
      return;
    }
    MOD.preenchido = r;
    MOD.semIA = !!r.ia_indisponivel && (r.pendencias || []).some(c => c !== "PRAZO_INTERNO");
    if (!MOD.semIA) MOD.arquivos = [];   // sem chave: mantém os arquivos para completar com a IA depois
    await abrirPainel("modelo", r.codigo);   // mostra os dados para o advogado conferir
  } catch (e) { res.classList.remove("hidden"); res.textContent = e.message; }
  finally { btn.disabled = false; $("#mp-status").textContent = ""; }
}

// Menu "/" para buscar modelos pelo nome ou código
function filtrarModelos(q) {
  q = q.trim().toLowerCase();
  return (MOD.lista || []).filter(m => !q || `${m.codigo} ${m.titulo} ${m.grupo}`.toLowerCase().includes(q)).slice(0, 40);
}
function mostrarSlash(q) {
  const menu = $("#slash-menu");
  carregarModelos().then(() => {
    const qq = q.trim();
    MOD.slashItens = (!qq || /^(ia|aut|anex|doc|preen)/i.test(qq) ? [AUTO_ITEM] : []).concat(filtrarModelos(q)); MOD.slashIdx = 0;
    let ultimo = "";
    menu.innerHTML = MOD.slashItens.length ? MOD.slashItens.map((m, i) => {
      const g = m.grupo !== ultimo ? `<div class="grp">${esc(m.grupo)}</div>` : ""; ultimo = m.grupo;
      return `${g}<div class="it ${i === 0 ? "on" : ""}" role="option" data-i="${i}"><span class="cod ${m.auto ? "auto" : ""}">${m.codigo}</span><span>${esc(m.titulo)}</span></div>`;
    }).join("") : `<div class="vazio">Nenhum modelo encontrado para "${esc(q)}".</div>`;
    menu.classList.remove("hidden");
    $$(".it", menu).forEach(d => d.onmousedown = (e) => { e.preventDefault(); escolherSlash(+d.dataset.i); });
  }).catch(() => {});
}
function escolherSlash(i) {
  const m = MOD.slashItens[i]; if (!m) return;
  limparGatilhoSlash();
  if (m.auto) {  // com e-mail aberto ou arquivo já anexado, preenche na hora
    abrirPainel("ia", "").then(() => { if (compose.ref || MOD.arquivos.length) executarIA(); });
    return;
  }
  abrirPainel("modelo", m.codigo);
}
function limparGatilhoSlash() {
  const sub = $("#c-subject");
  if (sub.value.startsWith("/")) { sub.value = ""; $("#compose-title").textContent = "Nova mensagem"; }
  const sel = getSelection();
  if (sel.rangeCount && $("#c-editor").contains(sel.anchorNode) && sel.anchorNode.nodeType === 3) {
    const n = sel.anchorNode, antes = n.textContent.slice(0, sel.anchorOffset), m = antes.match(/(^|\s)\/[^\s/]*$/);
    if (m) { const ini = antes.length - m[0].length + m[1].length; n.textContent = n.textContent.slice(0, ini) + n.textContent.slice(sel.anchorOffset); const r = document.createRange(); r.setStart(n, ini); r.collapse(true); sel.removeAllRanges(); sel.addRange(r); }
  }
}
function gatilhoSlashNoEditor() {
  const sel = getSelection();
  if (!sel.rangeCount || !$("#c-editor").contains(sel.anchorNode) || sel.anchorNode.nodeType !== 3) return null;
  const antes = sel.anchorNode.textContent.slice(0, sel.anchorOffset);
  const m = antes.match(/(^|\s)\/([^\s/]{0,30})$/);
  return m ? m[2] : null;
}
function teclaSlash(e) {
  const menu = $("#slash-menu");
  if (menu.classList.contains("hidden")) return;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault(); const n = MOD.slashItens.length || 1;
    MOD.slashIdx = (MOD.slashIdx + (e.key === "ArrowDown" ? 1 : -1) + n) % n;
    $$(".it", menu).forEach((d, i) => d.classList.toggle("on", i === MOD.slashIdx));
    const on = $(".it.on", menu); if (on) on.scrollIntoView({block: "nearest"});
  } else if (e.key === "Enter" || e.key === "Tab") { if (MOD.slashItens.length) { e.preventDefault(); escolherSlash(MOD.slashIdx); } }
  else if (e.key === "Escape") { e.preventDefault(); menu.classList.add("hidden"); }
}

// ─── Contadores e notificações ───────────────────────────────────────────
async function refreshStatus() {
  let s;
  try { s = await api(`/api/status?${qs({account: state.account, desde: state.lastNotif ?? 0})}`); }
  catch (e) {
    // o programa local não respondeu: sem ele nada chega aqui, então avisa em vez de parecer "tudo em dia"
    state.offline = true; renderIntegridade(); return;
  }
  state.offline = false;
  const first = state.lastNotif === null;
  state.status = s;
  $("#counter-num").textContent = s.recebidas_hoje;
  const nh = s.notificacoes.hoje;
  $("#notif-num").textContent = nh;
  if (!first && state.notifHoje != null && nh > state.notifHoje) {
    const c = $("#counter-notif"); c.classList.remove("pulse"); void c.offsetWidth; c.classList.add("pulse");
    toast(`${nh - state.notifHoje} nova(s) notificação(ões) judicial(is).`);
  }
  state.notifHoje = nh;
  if (!first && s.novas.length) {
    s.novas.slice(0, 3).forEach(n => {
      if ("Notification" in window && Notification.permission === "granted") {
        const nt = new Notification(n.from_name || "Novo e-mail", {body: n.subject || "", tag: n.message_id});
        nt.onclick = () => { window.focus(); openThread(n.account, n.thread_id); };
      }
    });
    if (!$("#thread-list").classList.contains("hidden")) loadThreads();
  }
  state.lastNotif = s.ultimo_id;
  renderIntegridade();
  document.title = (s.integridade && s.integridade.nivel === "erro" ? "⚠ " : "") + (s.nao_lidas_local ? `Caixa de entrada (${s.nao_lidas_local})` : "Caixa de entrada") + " - MarquesPro Mail";
  renderSidebar();
  if (!$("#tabs-inbox").classList.contains("hidden")) renderTabs();
  if (!$("#counter-pop").classList.contains("hidden")) renderCounterPop();
}
// ─── Integridade Gmail × MarquesPro ──────────────────────────────────────────
const NIVEL_INFO = {ok: {icon: "verified_user", lbl: "Gmail sincronizado"}, atencao: {icon: "warning", lbl: "Atenção na sincronização"}, erro: {icon: "gpp_bad", lbl: "Falha na sincronização"}};
function renderIntegridade() {
  const i = state.status && state.status.integridade;
  const off = state.offline;
  const nivel = off ? "erro" : (i ? i.nivel : "ok");
  const info = NIVEL_INFO[nivel];
  const btn = $("#btn-integ");
  btn.className = `pill-count integ ${nivel}`;
  btn.querySelector(".ms").textContent = off ? "cloud_off" : info.icon;
  $("#integ-lbl").textContent = off ? "Sem comunicação" : info.lbl;
  btn.title = off ? "Sem comunicação com o MarquesPro" : `${info.lbl}. Clique para ver a conferência com o Gmail.`;
  const ban = $("#integ-banner");
  if (off) {
    ban.className = "integ-banner erro";
    ban.innerHTML = `${ic("cloud_off")}<div><b>O MarquesPro não está respondendo neste computador.</b> Enquanto isso, nenhum e-mail novo do Gmail chega aqui. Verifique se a janela do programa está aberta e tente novamente.</div><button class="btn" id="integ-retry">Tentar de novo</button>`;
    $("#integ-retry").onclick = guard(refreshStatus);
    return;
  }
  if (!i || i.nivel === "ok") { ban.className = "integ-banner hidden"; ban.innerHTML = ""; return; }
  const acoes = {reconectar: `<button class="btn primary" data-ia="reconectar">Reconectar conta</button>`, verificar: `<button class="btn" data-ia="verificar">Verificar agora</button>`, reconhecer: `<button class="btn" data-ia="reconhecer">Entendi</button>`};
  ban.className = `integ-banner ${i.nivel}`;
  ban.innerHTML = `${ic(info.icon)}<div><b>${esc(info.lbl)}.</b> ${esc(i.mensagem)}${i.conta ? ` <span class="muted">(${esc(i.conta)})</span>` : ""}</div>
    <button class="btn" data-ia="detalhes">Detalhes</button>${acoes[i.acao] || ""}`;
  $$("[data-ia]", ban).forEach(b => b.onclick = guard(() => acaoIntegridade(b.dataset.ia)));
  if (i.nivel === "erro" && state.integAvisado !== i.mensagem) {
    state.integAvisado = i.mensagem;
    if ("Notification" in window && Notification.permission === "granted") new Notification("MarquesPro: falha na sincronização com o Gmail", {body: i.mensagem, tag: "integ"});
  }
  if (i.nivel !== "erro") state.integAvisado = null;
}
async function acaoIntegridade(a) {
  if (a === "reconectar") { openSettings("tab-accounts"); return; }
  if (a === "detalhes") { await abrirIntegridade(); return; }
  if (a === "reconhecer") { await api("/api/integridade/reconhecer", {method: "POST"}); await refreshStatus(); await abrirIntegridade(true); return; }
  if (a === "verificar") {
    toast("Conferindo tudo o que está no Gmail…");
    const r = await api("/api/integridade/verificar", {method: "POST"});
    const rec = r.resultados.reduce((n, x) => n + (x.recuperados || 0), 0), err = r.resultados.find(x => x.erro || x.pendentes);
    toast(err ? `A conferência encontrou problema: ${err.erro || err.pendentes + " e-mail(s) não chegaram"}` : rec ? `Conferido: ${rec} e-mail(s) que faltavam foram recuperados.` : "Conferido: tudo o que está no Gmail está aqui.", !!err);
    await refreshStatus(); await loadThreads(); if (!$("#integ-pop").classList.contains("hidden")) await abrirIntegridade(true);
  }
}
async function abrirIntegridade(manter) {
  const pop = $("#integ-pop");
  if (!manter && !pop.classList.contains("hidden")) { pop.classList.add("hidden"); return; }
  closeMenus(); $("#counter-pop").classList.add("hidden");
  const d = await api("/api/integridade");
  const quando = (t) => t ? esc(t.slice(8, 10) + "/" + t.slice(5, 7) + " " + t.slice(11, 16)) : "—";
  pop.innerHTML = `<h4>Gmail × MarquesPro</h4>
    <p class="muted">A cada ${Math.round((d.intervalo_s || 60) / 60) || 1} min o programa busca o que chegou no Gmail. A cada 5 min ele <b>confere item por item</b> (inclusive spam) se tudo está aqui e traz o que faltar.</p>
    ${d.contas.map(c => `<div class="integ-conta ${c.nivel}"><div class="ic-top">${ic(NIVEL_INFO[c.nivel].icon, "sm")}<b>${esc(c.email)}</b></div>
      <div class="muted">${esc(c.mensagem)}</div>
      <div class="kv"><span>Última sincronização</span><b>${quando(c.ultima_sync)}</b></div>
      <div class="kv"><span>Última conferência completa</span><b>${quando(c.ultima_verificacao)}</b></div>
      <div class="kv"><span>No Gmail (últimos ${c.janela_dias || "—"} dias)</span><b>${c.gmail_n ?? "—"}</b></div>
      <div class="kv"><span>Aqui no MarquesPro</span><b>${c.aqui_n ?? "—"}</b></div>
      <div class="kv"><span>Recuperados pela conferência (total)</span><b>${c.recuperados_total}</b></div>
      ${c.erro ? `<div class="integ-erro">${esc(c.erro)}</div>` : ""}</div>`).join("") || `<p class="muted">Nenhuma conta conectada.</p>`}
    <div class="row"><button class="btn primary" data-ia="verificar">Verificar agora</button>${d.contas.some(c => c.acao === "reconhecer") ? `<button class="btn" data-ia="reconhecer">Entendi</button>` : ""}${d.contas.some(c => c.acao === "reconectar") ? `<button class="btn" data-ia="reconectar">Reconectar conta</button>` : ""}</div>
    <h4>Histórico</h4>
    ${d.eventos.length ? d.eventos.slice(0, 12).map(e => `<div class="ev ${e.nivel}"><span class="muted">${quando(e.ts)}</span> ${esc(e.detalhe || e.evento)}</div>`).join("") : `<p class="muted">Sem ocorrências registradas.</p>`}`;
  pop.classList.remove("hidden");
  $$("[data-ia]", pop).forEach(b => b.onclick = guard(() => acaoIntegridade(b.dataset.ia)));
}

function renderCounterPop() {
  const s = state.status; if (!s) return;
  const n = s.notificacoes;
  $("#counter-pop").innerHTML = `
    <h4>Notificações judiciais</h4>
    <div class="big"><b>${n.hoje}</b><span>recebidas hoje</span></div>
    <div class="kv"><span>Ainda não abertas no MarquesPro (todas as datas)</span><b>${n.pendentes}</b></div>
    ${n.por_tipo.map(t => `<div class="kv"><span>${esc(t.nome)}</span><b>${t.n}</b></div>`).join("")}
    <div class="row"><button class="btn primary" id="pop-ver-notif">Ver notificações</button></div>
    <h4>Atenção</h4>
    <div class="kv"><span>Novos hoje (fora da cadeia)</span><b>${s.novos_hoje || 0}</b></div>
    <div class="kv"><span>Clientes sem resposta</span><b>${s.pendencias ? s.pendencias.abertas : 0}</b></div>
    <div class="kv"><span>Tratativas em execução</span><b>${s.pendencias ? s.pendencias.em_execucao : 0}</b></div>
    <div class="row"><button class="btn" id="pop-ver-pend">Ver pendências</button></div>
    <h4>E-mails de hoje</h4>
    <div class="kv"><span>Recebidos na caixa de entrada</span><b>${s.recebidas_hoje}</b></div>
    <div class="kv"><span>Novos desde que o sistema abriu</span><b>${s.notificacoes_hoje}</b></div>
    <div class="kv"><span>Não lidos no MarquesPro</span><b>${s.nao_lidas_local}</b></div>
    ${s.hoje_por_etiqueta.length ? `<h4>Por marcador (hoje)</h4>` + s.hoje_por_etiqueta.map(l => `<div class="kv"><span>${esc(l.name)}</span><b>${l.n}</b></div>`).join("") : ""}
    ${s.novas.length ? `<h4>Últimos recebidos</h4>` + s.novas.map(x => `<div class="nt" data-acc="${esc(x.account)}" data-tid="${esc(x.thread_id)}"><b>${esc(x.from_name || "")}</b><br><span class="muted">${esc(x.subject || "")} · ${esc(x.created_at.slice(11, 16))}</span></div>`).join("") : ""}
    <h4>Sincronização</h4>${s.contas.map(c => `<div class="kv"><span class="muted">${esc(c.email)}</span><span class="muted">${c.last_error ? "Erro: " + esc(c.last_error.slice(0, 60)) : esc(c.last_sync || "—")}</span></div>`).join("")}`;
  $("#pop-ver-notif").onclick = guard(async () => {
    $("#counter-pop").classList.add("hidden"); state.folder = {id: "INBOX"}; state.grupo = "judiciais"; state.novos = false; state.search = ""; state.offset = 0; renderSidebar(); await loadThreads();
  });
  $("#pop-ver-pend").onclick = guard(async () => { $("#counter-pop").classList.add("hidden"); state.folder = {id: "PEND"}; state.search = ""; state.offset = 0; renderSidebar(); await loadThreads(); });
  $$("#counter-pop .nt").forEach(x => x.onclick = guard(() => { $("#counter-pop").classList.add("hidden"); return openThread(x.dataset.acc, x.dataset.tid); }));
}

// ─── Configurações ───────────────────────────────────────────────────────
const ruleForm = {labels: []};
function openSettings(tab) {
  $("#counter-pop").classList.add("hidden");
  $("#settings").classList.remove("hidden");
  selectTab(tab || "tab-general");
}
function selectTab(id) {
  $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === id));
  $$(".tab-pane").forEach(p => p.classList.toggle("hidden", p.id !== id));
  ({"tab-general": renderGeneral, "tab-accounts": renderAccounts, "tab-signatures": renderSignatures, "tab-rules": renderRules, "tab-grupos": renderGrupos})[id]();
}
function renderGeneral() {
  const v = state.settings.lida_no_gmail_conta_como_lida === "1" ? "1" : "0";
  $(`#leitura-${v}`).checked = true;
  $("#ocultar-anuncios").checked = state.settings.ocultar_anuncios !== "0";
  $("#ia-ler-imagens").checked = state.settings.ia_ler_imagens_auto !== "0";
  $("#prazo-interno-dias").value = state.settings.prazo_interno_dias || "";
  $("#palavras-destaque").value = state.settings.palavras_destaque || "";
}
function renderAccounts() {
  $("#acc-list").innerHTML = state.accounts.map(a => `<div class="card"><b>${esc(a.email)}</b>
    <div class="muted">Última sincronização: ${esc(a.last_sync || "—")}${a.last_error ? ` · <span style="color:var(--red)">${esc(a.last_error)}</span>` : ""}</div>
    <div class="row"><button class="btn danger" data-disc="${esc(a.email)}">Desconectar</button></div></div>`).join("") || `<p class="muted">Nenhuma conta conectada.</p>`;
  $$("[data-disc]").forEach(b => b.onclick = guard(async () => {
    if (!confirm(`Desconectar ${b.dataset.disc}? O cache local permanece; o Gmail não é alterado.`)) return;
    await api(`/api/accounts/${encodeURIComponent(b.dataset.disc)}/disconnect`, {method: "POST"});
    await loadAccounts(); renderAccounts();
  }));
}
function renderSignatures() {
  const box = $("#sig-list");
  box.innerHTML = state.sendAs.map((s, i) => `<div class="card">
    <b>${esc(s.display_name || "(sem nome)")}</b> &lt;${esc(s.email)}&gt; <span class="muted">· conta ${esc(s.account)}${s.is_default ? " · padrão" : ""}</span>
    <div class="muted" style="margin-top:8px">Assinatura no Gmail:</div>
    <div id="sigp-${i}"></div>
    <label class="radio"><input type="checkbox" data-use="${i}" ${s.use_local ? "checked" : ""}> <span>Usar assinatura local (HTML) em vez da do Gmail</span></label>
    <textarea data-loc="${i}" placeholder="Assinatura local (opcional)" aria-label="Assinatura local">${esc(s.local_signature || "")}</textarea>
    <div class="row"><button class="btn" data-save="${i}">Salvar</button><button class="btn" data-logo="${i}" title="Preenche a assinatura local com a logo do escritório">Modelo do escritório com logo</button></div></div>`).join("") || `<p class="muted">Nenhum remetente carregado. Clique em "Atualizar do Gmail".</p>`;
  state.sendAs.forEach((s, i) => {
    const fr = document.createElement("iframe");
    fr.setAttribute("sandbox", ""); fr.style.cssText = "width:100%;border:1px dashed #e0e0e0;border-radius:4px;height:110px";
    fr.srcdoc = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data: https:"><div style="font:14px Arial,sans-serif">` +
      (s.api_signature || "<i style='color:#888'>Nenhuma assinatura cadastrada no Gmail</i>") + "</div>";
    $(`#sigp-${i}`).appendChild(fr);
  });
  $$("[data-logo]").forEach(b => b.onclick = () => {
    const i = +b.dataset.logo, s = state.sendAs[i];
    $(`[data-loc="${i}"]`).value = `<table style="font-family:Arial,sans-serif;font-size:13px;color:#333;border-collapse:collapse"><tr><td style="padding-right:12px;vertical-align:middle"><img src="/static/logo-m-dourado.png" width="86" alt="Marques Advogados"></td><td style="border-left:2px solid #8C5818;padding-left:12px;vertical-align:middle"><b>${esc(s.display_name || "")}</b><br>Marques Advogados S/S<br>${esc(s.email)}</td></tr></table>`;
    $(`[data-use="${i}"]`).checked = true;
    toast("Modelo com logo preenchido. Edite o texto se precisar e clique em Salvar.");
  });
  $$("[data-save]").forEach(b => b.onclick = guard(async () => {
    const i = +b.dataset.save, s = state.sendAs[i];
    await api("/api/send-as/signature", {body: {account: s.account, email: s.email,
      local_signature: $(`[data-loc="${i}"]`).value, use_local: $(`[data-use="${i}"]`).checked}});
    await loadSendAs(); toast("Assinatura salva.");
  }));
}
async function renderRules() {
  $("#r-account").innerHTML = state.accounts.map(a => `<option>${esc(a.email)}</option>`).join("");
  if (state.account) $("#r-account").value = state.account;
  renderRuleChips();
  const rules = await api("/api/rules");
  $("#rule-list").innerHTML = rules.map(r => `<tr>
    <td>${esc(r.account)}</td><td>${r.direction === "enviado" ? "Enviado por" : "Recebido de"}</td><td>${esc(r.pattern)}</td>
    <td>${r.label_ids.map(id => labelById(r.account, id)).filter(Boolean).map(l => chipHtml(l)).join(" ")}</td>
    <td><input type="checkbox" data-active="${r.id}" ${r.active ? "checked" : ""} aria-label="Ativo"></td>
    <td><button class="btn" data-apply="${r.id}">Aplicar às existentes</button> <button class="btn danger" data-del="${r.id}">Excluir</button></td></tr>`).join("")
    || `<tr><td colspan="6" class="muted">Nenhum filtro.</td></tr>`;
  $$("[data-active]").forEach(c => c.onchange = guard(() => api(`/api/rules/${c.dataset.active}/ativo`, {body: {active: c.checked}})));
  $$("[data-apply]").forEach(b => b.onclick = guard(async () => {
    const r = await api(`/api/rules/${b.dataset.apply}/aplicar`, {method: "POST"});
    toast(`Marcadores aplicados em ${r.aplicadas} mensagem(ns).`);
  }));
  $$("[data-del]").forEach(b => b.onclick = guard(async () => {
    if (!confirm("Excluir este filtro? Os marcadores já aplicados permanecem no Gmail.")) return;
    await api(`/api/rules/${b.dataset.del}`, {method: "DELETE"}); renderRules();
  }));
}
function renderRuleChips() {
  const acc = $("#r-account").value;
  $("#r-chips").innerHTML = ruleForm.labels.map(id => labelById(acc, id)).filter(Boolean).map(l => chipHtml(l, true)).join("");
  $$("#r-chips .x").forEach(x => x.onclick = () => { ruleForm.labels = ruleForm.labels.filter(id => id !== x.parentElement.dataset.label); renderRuleChips(); });
}

// ─── Eventos ─────────────────────────────────────────────────────────────
function bind() {
  document.addEventListener("click", () => { closeMenus(); $("#counter-pop").classList.add("hidden"); $("#integ-pop").classList.add("hidden"); });
  document.addEventListener("click", () => {
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  }, {once: true});

  $("#btn-menu").onclick = () => { $("#sidebar").classList.toggle(innerWidth < 760 ? "open" : "collapsed"); };
  $("#brand").onclick = guard(async (e) => { e.preventDefault(); state.folder = {id: "INBOX"}; state.search = ""; $("#search-input").value = ""; state.offset = 0; renderSidebar(); await loadThreads(); });
  $("#btn-account").onclick = (e) => { e.stopPropagation(); const m = $("#account-menu"); const hid = m.classList.contains("hidden"); closeMenus(); if (hid) { renderAccountMenu(); m.classList.remove("hidden"); } };
  $("#account-menu").onclick = (e) => e.stopPropagation();
  $("#folders").onclick = guard(async (e) => {
    if (e.target.closest("li[data-mais]")) { state.maisPastas = !state.maisPastas; renderSidebar(); return; }
    const li = e.target.closest("li[data-folder]"); if (!li) return;
    state.folder = {id: li.dataset.folder}; state.grupo = ""; state.novos = false;
    state.search = ""; $("#search-input").value = ""; state.offset = 0;
    if (innerWidth < 760) $("#sidebar").classList.remove("open");
    renderSidebar(); await loadThreads();
  });
  $("#label-list").onclick = guard(async (e) => {
    const li = e.target.closest("li[data-label-name]"); if (!li) return;
    state.folder = {id: li.dataset.labelId, name: li.dataset.labelName}; state.grupo = ""; state.search = ""; $("#search-input").value = ""; state.offset = 0;
    if (innerWidth < 760) $("#sidebar").classList.remove("open");
    renderSidebar(); await loadThreads();
  });
  $("#btn-new-label").onclick = guard(async () => {
    const acc = state.account || (state.accounts[0] && state.accounts[0].email);
    if (!acc) return toast("Conecte uma conta primeiro", true);
    const name = prompt(`Novo marcador em ${acc} (use / para aninhar):`);
    if (!name) return;
    await api("/api/labels", {body: {account: acc, name}}); await loadLabels(); toast("Marcador criado no Gmail.");
  });
  $("#search-form").onsubmit = guard(async (e) => {
    e.preventDefault(); state.search = $("#search-input").value.trim(); state.searchGmail = $("#search-gmail").checked; state.offset = 0; await loadThreads();
  });
  $("#btn-clear-search").onclick = guard(async () => { $("#search-input").value = ""; state.search = ""; state.offset = 0; await loadThreads(); });
  $("#only-unread").onchange = guard(async () => { state.offset = 0; await loadThreads(); });
  $("#btn-refresh").onclick = guard(loadThreads);
  $("#btn-prev").onclick = guard(async () => { state.offset = Math.max(0, state.offset - PAGE); await loadThreads(); });
  $("#btn-next").onclick = guard(async () => { state.offset += PAGE; await loadThreads(); });
  $("#btn-sync").onclick = guard(async () => {
    toast("Sincronizando…");
    const r = await api("/api/sync", {method: "POST"});
    r.filter(x => x.status === "erro").forEach(x => toast(`${x.account}: ${x.erro}`, true));
    if (r.length && r.every(x => x.status === "ok")) toast("Sincronizado com o Gmail.");
    await loadLabels(); await refreshStatus(); await loadThreads();
  });
  const togglePop = (e) => { e.stopPropagation(); closeMenus(); const p = $("#counter-pop"); p.classList.toggle("hidden"); renderCounterPop(); };
  $("#counter").onclick = togglePop; $("#counter-notif").onclick = togglePop;
  $("#counter-pop").onclick = (e) => e.stopPropagation();
  $("#btn-integ").onclick = guard(async (e) => { e.stopPropagation(); await abrirIntegridade(); });
  $("#integ-pop").onclick = (e) => e.stopPropagation();

  // Lista
  $("#thread-list").onclick = guard(async (e) => {
    const row = e.target.closest(".row-t"); if (!row) return;
    const i = +row.dataset.i, t = state.threads[i];
    if (e.target.classList.contains("sel")) {
      e.target.checked ? state.selected.add(i) : state.selected.delete(i);
      row.classList.toggle("selected", e.target.checked); renderPager(); return;
    }
    if (e.target.closest(".cell")) return;
    if (e.target.closest(".star")) {
      const on = t.label_ids.includes("STARRED");
      await api("/api/threads/labels", {body: {account: t.account, thread_ids: [t.thread_id], [on ? "remove" : "add"]: ["STARRED"]}});
      t.label_ids = on ? t.label_ids.filter(x => x !== "STARRED") : [...t.label_ids, "STARRED"]; renderThreads(); return;
    }
    if (e.target.closest(".imp")) {
      const on = t.important;
      await api("/api/threads/labels", {body: {account: t.account, thread_ids: [t.thread_id], [on ? "remove" : "add"]: ["IMPORTANT"]}});
      t.important = !on; renderThreads(); return;
    }
    if (e.target.closest("[data-toggle-read]")) {
      await api(`/api/threads/${encodeURIComponent(t.account)}/${t.thread_id}/${t.read_local ? "nao-lida" : "lida"}`, {method: "POST"});
      t.read_local = !t.read_local; renderThreads(); refreshStatus(); return;
    }
    await openThread(t.account, t.thread_id);
  });
  $("#select-all").onchange = (e) => { state.selected = new Set(e.target.checked ? state.threads.map((_, i) => i) : []); renderThreads(); };
  $("#btn-bulk-labels").onclick = (e) => {
    e.stopPropagation();
    const sel = [...state.selected].map(i => state.threads[i]);
    const accs = [...new Set(sel.map(t => t.account))];
    if (accs.length > 1) return toast("Selecione conversas de uma única conta", true);
    const common = sel.map(t => t.label_ids).reduce((a, b) => a.filter(x => b.includes(x)));
    labelMenu($("#bulk-label-menu"), accs[0], common, async (add, remove) => {
      await api("/api/threads/labels", {body: {account: accs[0], thread_ids: sel.map(t => t.thread_id), add, remove}});
      toast("Marcadores aplicados no Gmail."); await loadThreads();
    });
  };
  $("#btn-bulk-unread").onclick = guard(async () => {
    for (const i of state.selected) { const t = state.threads[i];
      await api(`/api/threads/${encodeURIComponent(t.account)}/${t.thread_id}/nao-lida`, {method: "POST"}); }
    await loadThreads(); await refreshStatus();
  });

  // Nova mensagem
  $("#btn-compose").onclick = () => openCompose({mode: "novo"});
  const closeCompose = () => $("#compose").classList.add("hidden");
  $("#compose-close").onclick = (e) => { e.stopPropagation(); if (confirm("Fechar e descartar esta mensagem?")) closeCompose(); };
  $("#c-discard").onclick = () => { if (confirm("Descartar esta mensagem?")) closeCompose(); };
  $("#compose-min").onclick = (e) => { e.stopPropagation(); $("#compose").classList.toggle("min"); $("#compose").classList.remove("max"); };
  $("#compose-max").onclick = (e) => { e.stopPropagation(); $("#compose").classList.toggle("max"); $("#compose").classList.remove("min"); };
  $("#compose-head").onclick = () => $("#compose").classList.remove("min");
  $("#c-subject").addEventListener("input", (e) => { $("#compose-title").textContent = e.target.value.startsWith("/") ? "Nova mensagem" : (e.target.value || "Nova mensagem"); });
  $("#c-from").onchange = applySignature;
  $("#c-show-cc").onclick = (e) => { e.preventDefault(); $("#c-cc-row").classList.remove("hidden"); $("#c-bcc-row").classList.remove("hidden"); };
  $("#c-attach").onchange = (e) => { compose.files.push(...e.target.files); e.target.value = ""; renderComposeFiles(); };
  $("#c-send").onclick = sendCompose;
  $("#c-format").onclick = () => $("#editor-tools").classList.toggle("hidden");
  $$("#editor-tools button").forEach(b => b.onmousedown = (e) => { e.preventDefault(); document.execCommand(b.dataset.cmd); });
  $("#c-link").onmousedown = (e) => e.preventDefault();
  $("#c-link").onclick = () => {
    const u = prompt("Endereço do link (https://...):");
    if (u && /^(https?:|mailto:)/i.test(u)) { $("#c-editor").focus(); document.execCommand("createLink", false, u); }
  };
  $("#c-add-label").onclick = (e) => {
    e.preventDefault(); e.stopPropagation();
    labelMenu($("#c-label-menu"), currentFrom().account, compose.labels, (add, remove, all) => { compose.labels = all; renderComposeLabels(); }, {applyText: "OK"});
  };
  ["#c-to", "#c-cc", "#c-bcc"].forEach(s => setupAutocomplete($(s)));

  // Grupos de destinatários
  $("#c-grupos").onclick = guard(async (e) => { e.preventDefault(); e.stopPropagation(); await menuGrupos(); });
  $("#g-add-empresa").onclick = guard(async () => {
    await api("/api/grupos", {body: {nome: $("#g-empresa").value, observacao: $("#g-obs").value}});
    $("#g-empresa").value = ""; $("#g-obs").value = ""; await renderGrupos(); toast("Empresa cadastrada.");
  });
  $("#g-lista").onclick = guard(async (e) => {
    const t = e.target.closest("button"); if (!t) return;
    if (t.dataset.delEmp) { if (!confirm("Excluir a empresa e todos os seus subgrupos?")) return; await api(`/api/grupos/${t.dataset.delEmp}`, {method: "DELETE"}); await renderGrupos(); }
    else if (t.dataset.delSg) { if (!confirm("Excluir este subgrupo?")) return; await api(`/api/subgrupos/${t.dataset.delSg}`, {method: "DELETE"}); await renderGrupos(); }
    else if (t.dataset.editSg) {
      const sg = JSON.parse(t.dataset.editSg), f = t.closest(".card").querySelector(".g-form");
      ["nome", "para", "cc", "cco", "id"].forEach(k => { f.querySelector(`[data-f=${k}]`).value = sg[k] || ""; });
      f.querySelector("[data-f=nome]").focus();
    } else if (t.dataset.saveSg) {
      const f = t.closest(".g-form"), v = (k) => f.querySelector(`[data-f=${k}]`).value;
      await api(`/api/grupos/${t.dataset.saveSg}/subgrupos`, {body: {id: v("id") || null, nome: v("nome"), para: v("para"), cc: v("cc"), cco: v("cco")}});
      await renderGrupos(); toast("Subgrupo salvo.");
    }
  });

  // Confirmação dos dados lidos do documento e arrastar arquivo para a janela de escrita
  $("#mp-confirmo").onchange = (e) => { $("#mp-inserir").disabled = !e.target.checked; };
  const comp = $("#compose");
  ["dragenter", "dragover"].forEach(ev => comp.addEventListener(ev, (e) => { if (e.dataTransfer && [...e.dataTransfer.types].includes("Files")) { e.preventDefault(); comp.classList.add("drop-over"); } }));
  ["dragleave", "drop"].forEach(ev => comp.addEventListener(ev, () => comp.classList.remove("drop-over")));
  comp.addEventListener("drop", (e) => {
    if (!e.dataTransfer || !e.dataTransfer.files.length || e.target.closest("#mp-drop")) return;
    e.preventDefault(); adicionarArquivosIA(e.dataTransfer.files);
    abrirPainel("ia", "").then(() => executarIA());
  });

  // Modelos e IA
  $("#c-modelos").onclick = (e) => { e.stopPropagation(); abrirPainel("modelo", ""); };
  $("#c-ia").onclick = (e) => { e.stopPropagation(); abrirPainel("ia", ""); };
  $("#mp-close").onclick = $("#mp-cancelar").onclick = fecharPainel;
  $$("[data-mtab]").forEach(b => b.onclick = () => trocarAba(b.dataset.mtab));
  $("#mp-modelo").onchange = () => { if (MOD.aba === "modelo") renderFormModelo(); };
  $("#mp-inserir").onclick = inserirModelo;
  $("#mp-drop").onclick = () => $("#mp-arquivos").click();
  $("#mp-arquivos").onchange = (e) => { adicionarArquivosIA(e.target.files); e.target.value = ""; };
  ["dragover", "dragenter"].forEach(ev => $("#mp-drop").addEventListener(ev, (e) => { e.preventDefault(); $("#mp-drop").classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => $("#mp-drop").addEventListener(ev, (e) => { e.preventDefault(); $("#mp-drop").classList.remove("over"); }));
  $("#mp-drop").addEventListener("drop", (e) => adicionarArquivosIA(e.dataTransfer.files));
  $("#mp-ia-run").onclick = guard(executarIA);
  $("#mp-key-save").onclick = guard(async () => { await api("/api/ia/config", {body: {api_key: $("#mp-key").value}}); $("#mp-key").value = ""; const rodar = MOD.aguardaChave; await renderIA(); toast("Chave da IA salva neste computador."); if (rodar && (MOD.arquivos.length || compose.ref || $("#mp-instrucoes").value.trim())) { MOD.semIA = false; executarIA(); } });
  $("#mp-key-remover").onclick = guard(async () => { if (!confirm("Remover a chave da IA deste computador?")) return; await api("/api/ia/config", {body: {api_key: ""}}); await renderIA(); });
  // "/" no corpo do e-mail e no assunto abre o menu de modelos
  $("#c-editor").addEventListener("input", () => { const q = gatilhoSlashNoEditor(); if (q === null) $("#slash-menu").classList.add("hidden"); else mostrarSlash(q); });
  $("#c-editor").addEventListener("keydown", teclaSlash);
  $("#c-editor").addEventListener("blur", () => setTimeout(() => $("#slash-menu").classList.add("hidden"), 150));
  $("#c-subject").addEventListener("input", (e) => { if (e.target.value.startsWith("/")) mostrarSlash(e.target.value.slice(1)); else $("#slash-menu").classList.add("hidden"); });
  $("#c-subject").addEventListener("keydown", teclaSlash);

  // Configurações
  $("#btn-settings").onclick = (e) => { e.stopPropagation(); openSettings(); };
  $("#settings").onclick = (e) => { if (e.target.id === "settings") $("#settings-close").click(); };
  $(".modal").onclick = (e) => { e.stopPropagation(); if (!e.target.closest(".dropdown")) closeMenus(); };
  $("#settings-close").onclick = guard(async () => { $("#settings").classList.add("hidden"); await loadAccounts(); await loadLabels(); await loadSendAs(); });
  $$(".tab").forEach(t => t.onclick = () => selectTab(t.dataset.tab));
  $$('input[name="leitura"]').forEach(r => r.onchange = guard(async () => {
    state.settings = await api("/api/settings", {body: {lida_no_gmail_conta_como_lida: r.value === "1"}});
    toast(r.value === "1" ? "O MarquesPro passa a acompanhar as leituras feitas no Gmail." : "Leitura do MarquesPro independente do Gmail.");
    await refreshStatus(); await loadThreads();
  }));
  $("#ocultar-anuncios").onchange = guard(async (e) => {
    state.settings = await api("/api/settings", {body: {ocultar_anuncios: e.target.checked}});
    toast(e.target.checked ? "Anúncios e promoções saem da caixa de entrada." : "Anúncios voltam a aparecer na caixa de entrada.");
    await refreshStatus(); await loadThreads();
  });
  $("#ia-ler-imagens").onchange = guard(async (e) => { state.settings = await api("/api/settings", {body: {ia_ler_imagens_auto: e.target.checked}}); });
  $("#palavras-destaque").onchange = guard(async (e) => {
    state.settings = await api("/api/settings", {body: {palavras_destaque: e.target.value}});
    toast("Palavras em destaque atualizadas."); await loadThreads();
  });
  $("#prazo-interno-dias").onchange = guard(async (e) => {
    state.settings = await api("/api/settings", {body: {prazo_interno_dias: e.target.value}});
    toast(e.target.value ? `Prazo interno: ${e.target.value} dia(s) útil(eis) antes da data.` : "Prazo interno será preenchido manualmente.");
  });
  $("#acc-connect").onclick = guard(async () => {
    toast("Abra a janela do Google para autorizar a conta…");
    const r = await api("/api/accounts/connect", {body: {email: $("#acc-hint").value.trim()}});
    toast(`Conta ${r.email} conectada.`);
    await loadAccounts(); await loadLabels(); await loadSendAs(); renderAccounts(); await refreshStatus(); await loadThreads();
  });
  $("#sig-refresh").onclick = guard(async () => { state.sendAs = await api("/api/send-as/refresh", {method: "POST"}); renderSignatures(); toast("Remetentes e assinaturas atualizados."); });
  $("#r-account").onchange = () => { ruleForm.labels = []; renderRuleChips(); };
  $("#r-labels-btn").onclick = (e) => {
    e.stopPropagation();
    labelMenu($("#r-label-menu"), $("#r-account").value, ruleForm.labels, (a, r, all) => { ruleForm.labels = all; renderRuleChips(); }, {applyText: "OK"});
  };
  $("#r-save").onclick = guard(async () => {
    const r = await api("/api/rules", {body: {account: $("#r-account").value, direction: $("#r-direction").value,
      pattern: $("#r-pattern").value, label_ids: ruleForm.labels, aplicar_existentes: $("#r-existing").checked}});
    toast(`Filtro criado${r.aplicadas ? ` e aplicado em ${r.aplicadas} mensagem(ns)` : ""}.`);
    $("#r-pattern").value = ""; ruleForm.labels = []; renderRules();
  });
}

// ─── Início ──────────────────────────────────────────────────────────────
(async function init() {
  bind();
  await guard(async () => {
    await loadAccounts();
    await Promise.all([loadLabels(), loadSendAs(), loadSettings()]);
    await refreshStatus();
    await loadThreads();
  })();
  setInterval(guard(refreshStatus), 20000);
})();
})();
