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
  {id: "NOTIF", name: "Notificações judiciais", icon: "gavel"},
  {id: "STARRED", name: "Com estrela", icon: "star"},
  {id: "IMPORTANT", name: "Importante", icon: "label_important"},
  {id: "SENT", name: "Enviados", icon: "send"},
  {id: "ALL", name: "Todos os e-mails", icon: "mail"},
];
const TABS = [
  {cat: "principal", name: "Principal", icon: "inbox"},
  {cat: "promocoes", name: "Promoções", icon: "sell"},
  {cat: "social", name: "Social", icon: "group"},
  {cat: "atualizacoes", name: "Atualizações", icon: "info"},
];

const state = {
  accounts: [], account: "", folder: {id: "INBOX", cat: "principal"}, offset: 0, total: 0,
  labels: [], threads: [], selected: new Set(), sendAs: [], settings: {},
  lastNotif: null, notifHoje: null, status: null, search: "", searchGmail: false, current: null,
};

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
  const st = l.bg_color ? `style="background:${esc(l.bg_color)};color:${esc(l.text_color || "#000")}"` : "";
  return `<span class="chip" ${st} data-label="${esc(l.id)}">${esc(l.name)}${removable ? `<span class="ms x" title="Remover marcador">close</span>` : ""}</span>`;
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
    if (state.folder.name) state.folder = {id: "INBOX", cat: "principal"};
    renderAccountButton(); renderSidebar(); await refreshStatus(); await loadThreads();
  }));
  $("[data-add]", m).onclick = () => { m.classList.add("hidden"); openSettings("tab-accounts"); };
}

