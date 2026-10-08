/* MarquesPro Mail — interface local espelhada do Gmail.
 * Abrir mensagens aqui NÃO altera o status de leitura no Gmail.
 */
(() => {
"use strict";

const TOKEN = window.GESTOR_TOKEN;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

const SYSTEM_FOLDERS = [
  {id: "INBOX", name: "Caixa de entrada", icon: "📥"},
  {id: "STARRED", name: "Com estrela", icon: "⭐"},
  {id: "IMPORTANT", name: "Importante", icon: "🏷️"},
  {id: "SENT", name: "Enviados", icon: "📤"},
  {id: "ALL", name: "Todos os e-mails", icon: "🗂️"},
];

const state = {
  accounts: [], account: "", folder: {id: "INBOX"}, labels: [], threads: [],
  selected: new Set(), sendAs: [], lastNotif: null, status: null, search: "", searchGmail: false,
  current: null,
};

// ─── API ─────────────────────────────────────────────────────────────────
async function api(path, opts = {}) {
  const headers = Object.assign({"X-Gestor-Token": TOKEN}, opts.headers || {});
  let body = opts.body;
  if (body && !(body instanceof FormData)) { headers["Content-Type"] = "application/json"; body = JSON.stringify(body); }
  const r = await fetch(path, {method: opts.method || (body ? "POST" : "GET"), headers, body});
  let data = null;
  try { data = await r.json(); } catch (_) {}
  if (!r.ok) throw new Error((data && data.erro) || `Erro ${r.status}`);
  return data;
}
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
function fmtDate(ms, long) {
  const d = new Date(ms), now = new Date();
  if (long) return d.toLocaleString("pt-BR", {dateStyle: "medium", timeStyle: "short"});
  if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit"});
  if (d.getFullYear() === now.getFullYear()) return d.toLocaleDateString("pt-BR", {day: "numeric", month: "short"});
  return d.toLocaleDateString("pt-BR");
}
function colorFor(s) {
  let h = 0; for (const c of s || "") h = (h * 31 + c.charCodeAt(0)) | 0;
  return `hsl(${Math.abs(h) % 360} 45% 45%)`;
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
function labelsOf(acc) { return state.labels.filter(l => l.account === acc); }
function labelById(acc, id) { return state.labels.find(l => l.account === acc && l.id === id); }
function userLabels(acc) { return labelsOf(acc).filter(l => l.type === "user"); }
function chipHtml(l, removable) {
  const st = l.bg_color ? `style="background:${esc(l.bg_color)};color:${esc(l.text_color || "#000")}"` : "";
  return `<span class="chip" ${st} data-label="${esc(l.id)}">${esc(l.name)}${removable ? '<span class="x" title="Remover">✕</span>' : ""}</span>`;
}

// ─── Carregamento ────────────────────────────────────────────────────────
async function loadAccounts() {
  state.accounts = await api("/api/accounts");
  const sel = $("#account-select");
  sel.innerHTML = `<option value="">Todas as contas</option>` +
    state.accounts.map(a => `<option value="${esc(a.email)}">${esc(a.email)}</option>`).join("");
  sel.value = state.account;
  if (!state.accounts.length) openSettings("tab-accounts");
}
async function loadLabels() {
  state.labels = await api("/api/labels");
  renderSidebar();
}
async function loadSendAs() { state.sendAs = await api("/api/send-as"); }

function renderSidebar() {
  const unread = state.status ? state.status.nao_lidas_local : 0;
  $("#folders").innerHTML = SYSTEM_FOLDERS.map(f => `
    <li data-folder="${f.id}" class="${state.folder.id === f.id && !state.folder.name ? "active" : ""}">
      <span>${f.icon}</span><span class="name">${f.name}</span>
      ${f.id === "INBOX" && unread ? `<span class="count">${unread}</span>` : ""}</li>`).join("");
  // Etiquetas de usuário (mescladas por nome quando "Todas as contas")
  const src = state.account ? userLabels(state.account) : state.labels.filter(l => l.type === "user");
  const byName = new Map();
  src.forEach(l => { if (!byName.has(l.name)) byName.set(l.name, l); });
  const names = [...byName.keys()].sort((a, b) => a.localeCompare(b, "pt-BR"));
  $("#label-list").innerHTML = names.map(n => {
    // Aninha apenas quando a etiqueta-mãe existe (como no Gmail)
    const parts = n.split("/"), parent = parts.slice(0, -1).join("/");
    const nested = parts.length > 1 && byName.has(parent);
    const l = byName.get(n), depth = nested ? parts.length - 1 : 0, short = nested ? parts[parts.length - 1] : n;
    return `<li data-label-name="${esc(n)}" data-label-id="${esc(l.id)}" style="padding-left:${24 + depth * 16}px"
      class="${state.folder.name === n ? "active" : ""}" title="${esc(n)}">
      <span class="dot" style="background:${esc(l.bg_color || "#c4c7c5")}"></span><span class="name">${esc(short)}</span></li>`;
  }).join("") || `<li class="muted"><span class="name">Nenhuma etiqueta</span></li>`;
}

async function loadThreads() {
  const list = $("#thread-list");
  showList();
  list.innerHTML = `<div class="empty">Carregando…</div>`;
  let data;
  if (state.search && state.searchGmail) {
    if (!state.account) { list.innerHTML = `<div class="empty">Selecione uma conta para buscar no Gmail.</div>`; return; }
    data = await api(`/api/search?${qs({account: state.account, q: state.search})}`);
  } else {
    const p = {account: state.account, q: state.search, nao_lidas: $("#only-unread").checked ? 1 : ""};
    if (state.folder.name) { if (state.account) p.label = state.folder.id; else p.label_nome = state.folder.name; }
    else p.label = state.folder.id;
    data = await api(`/api/threads?${qs(p)}`);
  }
  state.threads = data;
  state.selected.clear();
  $("#select-all").checked = false;
  renderThreads();
}

function renderThreads() {
  const list = $("#thread-list");
  if (!state.threads.length) { list.innerHTML = `<div class="empty">Nenhuma conversa aqui.</div>`; return; }
  const multi = !state.account && state.accounts.length > 1;
  list.innerHTML = state.threads.map((t, i) => {
    const chips = t.label_ids.map(id => labelById(t.account, id)).filter(l => l && l.type === "user")
      .filter(l => !(state.folder.name && l.name === state.folder.name)).map(l => chipHtml(l)).join("");
    return `<div class="row-t ${t.read_local ? "" : "unread"} ${state.selected.has(i) ? "selected" : ""}" data-i="${i}">
      <input type="checkbox" class="sel" ${state.selected.has(i) ? "checked" : ""}>
      <button class="star ${t.label_ids.includes("STARRED") ? "on" : ""}" title="Estrela">★</button>
      <div class="from">${esc(t.senders)}${t.count > 1 ? `<span class="cnt">${t.count}</span>` : ""}</div>
      ${multi ? `<span class="acc">${esc(t.account.split("@")[0])}</span>` : ""}
      <div class="subj">${chips}${esc(t.subject)} <span class="snip">— ${esc(t.snippet)}</span></div>
      ${t.unread_gmail ? `<span class="gm" title="Ainda não lida no Gmail (status preservado para a controladoria)">não lida no Gmail</span>` : ""}
      ${t.has_attachments ? "📎" : ""}
      <div class="date">${fmtDate(t.last_date)}</div></div>`;
  }).join("");
}

// ─── Leitura ─────────────────────────────────────────────────────────────
function showList() { $("#thread-view").classList.add("hidden"); $("#thread-list").classList.remove("hidden"); $("#list-toolbar").classList.remove("hidden"); }
function showView() { $("#thread-view").classList.remove("hidden"); $("#thread-list").classList.add("hidden"); $("#list-toolbar").classList.add("hidden"); }

async function openThread(account, threadId) {
  const data = await api(`/api/threads/${encodeURIComponent(account)}/${threadId}`);
  state.current = data;
  const t = state.threads.find(x => x.thread_id === threadId && x.account === account);
  if (t) t.read_local = true;
  renderThreadView();
  showView();
  refreshStatus();
}

function renderThreadView() {
  const d = state.current, v = $("#thread-view");
  const msgs = d.messages;
  const labelChips = d.label_ids.map(id => labelById(d.account, id)).filter(l => l && l.type === "user").map(l => chipHtml(l, true)).join("");
  v.innerHTML = `
    <div class="tv-head">
      <button class="icon-btn" id="tv-back" title="Voltar">←</button>
      <div class="dropdown"><button class="tool-btn" id="tv-labels-btn">🏷️ Etiquetas ▾</button><div class="menu hidden" id="tv-label-menu"></div></div>
      <button class="tool-btn" id="tv-unread" title="Volta a aparecer como não lida apenas no MarquesPro">✉ Marcar não lida (local)</button>
      <span class="spacer"></span><span class="hint">${esc(d.account)}</span>
    </div>
    <h2 class="tv-subject">${esc(msgs[0].subject)}</h2>
    <div class="tv-labels" id="tv-labels">${labelChips}</div>
    ${msgs.map((m, i) => msgHtml(m, i === msgs.length - 1)).join("")}`;
  msgs.forEach((m, i) => renderBody(m, $(`#body-${i}`), false));
  $("#tv-back").onclick = () => { showList(); renderThreads(); };
  $("#tv-unread").onclick = guard(async () => {
    await api(`/api/threads/${encodeURIComponent(d.account)}/${d.thread_id}/nao-lida`, {method: "POST"});
    const t = state.threads.find(x => x.thread_id === d.thread_id); if (t) t.read_local = false;
    showList(); renderThreads(); refreshStatus();
  });
  $("#tv-labels-btn").onclick = (e) => { e.stopPropagation(); labelMenu($("#tv-label-menu"), d.account, d.label_ids, async (add, remove) => {
    await api("/api/threads/labels", {body: {account: d.account, thread_ids: [d.thread_id], add, remove}});
    await openThread(d.account, d.thread_id); toast("Etiquetas atualizadas no Gmail");
  }); };
  $$("#tv-labels .x").forEach(x => x.onclick = guard(async () => {
    const id = x.parentElement.dataset.label;
    await api("/api/threads/labels", {body: {account: d.account, thread_ids: [d.thread_id], remove: [id]}});
    await openThread(d.account, d.thread_id);
  }));
  $$(".msg-head", v).forEach(h => h.onclick = () => h.parentElement.classList.toggle("collapsed"));
  $$("[data-act]", v).forEach(b => b.onclick = guard(() => startReply(b.dataset.act, d.account, b.dataset.mid)));
}

function msgHtml(m, expanded) {
  const i = state.current.messages.indexOf(m);
  const name = m.from_name || m.from_email;
  const atts = (m.body && m.body.attachments || []).map(a =>
    `<a class="att" href="${attUrl(state.current.account, m.id, a)}" title="${esc(a.filename)}">📎 ${esc(a.filename)} <small class="muted">${Math.ceil((a.size || 0) / 1024)} KB</small></a>`).join("");
  return `<div class="msg ${expanded ? "" : "collapsed"}">
    <div class="msg-head">
      <div class="avatar" style="background:${colorFor(m.from_email)}">${esc((name || "?").trim()[0] || "?").toUpperCase()}</div>
      <div class="msg-meta">
        <div class="msg-from"><b>${esc(name)}</b> <span class="em">&lt;${esc(m.from_email)}&gt;</span>
          ${m.unread_gmail ? `<span class="chip" style="background:#fff4e5;color:#a15c00">não lida no Gmail</span>` : ""}</div>
        <div class="msg-to">para ${esc(m.to_raw)}${m.cc_raw ? ` · cc ${esc(m.cc_raw)}` : ""}</div>
        <div class="msg-snip">${esc(m.snippet)}</div>
      </div>
      <div class="msg-date">${fmtDate(m.internal_date, true)}</div>
    </div>
    <div class="msg-body"><div id="body-${i}"></div>${atts ? `<div class="atts">${atts}</div>` : ""}
      <div class="msg-actions">
        <button class="pill" data-act="responder" data-mid="${m.id}">↩ Responder</button>
        <button class="pill" data-act="responder_todos" data-mid="${m.id}">↩↩ Responder a todos</button>
        <button class="pill" data-act="encaminhar" data-mid="${m.id}">↪ Encaminhar</button>
      </div></div></div>`;
}

function renderBody(m, holder, showImages) {
  const b = m.body || {html: "", text: ""};
  let content = b.html || `<pre style="white-space:pre-wrap;font-family:inherit">${esc(b.text)}</pre>`;
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
    <meta name="referrer" content="no-referrer"><base target="_blank"><style>body{font-family:Arial,sans-serif;font-size:14px;margin:0;word-wrap:break-word;color:#202124}img{max-width:100%;height:auto}</style></head><body>${content}</body></html>`;
  holder.innerHTML = (hasRemote && !showImages)
    ? `<div class="img-warn">Imagens externas bloqueadas (evita aviso de leitura ao remetente). <button>Exibir imagens</button></div>` : "";
  const fr = document.createElement("iframe");
  fr.setAttribute("sandbox", "allow-same-origin allow-popups allow-popups-to-escape-sandbox");
  fr.srcdoc = doc;
  fr.onload = () => {
    try {
      fr.contentDocument.querySelectorAll("a[href]").forEach(a => { a.target = "_blank"; a.rel = "noopener noreferrer"; });
      fr.style.height = (fr.contentDocument.documentElement.scrollHeight + 16) + "px";
    } catch (_) {}
  };
  holder.appendChild(fr);
  const btn = $(".img-warn button", holder);
  if (btn) btn.onclick = () => renderBody(m, holder, true);
}

// ─── Menu de etiquetas (reutilizado) ─────────────────────────────────────
function labelMenu(menu, account, currentIds, onApply, opts = {}) {
  closeMenus(menu);
  if (!account) { toast("Selecione uma conta para gerenciar etiquetas", true); return; }
  const labels = userLabels(account).sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
  const cur = new Set(currentIds || []);
  menu.innerHTML = labels.map(l => `<label><input type="checkbox" value="${esc(l.id)}" ${cur.has(l.id) ? "checked" : ""}>
      <span class="dot" style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${esc(l.bg_color || "#c4c7c5")}"></span>${esc(l.name)}</label>`).join("")
    + `<div class="menu-foot"><button class="btn primary">${opts.applyText || "Aplicar"}</button><button class="btn" data-new>+ Nova</button></div>`;
  menu.classList.remove("hidden");
  menu.onclick = (e) => e.stopPropagation();
  $(".btn.primary", menu).onclick = guard(async () => {
    const checked = new Set($$("input:checked", menu).map(i => i.value));
    const add = [...checked].filter(id => !cur.has(id));
    const remove = [...cur].filter(id => !checked.has(id) && labels.some(l => l.id === id));
    menu.classList.add("hidden");
    await onApply(add, remove, [...checked]);
  });
  $("[data-new]", menu).onclick = guard(async () => {
    const name = prompt("Nome da nova etiqueta (use / para aninhar, ex.: MarquesPro/Tribunal):");
    if (!name) return;
    await api("/api/labels", {body: {account, name}});
    await loadLabels();
    labelMenu(menu, account, currentIds, onApply, opts);
  });
}
function closeMenus(except) { $$(".menu").forEach(m => { if (m !== except) m.classList.add("hidden"); }); $$(".ac").forEach(a => a.classList.add("hidden")); }

// ─── Composição ──────────────────────────────────────────────────────────
const compose = {mode: "novo", account: "", ref: null, files: [], labels: [], fwdAtts: []};

function fromOptions(onlyAccount) {
  const list = state.sendAs.filter(s => !onlyAccount || s.account === onlyAccount);
  const accs = state.accounts.map(a => a.email).filter(a => !onlyAccount || a === onlyAccount);
  // Garante a conta principal mesmo sem dados de send-as
  accs.forEach(a => { if (!list.some(s => s.account === a && s.email === a)) list.push({account: a, email: a, display_name: "", signature: ""}); });
  return list;
}

function openCompose(ctx = {}) {
  if (!state.accounts.length) { toast("Conecte uma conta primeiro", true); openSettings("tab-accounts"); return; }
  Object.assign(compose, {mode: ctx.mode || "novo", account: ctx.account || "", ref: ctx.ref || null, files: [],
    labels: ctx.labels || [], fwdAtts: ctx.attachments || []});
  const opts = fromOptions(ctx.account || "");
  const sel = $("#c-from");
  sel.innerHTML = opts.map(s => `<option value="${esc(s.account + "|" + s.email)}">${esc(s.display_name ? `${s.display_name} <${s.email}>` : s.email)}</option>`).join("");
  const pref = ctx.fromEmail && opts.find(s => s.email === ctx.fromEmail)
    || opts.find(s => s.account === (state.account || s.account) && s.is_default) || opts[0];
  if (pref) sel.value = pref.account + "|" + pref.email;
  $("#c-to").value = ctx.to || "";
  $("#c-cc").value = ctx.cc || ""; $("#c-bcc").value = "";
  $("#c-cc-row").classList.toggle("hidden", !ctx.cc); $("#c-bcc-row").classList.add("hidden");
  $("#c-subject").value = ctx.subject || "";
  $("#compose-title").textContent = {novo: "Nova mensagem", responder: "Responder", responder_todos: "Responder a todos", encaminhar: "Encaminhar"}[compose.mode];
  const ed = $("#c-editor");
  ed.innerHTML = `<div><br></div><div class="sig" data-sig></div>${ctx.quoted ? `<div data-quoted>${sanitizeHtml(ctx.quoted)}</div>` : ""}`;
  applySignature();
  $("#c-fwd-att").classList.toggle("hidden", !(compose.mode === "encaminhar" && compose.fwdAtts.length));
  $("#c-fwd-att-list").textContent = compose.fwdAtts.map(a => a.filename).join(", ");
  $("#c-fwd-att-chk").checked = true;
  renderComposeFiles(); renderComposeLabels();
  $("#c-status").textContent = "";
  $("#compose").classList.remove("hidden", "min");
  (ctx.to ? ed : $("#c-to")).focus();
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
  $("#c-files").innerHTML = compose.files.map((f, i) => `<span class="chip">📎 ${esc(f.name)}<span class="x" data-i="${i}">✕</span></span>`).join("");
  $$("#c-files .x").forEach(x => x.onclick = () => { compose.files.splice(+x.dataset.i, 1); renderComposeFiles(); });
}
function renderComposeLabels() {
  const acc = currentFrom().account;
  $("#c-label-chips").innerHTML = compose.labels.map(id => labelById(acc, id)).filter(Boolean).map(l => chipHtml(l, true)).join("") || `<span class="muted">nenhuma</span>`;
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
    toast("Mensagem enviada");
    if (state.current && !$("#thread-view").classList.contains("hidden")) await openThread(state.current.account, state.current.thread_id);
    else await loadThreads();
  } catch (e) { $("#c-status").textContent = ""; toast(e.message, true); }
  finally { btn.disabled = false; }
}

// Autocompletar destinatários (nome já aparece junto ao e-mail)
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
      box.innerHTML = items.map((c, i) => `<div data-i="${i}"><b>${esc(c.name || c.email)}</b> <small>${esc(c.email)}</small></div>`).join("");
      $$("div", box).forEach(d => d.onmousedown = (e) => { e.preventDefault(); pick(items[+d.dataset.i]); });
      box.classList.remove("hidden");
    }), 200);
  });
  input.addEventListener("keydown", (e) => {
    if (box.classList.contains("hidden")) return;
    const ds = $$("div", box);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); on = (on + (e.key === "ArrowDown" ? 1 : -1) + ds.length) % ds.length;
      ds.forEach((d, i) => d.classList.toggle("on", i === on));
    } else if (e.key === "Enter" && on >= 0) { e.preventDefault(); pick(items[on]); }
    else if (e.key === "Escape") box.classList.add("hidden");
  });
  input.addEventListener("blur", () => setTimeout(() => box.classList.add("hidden"), 150));
}

// ─── Contador e notificações ─────────────────────────────────────────────
async function refreshStatus() {
  const s = await api(`/api/status?${qs({account: state.account, desde: state.lastNotif ?? 0})}`);
  const first = state.lastNotif === null;
  state.status = s;
  $("#counter-num").textContent = s.recebidas_hoje;
  if (!first && s.novas.length) {
    $("#counter").classList.remove("pulse"); void $("#counter").offsetWidth; $("#counter").classList.add("pulse");
    s.novas.slice(0, 3).forEach(n => {
      toast(`Novo e-mail: ${n.from_name || ""} — ${n.subject || ""}`);
      if ("Notification" in window && Notification.permission === "granted") {
        const nt = new Notification(n.from_name || "Novo e-mail", {body: n.subject || "", tag: n.message_id});
        nt.onclick = () => { window.focus(); openThread(n.account, n.thread_id); };
      }
    });
    if (!$("#thread-list").classList.contains("hidden")) loadThreads();
  }
  state.lastNotif = s.ultimo_id;
  document.title = (s.nao_lidas_local ? `(${s.nao_lidas_local}) ` : "") + "MarquesPro Mail";
  renderSidebar();
  if (!$("#counter-pop").classList.contains("hidden")) renderCounterPop();
}
function renderCounterPop() {
  const s = state.status; if (!s) return;
  $("#counter-pop").innerHTML = `
    <h4>Hoje</h4>
    <div class="kv"><span>Recebidas na caixa de entrada</span><b>${s.recebidas_hoje}</b></div>
    <div class="kv"><span>Novas notificações registradas hoje</span><b>${s.notificacoes_hoje}</b></div>
    <div class="kv"><span>Não lidas no MarquesPro</span><b>${s.nao_lidas_local}</b></div>
    ${s.hoje_por_etiqueta.length ? `<h4>Por etiqueta (hoje)</h4>` + s.hoje_por_etiqueta.map(l => `<div class="kv"><span>${esc(l.name)}</span><b>${l.n}</b></div>`).join("") : ""}
    ${s.novas.length ? `<h4>Últimas notificações</h4>` + s.novas.map(n => `<div class="nt" data-acc="${esc(n.account)}" data-tid="${esc(n.thread_id)}"><b>${esc(n.from_name || "")}</b><br><small>${esc(n.subject || "")} · ${esc(n.created_at.slice(11, 16))}</small></div>`).join("") : ""}
    <h4>Sincronização</h4>${s.contas.map(c => `<div class="kv"><small>${esc(c.email)}</small><small>${c.last_error ? "⚠ " + esc(c.last_error.slice(0, 60)) : esc(c.last_sync || "—")}</small></div>`).join("")}`;
  $$("#counter-pop .nt").forEach(n => n.onclick = guard(() => { $("#counter-pop").classList.add("hidden"); return openThread(n.dataset.acc, n.dataset.tid); }));
}