function renderSidebar() {
  const st = state.status || {};
  const counts = {INBOX: st.nao_lidas_local || 0, NOTIF: st.notificacoes ? st.notificacoes.pendentes : 0};
  const isFolder = (id) => state.folder.id === id && !state.folder.name;
  $("#folders").innerHTML = FOLDERS.map(f => `
    <li data-folder="${f.id}" class="${isFolder(f.id) ? "active" : ""} ${counts[f.id] ? "has-unread" : ""} ${f.id === "NOTIF" ? "notif" : ""}"
      title="${f.id === "NOTIF" ? "Intimações, citações, publicações e demais avisos de tribunais (contador: não abertas no MarquesPro)" : esc(f.name)}">
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
  const show = state.folder.id === "INBOX" && !state.folder.name && !state.search;
  const box = $("#tabs-inbox");
  box.classList.toggle("hidden", !show);
  if (!show) return;
  const un = (state.status && state.status.nao_lidas_categoria) || {};
  box.innerHTML = TABS.map(t => `<button data-cat="${t.cat}" class="${state.folder.cat === t.cat ? "on" : ""}">
    ${ic(t.icon)}<span class="tname">${t.name}</span>${t.cat !== "principal" && un[t.cat] ? `<span class="new">${un[t.cat]} nova${un[t.cat] > 1 ? "s" : ""}</span>` : ""}</button>`).join("");
  $$("button", box).forEach(b => b.onclick = guard(async () => { state.folder = {id: "INBOX", cat: b.dataset.cat}; state.offset = 0; await loadThreads(); }));
}

async function loadThreads() {
  const list = $("#thread-list");
  showList();
  renderTabs();
  let data, total;
  if (state.search && state.searchGmail) {
    if (!state.account) { list.innerHTML = `<div class="empty">${ic("person_search")}Escolha uma conta (no círculo do canto superior direito) para buscar no Gmail.</div>`; return; }
    data = await api(`/api/search?${qs({account: state.account, q: state.search})}`);
    total = data.length;
  } else {
    const p = {account: state.account, q: state.search, nao_lidas: $("#only-unread").checked ? 1 : "", limit: PAGE, offset: state.offset};
    if (state.folder.name) { if (state.account) p.label = state.folder.id; else p.label_nome = state.folder.name; }
    else if (state.folder.id === "NOTIF") { p.label = "ALL"; p.tipo = "TRIBUNAL"; }
    else { p.label = state.folder.id; if (state.folder.id === "INBOX" && !state.search) p.categoria = state.folder.cat || "principal"; }
    const r = await apiRaw(`/api/threads?${qs(p)}`);
    data = r.data; total = +(r.headers.get("X-Total-Count") || data.length);
  }
  state.threads = data; state.total = total;
  state.selected.clear();
  $("#select-all").checked = false;
  renderThreads();
}

function renderPager() {
  const n = state.threads.length;
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
      state.folder.id === "NOTIF" ? "Nenhuma notificação judicial por aqui." : "Nenhuma conversa nesta pasta.";
    list.innerHTML = `<div class="empty">${ic(state.folder.id === "NOTIF" ? "gavel" : "inbox")}${msg}</div>`; return;
  }
  const multi = !state.account && state.accounts.length > 1;
  list.innerHTML = state.threads.map((t, i) => {
    const chips = t.label_ids.map(id => labelById(t.account, id)).filter(l => l && l.type === "user")
      .filter(l => !(state.folder.name && l.name === state.folder.name)).map(l => chipHtml(l)).join("");
    const atts = (t.anexos || []).map(n => `<span class="att-chip">${ic("description", "sm")}${esc(n)}</span>`).join("");
    const starred = t.label_ids.includes("STARRED");
    return `<div class="row-t ${t.read_local ? "" : "unread"} ${state.selected.has(i) ? "selected" : ""}" data-i="${i}">
      <div class="lead">
        <span class="cell"><input type="checkbox" class="sel" ${state.selected.has(i) ? "checked" : ""} aria-label="Selecionar"></span>
        <button class="star ${starred ? "on" : ""}" title="${starred ? "Com estrela" : "Sem estrela"}">${ic("star", starred ? "fill" : "")}</button>
        <button class="imp ${t.important ? "on" : ""}" title="${t.important ? "Importante" : "Marcar como importante"}">${ic("label_important", t.important ? "fill" : "")}</button>
      </div>
      <div class="from">${esc(t.senders)}${t.count > 1 ? `<span class="cnt">${t.count}</span>` : ""}</div>
      <div class="mid">
        <div class="line1">${t.notificacao ? `<span class="chip notif" title="Notificação judicial">${ic("gavel", "sm")}${esc(t.notificacao)}</span>` : ""}${chips}
          <span class="subj"><span class="subj-t">${esc(t.subject)}</span><span class="snip"> - ${esc(t.snippet)}</span></span></div>
        ${atts ? `<div class="att-chips">${atts}</div>` : ""}
      </div>
      ${t.unread_gmail ? `<span class="gm" title="Ainda não lida no Gmail (status preservado para a controladoria)">${ic("mark_email_unread", "sm")}<span class="t">&nbsp;não lida no Gmail</span></span>` : ""}
      ${multi ? `<span class="acc">${esc(t.account.split("@")[0])}</span>` : ""}
      ${t.has_attachments && !atts ? `<span class="ms sm" style="color:#5e5e5e;margin-left:8px" title="Possui anexo">attach_file</span>` : ""}
      <div class="date">${fmtDate(t.last_date)}</div>
      <div class="hover-acts">
        <button class="icon-btn small" data-toggle-read title="${t.read_local ? "Marcar como não lida (somente no MarquesPro)" : "Marcar como lida (somente no MarquesPro)"}">${ic(t.read_local ? "mark_email_unread" : "drafts")}</button>
      </div></div>`;
  }).join("");
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

function renderThreadView() {
  const d = state.current, v = $("#thread-view"), msgs = d.messages;
  const notif = msgs.find(m => m.tipo === "TRIBUNAL");
  const labelChips = d.label_ids.map(id => labelById(d.account, id)).filter(l => l && l.type === "user").map(l => chipHtml(l, true)).join("");
  const lastUnreadIdx = msgs.length - 1;
  v.innerHTML = `
    <div class="tv-tools">
      <button class="icon-btn" id="tv-back" title="Voltar para a lista">${ic("arrow_back")}</button>
      <button class="icon-btn" id="tv-unread" title="Marcar como não lida (somente no MarquesPro)">${ic("mark_email_unread")}</button>
      <div class="dropdown"><button class="icon-btn" id="tv-labels-btn" title="Marcadores">${ic("label")}</button><div class="menu hidden" id="tv-label-menu"></div></div>
      <span class="local-note" title="Abrir aqui não marca a mensagem como lida no Gmail">${ic("visibility", "sm")} Leitura somente no MarquesPro · ${esc(d.account)}</span>
    </div>
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
  Object.assign(compose, {mode: ctx.mode || "novo", account: ctx.account || "", ref: ctx.ref || null, files: [],
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
  if (sig) sig.innerHTML = info && info.signature ? `<br>-- <br>${sanitizeHtml(info.signature)}` : "";
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
function setupAutocomplete(input) {
  const box = $(".ac", input.parentElement);
  let timer, items = [], on = -1;
  const pick = (c) => {
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
      box.innerHTML = items.map((c, i) => `<div data-i="${i}"><span class="av" style="background:${colorFor(c.email)}">${initial(c.name || c.email)}</span>
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

// ─── Contadores e notificações ───────────────────────────────────────────
async function refreshStatus() {
  const s = await api(`/api/status?${qs({account: state.account, desde: state.lastNotif ?? 0})}`);
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
  document.title = (s.nao_lidas_local ? `Caixa de entrada (${s.nao_lidas_local})` : "Caixa de entrada") + " - MarquesPro Mail";
  renderSidebar();
  if (!$("#tabs-inbox").classList.contains("hidden")) renderTabs();
  if (!$("#counter-pop").classList.contains("hidden")) renderCounterPop();
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
    <h4>E-mails de hoje</h4>
    <div class="kv"><span>Recebidos na caixa de entrada</span><b>${s.recebidas_hoje}</b></div>
    <div class="kv"><span>Novos desde que o sistema abriu</span><b>${s.notificacoes_hoje}</b></div>
    <div class="kv"><span>Não lidos no MarquesPro</span><b>${s.nao_lidas_local}</b></div>
    ${s.hoje_por_etiqueta.length ? `<h4>Por marcador (hoje)</h4>` + s.hoje_por_etiqueta.map(l => `<div class="kv"><span>${esc(l.name)}</span><b>${l.n}</b></div>`).join("") : ""}
    ${s.novas.length ? `<h4>Últimos recebidos</h4>` + s.novas.map(x => `<div class="nt" data-acc="${esc(x.account)}" data-tid="${esc(x.thread_id)}"><b>${esc(x.from_name || "")}</b><br><span class="muted">${esc(x.subject || "")} · ${esc(x.created_at.slice(11, 16))}</span></div>`).join("") : ""}
    <h4>Sincronização</h4>${s.contas.map(c => `<div class="kv"><span class="muted">${esc(c.email)}</span><span class="muted">${c.last_error ? "Erro: " + esc(c.last_error.slice(0, 60)) : esc(c.last_sync || "—")}</span></div>`).join("")}`;
  $("#pop-ver-notif").onclick = guard(async () => {
    $("#counter-pop").classList.add("hidden"); state.folder = {id: "NOTIF"}; state.search = ""; state.offset = 0; renderSidebar(); await loadThreads();
  });
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
  ({"tab-general": renderGeneral, "tab-accounts": renderAccounts, "tab-signatures": renderSignatures, "tab-rules": renderRules})[id]();
}
function renderGeneral() {
  const v = state.settings.lida_no_gmail_conta_como_lida === "1" ? "1" : "0";
  $(`#leitura-${v}`).checked = true;
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
    <div class="row"><button class="btn" data-save="${i}">Salvar</button></div></div>`).join("") || `<p class="muted">Nenhum remetente carregado. Clique em "Atualizar do Gmail".</p>`;
  state.sendAs.forEach((s, i) => {
    const fr = document.createElement("iframe");
    fr.setAttribute("sandbox", ""); fr.style.cssText = "width:100%;border:1px dashed #e0e0e0;border-radius:4px;height:110px";
    fr.srcdoc = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data: https:"><div style="font:14px Arial,sans-serif">` +
      (s.api_signature || "<i style='color:#888'>Nenhuma assinatura cadastrada no Gmail</i>") + "</div>";
    $(`#sigp-${i}`).appendChild(fr);
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
  document.addEventListener("click", () => { closeMenus(); $("#counter-pop").classList.add("hidden"); });
  document.addEventListener("click", () => {
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  }, {once: true});

  $("#btn-menu").onclick = () => { $("#sidebar").classList.toggle(innerWidth < 760 ? "open" : "collapsed"); };
  $("#brand").onclick = guard(async (e) => { e.preventDefault(); state.folder = {id: "INBOX", cat: "principal"}; state.search = ""; $("#search-input").value = ""; state.offset = 0; renderSidebar(); await loadThreads(); });
  $("#btn-account").onclick = (e) => { e.stopPropagation(); const m = $("#account-menu"); const hid = m.classList.contains("hidden"); closeMenus(); if (hid) { renderAccountMenu(); m.classList.remove("hidden"); } };
  $("#account-menu").onclick = (e) => e.stopPropagation();
  $("#folders").onclick = guard(async (e) => {
    const li = e.target.closest("li[data-folder]"); if (!li) return;
    state.folder = {id: li.dataset.folder, cat: li.dataset.folder === "INBOX" ? "principal" : undefined};
    state.search = ""; $("#search-input").value = ""; state.offset = 0;
    if (innerWidth < 760) $("#sidebar").classList.remove("open");
    renderSidebar(); await loadThreads();
  });
  $("#label-list").onclick = guard(async (e) => {
    const li = e.target.closest("li[data-label-name]"); if (!li) return;
    state.folder = {id: li.dataset.labelId, name: li.dataset.labelName}; state.search = ""; $("#search-input").value = ""; state.offset = 0;
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
    await loadLabels(); await refreshStatus(); await loadThreads();
  });
  const togglePop = (e) => { e.stopPropagation(); closeMenus(); const p = $("#counter-pop"); p.classList.toggle("hidden"); renderCounterPop(); };
  $("#counter").onclick = togglePop; $("#counter-notif").onclick = togglePop;
  $("#counter-pop").onclick = (e) => e.stopPropagation();

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
  $("#c-subject").oninput = (e) => { $("#compose-title").textContent = e.target.value || "Nova mensagem"; };
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