// ─── Configurações ───────────────────────────────────────────────────────
const ruleForm = {labels: []};
async function openSettings(tab) {
  $("#counter-pop").classList.add("hidden");
  $("#settings").classList.remove("hidden");
  selectTab(tab || "tab-accounts");
}
function selectTab(id) {
  $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === id));
  $$(".tab-pane").forEach(p => p.classList.toggle("hidden", p.id !== id));
  ({"tab-accounts": renderAccounts, "tab-signatures": renderSignatures, "tab-rules": renderRules})[id]();
}
function renderAccounts() {
  $("#acc-list").innerHTML = state.accounts.map(a => `<div class="card"><b>${esc(a.email)}</b>
    <div class="muted">Última sincronização: ${esc(a.last_sync || "—")}${a.last_error ? ` · <span style="color:var(--danger)">${esc(a.last_error)}</span>` : ""}</div>
    <button class="btn danger" data-disc="${esc(a.email)}">Desconectar</button></div>`).join("") || `<p class="muted">Nenhuma conta conectada.</p>`;
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
    <div class="muted" style="margin-top:6px">Assinatura no Gmail:</div>
    <div class="sig-preview" id="sigp-${i}"></div>
    <label><input type="checkbox" data-use="${i}" ${s.use_local ? "checked" : ""}> Usar assinatura local (HTML) em vez da do Gmail</label>
    <textarea data-loc="${i}" placeholder="Assinatura local (opcional)">${esc(s.local_signature || "")}</textarea>
    <button class="btn" data-save="${i}">Salvar</button></div>`).join("") || `<p class="muted">Nenhum remetente carregado. Clique em "Atualizar do Gmail".</p>`;
  state.sendAs.forEach((s, i) => {
    const fr = document.createElement("iframe");
    fr.setAttribute("sandbox", ""); fr.style.cssText = "width:100%;border:0;height:120px";
    fr.srcdoc = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data: https:">` +
      (s.api_signature || "<i style='color:#888'>Nenhuma assinatura cadastrada no Gmail</i>");
    $(`#sigp-${i}`).appendChild(fr);
  });
  $$("[data-save]").forEach(b => b.onclick = guard(async () => {
    const i = +b.dataset.save, s = state.sendAs[i];
    await api("/api/send-as/signature", {body: {account: s.account, email: s.email,
      local_signature: $(`[data-loc="${i}"]`).value, use_local: $(`[data-use="${i}"]`).checked}});
    await loadSendAs(); toast("Assinatura salva");
  }));
}
async function renderRules() {
  $("#r-account").innerHTML = state.accounts.map(a => `<option>${esc(a.email)}</option>`).join("");
  if (state.account) $("#r-account").value = state.account;
  renderRuleChips();
  const rules = await api("/api/rules");
  $("#rule-list").innerHTML = rules.map(r => `<tr>
    <td>${esc(r.account)}</td><td>${r.direction === "enviado" ? "Enviado por" : "Recebido de"}</td><td>${esc(r.pattern)}</td>
    <td>${r.label_ids.map(id => labelById(r.account, id)).filter(Boolean).map(l => chipHtml(l)).join("")}</td>
    <td><input type="checkbox" data-act="${r.id}" ${r.active ? "checked" : ""}></td>
    <td><button class="btn" data-apply="${r.id}">Aplicar às existentes</button> <button class="btn danger" data-del="${r.id}">Excluir</button></td></tr>`).join("")
    || `<tr><td colspan="6" class="muted">Nenhuma regra.</td></tr>`;
  $$("[data-act]", $("#rule-list")).forEach(c => c.onchange = guard(() => api(`/api/rules/${c.dataset.act}/ativo`, {body: {active: c.checked}})));
  $$("[data-apply]").forEach(b => b.onclick = guard(async () => {
    const r = await api(`/api/rules/${b.dataset.apply}/aplicar`, {method: "POST"});
    toast(`Etiquetas aplicadas em ${r.aplicadas} mensagem(ns)`);
  }));
  $$("[data-del]").forEach(b => b.onclick = guard(async () => {
    if (!confirm("Excluir esta regra? As etiquetas já aplicadas permanecem no Gmail.")) return;
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
  document.addEventListener("click", () => closeMenus());
  document.addEventListener("click", () => {
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  }, {once: true});

  $("#btn-menu").onclick = () => { $("#sidebar").classList.toggle(innerWidth < 800 ? "open" : "collapsed"); };
  $("#account-select").onchange = guard(async (e) => {
    state.account = e.target.value; state.lastNotif = null;
    if (state.folder.name) state.folder = {id: "INBOX"};
    renderSidebar(); await refreshStatus(); await loadThreads();
  });
  $("#folders").onclick = guard(async (e) => {
    const li = e.target.closest("li[data-folder]"); if (!li) return;
    state.folder = {id: li.dataset.folder}; state.search = ""; $("#search-input").value = "";
    renderSidebar(); await loadThreads();
  });
  $("#label-list").onclick = guard(async (e) => {
    const li = e.target.closest("li[data-label-name]"); if (!li) return;
    state.folder = {id: li.dataset.labelId, name: li.dataset.labelName}; state.search = ""; $("#search-input").value = "";
    renderSidebar(); await loadThreads();
  });
  $("#btn-new-label").onclick = guard(async () => {
    const acc = state.account || (state.accounts[0] && state.accounts[0].email);
    if (!acc) return toast("Conecte uma conta primeiro", true);
    const name = prompt(`Nova etiqueta em ${acc} (use / para aninhar):`);
    if (!name) return;
    await api("/api/labels", {body: {account: acc, name}}); await loadLabels(); toast("Etiqueta criada no Gmail");
  });
  $("#search-form").onsubmit = guard(async (e) => {
    e.preventDefault(); state.search = $("#search-input").value.trim(); state.searchGmail = $("#search-gmail").checked; await loadThreads();
  });
  $("#only-unread").onchange = guard(loadThreads);
  $("#btn-refresh").onclick = guard(loadThreads);
  $("#btn-sync").onclick = guard(async () => {
    toast("Sincronizando…");
    const r = await api("/api/sync", {method: "POST"});
    r.filter(x => x.status === "erro").forEach(x => toast(`${x.account}: ${x.erro}`, true));
    await loadLabels(); await refreshStatus(); await loadThreads();
  });
  $("#counter").onclick = (e) => { e.stopPropagation(); const p = $("#counter-pop"); p.classList.toggle("hidden"); renderCounterPop(); };
  $("#counter-pop").onclick = (e) => e.stopPropagation();

  // Lista
  $("#thread-list").onclick = guard(async (e) => {
    const row = e.target.closest(".row-t"); if (!row) return;
    const i = +row.dataset.i, t = state.threads[i];
    if (e.target.classList.contains("sel")) {
      e.target.checked ? state.selected.add(i) : state.selected.delete(i); row.classList.toggle("selected", e.target.checked); return;
    }
    if (e.target.classList.contains("star")) {
      const on = t.label_ids.includes("STARRED");
      await api("/api/threads/labels", {body: {account: t.account, thread_ids: [t.thread_id], [on ? "remove" : "add"]: ["STARRED"]}});
      t.label_ids = on ? t.label_ids.filter(x => x !== "STARRED") : [...t.label_ids, "STARRED"]; renderThreads(); return;
    }
    await openThread(t.account, t.thread_id);
  });
  $("#select-all").onchange = (e) => {
    state.selected = new Set(e.target.checked ? state.threads.map((_, i) => i) : []); renderThreads();
  };
  $("#btn-bulk-labels").onclick = (e) => {
    e.stopPropagation();
    const sel = [...state.selected].map(i => state.threads[i]);
    if (!sel.length) return toast("Selecione conversas", true);
    const accs = [...new Set(sel.map(t => t.account))];
    if (accs.length > 1) return toast("Selecione conversas de uma única conta", true);
    const common = sel.map(t => t.label_ids).reduce((a, b) => a.filter(x => b.includes(x)));
    labelMenu($("#bulk-label-menu"), accs[0], common, async (add, remove) => {
      await api("/api/threads/labels", {body: {account: accs[0], thread_ids: sel.map(t => t.thread_id), add, remove}});
      toast("Etiquetas replicadas no Gmail"); await loadThreads();
    });
  };
  $("#btn-bulk-unread").onclick = guard(async () => {
    for (const i of state.selected) { const t = state.threads[i];
      await api(`/api/threads/${encodeURIComponent(t.account)}/${t.thread_id}/nao-lida`, {method: "POST"}); }
    await loadThreads(); await refreshStatus();
  });

  // Composição
  $("#btn-compose").onclick = () => openCompose({mode: "novo"});
  $("#compose-close").onclick = (e) => { e.stopPropagation(); if (confirm("Descartar a mensagem?")) $("#compose").classList.add("hidden"); };
  $("#compose-min").onclick = (e) => { e.stopPropagation(); $("#compose").classList.toggle("min"); };
  $(".compose-head").onclick = () => $("#compose").classList.remove("min");
  $("#c-from").onchange = applySignature;
  $("#c-show-cc").onclick = (e) => { e.preventDefault(); $("#c-cc-row").classList.remove("hidden"); $("#c-bcc-row").classList.remove("hidden"); };
  $("#c-attach").onchange = (e) => { compose.files.push(...e.target.files); e.target.value = ""; renderComposeFiles(); };
  $("#c-send").onclick = sendCompose;
  $$(".editor-tools button").forEach(b => b.onclick = (e) => {
    e.preventDefault(); const cmd = b.dataset.cmd;
    if (cmd === "createLink") { const u = prompt("Endereço do link:"); if (u && /^(https?:|mailto:)/i.test(u)) document.execCommand(cmd, false, u); }
    else document.execCommand(cmd);
    $("#c-editor").focus();
  });
  $("#c-add-label").onclick = (e) => {
    e.preventDefault(); e.stopPropagation();
    labelMenu($("#c-label-menu"), currentFrom().account, compose.labels, (add, remove, all) => { compose.labels = all; renderComposeLabels(); }, {applyText: "OK"});
  };
  ["#c-to", "#c-cc", "#c-bcc"].forEach(s => setupAutocomplete($(s)));

  // Configurações
  $("#btn-settings").onclick = () => openSettings();
  $("#settings-close").onclick = guard(async () => { $("#settings").classList.add("hidden"); await loadAccounts(); await loadLabels(); await loadSendAs(); });
  $$(".tab").forEach(t => t.onclick = () => selectTab(t.dataset.tab));
  $("#acc-connect").onclick = guard(async () => {
    toast("Abra a janela do Google para autorizar a conta…");
    const r = await api("/api/accounts/connect", {body: {email: $("#acc-hint").value.trim()}});
    toast(`Conta ${r.email} conectada`);
    await loadAccounts(); await loadLabels(); await loadSendAs(); renderAccounts(); await refreshStatus(); await loadThreads();
  });
  $("#sig-refresh").onclick = guard(async () => { state.sendAs = await api("/api/send-as/refresh", {method: "POST"}); renderSignatures(); toast("Remetentes e assinaturas atualizados"); });
  $("#r-account").onchange = () => { ruleForm.labels = []; renderRuleChips(); };
  $("#r-labels-btn").onclick = (e) => {
    e.stopPropagation();
    labelMenu($("#r-label-menu"), $("#r-account").value, ruleForm.labels, (a, r, all) => { ruleForm.labels = all; renderRuleChips(); }, {applyText: "OK"});
  };
  $("#r-save").onclick = guard(async () => {
    const r = await api("/api/rules", {body: {account: $("#r-account").value, direction: $("#r-direction").value,
      pattern: $("#r-pattern").value, label_ids: ruleForm.labels, aplicar_existentes: $("#r-existing").checked}});
    toast(`Regra criada${r.aplicadas ? ` e aplicada em ${r.aplicadas} mensagem(ns)` : ""}`);
    $("#r-pattern").value = ""; ruleForm.labels = []; renderRules();
  });
}

// ─── Início ──────────────────────────────────────────────────────────────
(async function init() {
  bind();
  await guard(async () => {
    await loadAccounts();
    await Promise.all([loadLabels(), loadSendAs()]);
    await refreshStatus();
    await loadThreads();
  })();
  setInterval(guard(refreshStatus), 20000);
})();
})();
