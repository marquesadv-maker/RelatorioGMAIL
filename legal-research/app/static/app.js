/* Legal Research Local — frontend (vanilla JS) */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const LIMITE = 30;
let deslocamento = 0, ultimoTotal = 0, opcoes = {}, itensAtuais = [], ctrl = null, seq = 0, tmBusca = null;

const api = async (url, body, method, signal) => {
  const r = await fetch(url, { method: method || (body ? 'POST' : 'GET'), headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined, signal });
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(m); }
  return r.json();
};
const toast = (m) => { const t = $('#toast'); t.textContent = m; t.classList.remove('oculto'); setTimeout(() => t.classList.add('oculto'), 3500); };
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const brl = (v) => v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const sel = (id) => $$(`#${id} option:checked`).map(o => o.value);
const faixa = (a, b) => { const o = {}; if ($(a).value) o.min = Number($(a).value); if ($(b).value) o.max = Number($(b).value); return Object.keys(o).length ? o : undefined; };
const per = (a, b) => { const o = {}; if ($(a).value) o.min = $(a).value; if ($(b).value) o.max = $(b).value; return Object.keys(o).length ? o : undefined; };
const lista = (id) => $(id).value.trim() ? [$(id).value.trim()] : undefined;

// -------------------------------------------------------------- consulta
function montarConsulta() {
  const fg = {
    esfera: 'Trabalhista', ufs: sel('f_ufs'), tribunais: sel('f_tribunais'), classes: sel('f_classes'), assuntos: sel('f_assuntos'),
    fases: sel('f_fases'), status: sel('f_status'), desfechos: sel('f_desfechos'), graus: sel('f_graus'), comarcas: sel('f_comarcas'),
    orgaosJulgadores: lista('#f_orgao'), partes: lista('#f_parte'), advogados: lista('#f_advogado'), magistrados: lista('#f_magistrado'),
    cnpjs: lista('#f_cnpj'), atividadesEconomicas: lista('#f_atividade'), numeroProcesso: $('#f_numero').value.trim() || undefined,
    periodo: per('#f_ajIni', '#f_ajFim'),
    faixaValorCausa: faixa('#v_causaMin', '#v_causaMax'), faixaValorCondenacao: faixa('#v_condMin', '#v_condMax'),
    faixaValorAcordo: faixa('#v_acMin', '#v_acMax'), faixaValorLiquidacao: faixa('#v_liqMin', '#v_liqMax'), faixaCustas: faixa('#v_cusMin', '#v_cusMax'),
    filtrarValoresAnomalos: $('#v_anomalos').checked || undefined,
  };
  $$('.flag:checked').forEach(c => fg[c.value] = true);
  const ft = {
    trecho: $('#q').value.trim(), modoIA: $('input[name=modo]:checked').value === 'ia',
    tiposEntidades: $$('#f_tiposEntidades input:checked').map(c => c.value),
    tiposDocumento: sel('f_tiposDocumento'), fasesDocumento: sel('f_fasesDocumento'),
    periodoDataDocumento: per('#f_docIni', '#f_docFim'), tipoOrdenacao: $('#ordem').value,
    buscaDocumentosAvancada: { todasPalavras: $('#a_todas').value, fraseExata: $('#a_frase').value, aoMenosUma: $('#a_alguma').value, nenhumaPalavra: $('#a_nenhuma').value, numeroLei: $('#a_lei').value, anoLei: $('#a_anoLei').value },
  };
  return { filtroGeral: { conteudo: fg }, filtroPesquisaTextual: { conteudo: ft } };
}

const agendarBusca = (ms = 250) => { clearTimeout(tmBusca); tmBusca = setTimeout(() => buscar(), ms); };

async function buscar(reset = true) {
  if (reset) { deslocamento = 0; itensAtuais = []; }
  if (ctrl) ctrl.abort();
  ctrl = new AbortController(); const meu = ++seq;
  const q = montarConsulta();
  history.replaceState(null, '', '#' + encodeURIComponent(JSON.stringify({ c: q })));
  if (reset) $('#resultados').innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
  $('#maisBtn').classList.add('oculto');
  try {
    const t0 = performance.now();
    const pr = api(`/api/documento?limite=${LIMITE}&deslocamento=${deslocamento}`, q, null, ctrl.signal);
    const pm = reset ? api('/api/documento/obterMenuLateral', q, null, ctrl.signal) : null;
    const r = await pr; if (meu !== seq) return;
    ultimoTotal = r.totalTrechos;
    itensAtuais = reset ? r.resultados : itensAtuais.concat(r.resultados);
    $('#contagem').innerHTML = `<b>${r.totalProcessos.toLocaleString('pt-BR')}</b> processos · <b>${r.totalDocumentos.toLocaleString('pt-BR')}</b> documentos · <b>${r.totalTrechos.toLocaleString('pt-BR')}</b> trechos <span class="tempo">${Math.round(performance.now() - t0)} ms${r.cache ? ' · cache' : ''}</span>`;
    $('#juriN').textContent = r.totalProcessos.toLocaleString('pt-BR');
    renderResultados(itensAtuais, $('#resultados'));
    $('#pagInfo').textContent = `${Math.min(itensAtuais.length, ultimoTotal)} de ${ultimoTotal.toLocaleString('pt-BR')} trechos`;
    $('#maisBtn').classList.toggle('oculto', itensAtuais.length >= ultimoTotal);
    if (pm) { const m = await pm; if (meu === seq) renderFacetas(m); }
    if (reset && r.totalTrechos === 0 && $('#online').checked) buscarOnline(meu);
  } catch (e) { if (e.name !== 'AbortError') $('#resultados').innerHTML = `<p class="meta">Erro: ${esc(e.message)}</p>`; }
}

let onlineFeito = new Set();
async function buscarOnline(meu, forcar = false) {
  const termo = $('#q').value.trim().replace(/"/g, ''); const campo = $('#onlineCampo').value; const chave = campo + ':' + termo.toLowerCase();
  if (termo.length < 4) { if (forcar) $('#onlineStatus').textContent = 'Digite ao menos 4 letras do nome.'; return; }
  if (onlineFeito.has(chave) && !forcar) { $('#onlineStatus').textContent = 'DJEN já consultado para este nome: nenhuma publicação na Justiça do Trabalho.'; return; }
  $('#onlineStatus').textContent = 'Consultando o DJEN (CNJ)…'; $('#btnOnline').disabled = true;
  $('#resultados').innerHTML = '<p class="meta">Nenhum resultado na base local. Consultando publicações oficiais no DJEN (CNJ)…</p><div class="skeleton"></div><div class="skeleton"></div>';
  try {
    const r = await api('/api/busca-online', { termo, campo });
    onlineFeito.add(chave);
    $('#onlineStatus').textContent = `DJEN: ${r.publicacoes} publicação(ões) nova(s) em ${r.processos + r.atualizados} processo(s)`;
    if (r.publicacoes > 0 || r.atualizados > 0) { await carregarOpcoes(); if (meu === undefined || meu === seq) buscar(); toast(`${r.publicacoes} publicação(ões) importadas do DJEN`); }
    else $('#resultados').innerHTML = '<p class="meta">Nenhuma publicação encontrada no DJEN para este nome na Justiça do Trabalho. Tente "como nome de advogado", outra grafia, ou desmarque "Somente Justiça do Trabalho" em Fontes de dados.</p>';
  } catch (e) { $('#onlineStatus').textContent = 'DJEN: ' + e.message; $('#resultados').innerHTML = `<p class="meta">Nenhum resultado na base local. Busca online indisponível: ${esc(e.message)}</p>`; }
  $('#btnOnline').disabled = false;
}
$('#btnOnline').onclick = () => buscarOnline(undefined, true);
const carregarMais = () => { if (itensAtuais.length >= ultimoTotal || $('#maisBtn').classList.contains('oculto')) return; deslocamento += LIMITE; buscar(false); };
new IntersectionObserver(es => { if (es[0].isIntersecting) carregarMais(); }).observe($('#sentinela'));
$('#maisBtn').onclick = carregarMais;

function renderResultados(itens, alvo) {
  if (!itens.length) { alvo.innerHTML = '<p class="meta">Nenhum resultado. Importe dados em "Fontes de dados" ou ajuste os filtros.</p>'; return; }
  const favs = getFavs();
  alvo.innerHTML = itens.map(r => `
  <article class="resultado" data-id="${r.pagina_id}">
    <div class="cab">
      <div><span class="proc" data-proc="${r.processo_id}">${esc(r.processo)}</span><span class="trib">${esc(r.tribunal || '')} ${r.uf ? '· ' + esc(r.uf) : ''} ${r.orgao_julgador ? '· ' + esc(r.orgao_julgador) : ''}</span></div>
      <div class="menu"><button title="Mais">⋯</button><ul>
        <li data-acao="abrir">Abrir documento</li><li data-acao="pdf">Download / arquivo</li><li data-acao="imprimir">Imprimir</li>
        <li data-acao="fav">${favs[r.pagina_id] ? '★ Remover dos favoritos' : '☆ Favoritar'}</li><li data-acao="compartilhar">Compartilhar</li></ul></div>
    </div>
    <div class="partes">${(r.partes || []).map(p => `<span class="polo ${p.polo}">${p.polo === 'ativo' ? 'Ativo' : p.polo === 'passivo' ? 'Passivo' : esc(p.polo || '')}</span>${esc(p.nome)}`).join(' &nbsp; ')}</div>
    <div class="meta"><b>${esc(r.tipo)}</b> · ${esc(r.data_documento || 'sem data')} · página ${r.pagina}/${r.paginas} · ${esc(r.fase_doc || '')} · ${esc(r.status || '')} · <i>${esc(r.arquivo)}</i></div>
    <div class="trecho">${r.trecho}</div>
  </article>`).join('');
  alvo.dataset.itens = JSON.stringify(itens);
  // destaque adicional (termos avançados) no lado do cliente
}

function renderFacetas(m) {
  const chips = [];
  const add = (grupo, lab, campo) => (m[grupo] || []).slice(0, 8).forEach(x => chips.push(`<span class="faceta" data-campo="${campo}" data-valor="${esc(x.valor)}">${lab}: ${esc(x.valor)} <b>${x.quantidade}</b></span>`));
  add('tiposDocumento', 'Doc', 'f_tiposDocumento'); add('tribunais', 'Trib', 'f_tribunais'); add('fases', 'Fase', 'f_fases'); add('status', 'Status', 'f_status'); add('assuntos', 'Assunto', 'f_assuntos');
  const ents = m.entidades || {};
  const nomes = { pessoas: 'Pessoa', organizacoes: 'Org', juizes: 'Juiz', varas: 'Vara', fundamentos: 'Fund', funcoes: 'Função' };
  Object.entries(nomes).forEach(([k, lab]) => (ents[k] || []).slice(0, 5).forEach(x => chips.push(`<span class="faceta" data-ent="${k}" data-valor="${esc(x.valor)}">${lab}: ${esc(x.valor)} <b>${x.quantidade}</b></span>`)));
  $('#facetas').innerHTML = chips.join('');
}

$('#facetas').addEventListener('click', e => {
  const f = e.target.closest('.faceta'); if (!f) return;
  if (f.dataset.campo) { const s = $('#' + f.dataset.campo); [...s.options].forEach(o => { if (o.value === f.dataset.valor) o.selected = true; }); }
  else { $('#q').value = f.dataset.valor; $$('#f_tiposEntidades input').forEach(c => c.checked = c.value === f.dataset.ent); }
  buscar();
});

// -------------------------------------------------------------- ações por resultado
document.addEventListener('click', async e => {
  const mb = e.target.closest('.menu > button');
  $$('.menu.aberto').forEach(m => { if (!m.contains(e.target)) m.classList.remove('aberto'); });
  if (mb) { mb.parentElement.classList.toggle('aberto'); return; }
  const li = e.target.closest('.menu li');
  if (li) {
    const art = li.closest('.resultado'); const itens = JSON.parse(art.parentElement.dataset.itens || '[]'); const r = itens.find(x => String(x.pagina_id) === art.dataset.id);
    li.closest('.menu').classList.remove('aberto');
    if (li.dataset.acao === 'abrir') abrirDocumento(r.documento_id, r.pagina);
    if (li.dataset.acao === 'pdf') window.open(`/api/documento/${r.documento_id}/arquivo`, '_blank');
    if (li.dataset.acao === 'imprimir') { await abrirDocumento(r.documento_id, r.pagina); setTimeout(() => window.print(), 300); }
    if (li.dataset.acao === 'fav') { toggleFav(r); renderResultados(itens, art.parentElement); }
    if (li.dataset.acao === 'compartilhar') { const u = location.origin + '/#' + encodeURIComponent(JSON.stringify({ doc: r.documento_id, pag: r.pagina })); navigator.clipboard?.writeText(u); toast('Link copiado: ' + u); }
    return;
  }
  const pr = e.target.closest('.proc'); if (pr) abrirProcesso(pr.dataset.proc);
});

async function abrirDocumento(id, pagina) {
  const d = await api(`/api/documento/${id}`);
  const hl = ($('#q').value.trim().replace(/"/g, '').split(/\s+/).filter(w => w.length > 2));
  const marcar = (t) => { let h = esc(t); hl.forEach(w => { h = h.replace(new RegExp('(' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi'), '<mark>$1</mark>'); }); return h; };
  const ents = {}; d.entidades.forEach(e => (ents[e.tipo] = ents[e.tipo] || new Set()).add(e.valor));
  $('#modalCorpo').innerHTML = `<h3>${esc(d.documento.tipo)} — ${esc(d.documento.arquivo)}</h3>
    <p class="meta">Processo ${esc(d.documento.processo)} · ${esc(d.documento.tribunal || '')} · ${esc(d.documento.data_documento || '')} · ${d.documento.paginas} página(s)
    &nbsp; <a href="/api/documento/${id}/arquivo" target="_blank">abrir arquivo original</a></p>
    <div>${Object.entries(ents).map(([k, v]) => `<div><b>${k}</b>: ${[...v].slice(0, 30).map(x => `<span class="ent">${esc(x)}</span>`).join('')}</div>`).join('')}</div>
    ${d.paginas.map(p => `<div class="pagina-doc" id="pg${p.numero}"><h4>Página ${p.numero}</h4>${marcar(p.texto)}</div>`).join('')}`;
  $('#modal').classList.remove('oculto');
  if (pagina) setTimeout(() => $(`#pg${pagina}`)?.scrollIntoView({ behavior: 'smooth' }), 50);
}

async function abrirProcesso(id) {
  const p = await api(`/api/processo/${id}`); const x = p.processo;
  $('#modalCorpo').innerHTML = `<h3>Processo ${esc(x.numero)}</h3>
    <table class="tabela"><tr><th>Tribunal</th><td>${esc(x.tribunal)} / ${esc(x.uf || '')} · ${esc(x.grau || '')}</td></tr>
    <tr><th>Órgão julgador</th><td>${esc(x.orgao_julgador || '—')}</td></tr><tr><th>Classe</th><td>${esc(x.classe || '—')}</td></tr><tr><th>Assunto</th><td>${esc(x.assunto || '—')}</td></tr>
    <tr><th>Fase / Status / Desfecho</th><td>${esc(x.fase || '—')} / ${esc(x.status || '—')} / ${esc(x.desfecho || '—')}</td></tr>
    <tr><th>Ajuizamento</th><td>${esc(x.data_ajuizamento || '—')}</td></tr>
    <tr><th>Valores</th><td>Causa ${brl(x.valor_causa)} · Condenação ${brl(x.valor_condenacao)} · Acordo ${brl(x.valor_acordo)}</td></tr>
    <tr><th>Situações</th><td>${['transito_julgado', 'acordo_homologado', 'bloqueio', 'revelia', 'sindicato', 'acao_coletiva', 'covid'].filter(f => x[f]).join(', ') || '—'}</td></tr>
    <tr><th>Fonte</th><td>${esc(x.pasta || '')}</td></tr></table>
    <h4>Partes</h4>${p.partes.map(q => `<div><span class="polo ${q.polo}">${esc(q.polo || '')}</span>${esc(q.nome)} ${q.documento ? '· ' + esc(q.documento) : ''}</div>`).join('') || '—'}
    <h4>Profissionais</h4>${p.profissionais.map(q => `<div>${esc(q.papel)}: ${esc(q.nome)} ${q.registro ? '(' + esc(q.registro) + ')' : ''}</div>`).join('') || '—'}
    <h4>Documentos</h4><table class="tabela">${p.documentos.map(d => `<tr><td><a href="#" onclick="abrirDocumento(${d.id});return false">${esc(d.tipo)}</a></td><td>${esc(d.arquivo)}</td><td>${esc(d.data_documento || '')}</td><td>${d.paginas} pág.</td></tr>`).join('')}</table>`;
  $('#modal').classList.remove('oculto');
}
window.abrirDocumento = abrirDocumento;
$('#modalFechar').onclick = () => $('#modal').classList.add('oculto');
$('#modal').addEventListener('click', e => { if (e.target.id === 'modal') $('#modal').classList.add('oculto'); });

// -------------------------------------------------------------- favoritos (localStorage)
const getFavs = () => { try { return JSON.parse(localStorage.getItem('lr_favs') || '{}'); } catch (e) { return {}; } };
function toggleFav(r) { const f = getFavs(); if (f[r.pagina_id]) delete f[r.pagina_id]; else f[r.pagina_id] = r; try { localStorage.setItem('lr_favs', JSON.stringify(f)); } catch (e) {} atualizarFavCount(); }
function atualizarFavCount() { $('#favCount').textContent = Object.keys(getFavs()).length; }
function renderFavoritos() { renderResultados(Object.values(getFavs()), $('#listaFavoritos')); }

// -------------------------------------------------------------- jurimetria
$('#btnJurimetria').onclick = async () => {
  const j = await api('/api/jurimetria', montarConsulta());
  const tab = (t, arr) => arr?.length ? `<h4>${t}</h4><table class="tabela">${arr.map(x => `<tr><td>${esc(x.valor)}</td><td>${x.quantidade}</td></tr>`).join('')}</table>` : '';
  $('#modalCorpo').innerHTML = `<h3>Jurimetria (${j.processos} processos)</h3>
    <div class="grade-cartoes">
      <div class="kpi"><div class="n">${brl(j.valorMedioCausa)}</div><div class="l">valor médio da causa</div></div>
      <div class="kpi"><div class="n">${brl(j.valorMedioCondenacao)}</div><div class="l">condenação média</div></div>
      <div class="kpi"><div class="n">${brl(j.valorMedioAcordo)}</div><div class="l">acordo médio</div></div>
      <div class="kpi"><div class="n">${j.taxaAcordo == null ? '—' : (j.taxaAcordo * 100).toFixed(1) + '%'}</div><div class="l">taxa de acordo</div></div>
      <div class="kpi"><div class="n">${j.duracaoMediaDias == null ? '—' : Math.round(j.duracaoMediaDias) + ' dias'}</div><div class="l">duração média</div></div>
      <div class="kpi"><div class="n">${j.transitados ?? 0} / ${j.revelias ?? 0} / ${j.bloqueios ?? 0}</div><div class="l">transitados / revelias / bloqueios</div></div>
    </div>
    <div class="grade">${tab('Por tribunal', j.porTribunal)}${tab('Por UF', j.porUf)}${tab('Por fase', j.porFase)}${tab('Por status', j.porStatus)}${tab('Por desfecho', j.porDesfecho)}${tab('Por ano', j.porAno)}${tab('Por classe', j.porClasse)}${tab('Por assunto', j.porAssunto)}${tab('Por órgão', j.porOrgao)}${tab('Documentos por tipo', j.documentosPorTipo)}</div>
    <p class="meta">Valores de causa/condenação/acordo só existem quando informados nos metadados (processo.json) ou por provedor privado; o DataJud não os fornece.</p>`;
  $('#modal').classList.remove('oculto');
};

// -------------------------------------------------------------- filtros salvos / limpar
$('#btnLimpar').onclick = () => { $$('.filtros input, .filtros select').forEach(i => { if (i.type === 'checkbox') i.checked = false; else if (i.tagName === 'SELECT') [...i.options].forEach(o => o.selected = false); else i.value = ''; }); buscar(); };
$('#btnSalvarFiltro').onclick = async () => { const nome = prompt('Nome do filtro:'); if (!nome) return; await api('/api/filtros', { nome, corpo: montarConsulta() }); carregarFiltrosSalvos(); toast('Filtro salvo'); };
async function carregarFiltrosSalvos() {
  const fs = await api('/api/filtros');
  $('#filtrosSalvos').innerHTML = fs.map(f => `<button data-id="${f.id}" title="Clique para aplicar; Shift+clique para apagar">${esc(f.nome)}</button>`).join('');
  $$('#filtrosSalvos button').forEach(b => b.onclick = async (e) => {
    const f = fs.find(x => String(x.id) === b.dataset.id);
    if (e.shiftKey) { await api(`/api/filtros/${f.id}`, null, 'DELETE'); carregarFiltrosSalvos(); return; }
    aplicarConsulta(f.corpo); buscar();
  });
}
function aplicarConsulta(c) {
  const fg = c.filtroGeral?.conteudo || {}, ft = c.filtroPesquisaTextual?.conteudo || {};
  $('#q').value = ft.trecho || '';
  const setSel = (id, vals) => [...$('#' + id).options].forEach(o => o.selected = (vals || []).includes(o.value));
  setSel('f_ufs', fg.ufs); setSel('f_tribunais', fg.tribunais); setSel('f_classes', fg.classes); setSel('f_assuntos', fg.assuntos); setSel('f_fases', fg.fases); setSel('f_status', fg.status); setSel('f_desfechos', fg.desfechos); setSel('f_graus', fg.graus); setSel('f_tiposDocumento', ft.tiposDocumento); setSel('f_fasesDocumento', ft.fasesDocumento);
  $('#f_parte').value = (fg.partes || [])[0] || ''; $('#f_advogado').value = (fg.advogados || [])[0] || ''; $('#f_magistrado').value = (fg.magistrados || [])[0] || ''; $('#f_numero').value = fg.numeroProcesso || '';
  $$('.flag').forEach(c => c.checked = !!fg[c.value]); $$('#f_tiposEntidades input').forEach(c => c.checked = (ft.tiposEntidades || []).includes(c.value));
  const a = ft.buscaDocumentosAvancada || {}; $('#a_todas').value = a.todasPalavras || ''; $('#a_frase').value = a.fraseExata || ''; $('#a_alguma').value = a.aoMenosUma || ''; $('#a_nenhuma').value = a.nenhumaPalavra || ''; $('#a_lei').value = a.numeroLei || ''; $('#a_anoLei').value = a.anoLei || '';
}

// -------------------------------------------------------------- opções, autocomplete, navegação
async function carregarOpcoes() {
  opcoes = await api('/api/opcoes');
  const fill = (id, arr) => { const s = $('#' + id); const cur = sel(id); s.innerHTML = (arr || []).map(v => `<option ${cur.includes(v) ? 'selected' : ''}>${esc(v)}</option>`).join(''); };
  fill('f_tiposDocumento', opcoes.tiposDocumento); fill('f_ufs', opcoes.ufs); fill('f_tribunais', opcoes.tribunais); fill('f_classes', opcoes.classes); fill('f_assuntos', opcoes.assuntos); fill('f_desfechos', opcoes.desfechos); fill('f_comarcas', opcoes.comarcas);
  const t = await api('/api/home/total', {}); $('#totalBase').textContent = `${t.processos.toLocaleString('pt-BR')} processos · ${t.documentos.toLocaleString('pt-BR')} documentos · ${t.paginas.toLocaleString('pt-BR')} páginas`;
}
[['f_parte', 'parte'], ['f_advogado', 'advogado'], ['f_magistrado', 'magistrado'], ['f_orgao', 'orgaoJulgador'], ['f_numero', 'processo']].forEach(([id, campo]) => {
  let tm; $('#' + id).addEventListener('input', e => { clearTimeout(tm); tm = setTimeout(async () => { const v = await api(`/api/autocomplete/Trabalhista/${campo}?q=${encodeURIComponent(e.target.value)}`); $('#dl_' + campo).innerHTML = v.map(x => `<option value="${esc(x)}">`).join(''); }, 200); });
});
$$('.tab').forEach(b => b.onclick = () => { $$('.tab').forEach(x => x.classList.remove('ativo')); b.classList.add('ativo'); $$('.view').forEach(v => v.classList.add('oculto')); $('#view-' + b.dataset.view).classList.remove('oculto'); if (b.dataset.view === 'favoritos') renderFavoritos(); if (b.dataset.view === 'painel') renderPainel(); if (b.dataset.view === 'fontes') { statusFontes(); acompanharTarefas(); } });
$('#formBusca').onsubmit = e => { e.preventDefault(); buscar(); };
$('#q').addEventListener('input', () => agendarBusca(300));
$$('input[name=modo]').forEach(r => r.onchange = () => buscar());
$('#ordem').onchange = () => buscar();
$$('.filtros input, .filtros select').forEach(el => {
  el.addEventListener('change', () => agendarBusca(150));
  if (el.tagName === 'INPUT' && !['checkbox', 'date', 'number'].includes(el.type)) el.addEventListener('input', () => agendarBusca(400));
});
document.addEventListener('keydown', e => {
  if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') { e.preventDefault(); $('#q').focus(); $('#q').select(); }
  if (e.key === 'Escape') $('#modal').classList.add('oculto');
  if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && document.activeElement.tagName !== 'INPUT') {
    const arts = $$('#resultados .resultado'); if (!arts.length) return; e.preventDefault();
    let i = arts.findIndex(a => a.classList.contains('foco')); arts.forEach(a => a.classList.remove('foco'));
    i = e.key === 'ArrowDown' ? Math.min(arts.length - 1, i + 1) : Math.max(0, i - 1); arts[i].classList.add('foco'); arts[i].scrollIntoView({ block: 'nearest' });
  }
  if (e.key === 'Enter' && $('#resultados .resultado.foco') && document.activeElement.tagName !== 'INPUT') { const a = $('#resultados .resultado.foco'); const r = itensAtuais.find(x => String(x.pagina_id) === a.dataset.id); if (r) abrirDocumento(r.documento_id, r.pagina); }
});

async function renderPainel() {
  const [t, uf, vm, dm, pf, pt] = await Promise.all(['total', 'ativosPorUf', 'valorMedioCausas', 'duracaoMedia', 'porFase', 'porTribunal'].map(p => api('/api/home/' + p, {})));
  const tab = (titulo, arr, k) => `<div class="kpi"><div class="l">${titulo}</div><table class="tabela">${arr.map(x => `<tr><td>${esc(x[k] ?? '—')}</td><td>${x.quantidade}</td></tr>`).join('') || '<tr><td>—</td></tr>'}</table></div>`;
  $('#painel').innerHTML = `<div class="kpi"><div class="n">${t.processos}</div><div class="l">processos na base</div></div><div class="kpi"><div class="n">${t.documentos}</div><div class="l">documentos</div></div><div class="kpi"><div class="n">${t.paginas}</div><div class="l">páginas indexadas</div></div>
    <div class="kpi"><div class="n">${brl(vm.valorMedio)}</div><div class="l">valor médio das causas</div></div><div class="kpi"><div class="n">${dm.dias == null ? '—' : Math.round(dm.dias) + ' dias'}</div><div class="l">duração média</div></div>
    ${tab('Ativos por UF', uf, 'uf')}${tab('Por fase', pf, 'fase')}${tab('Por tribunal', pt, 'tribunal')}`;
}

// -------------------------------------------------------------- fontes de dados reais
async function statusFontes() {
  const s = await api('/api/fontes/status');
  $('#statusFontes').innerHTML = `<b>DJEN / Comunica PJe (CNJ):</b> ✅ público, sem chave (busca por nome de parte e advogado)<br>
    <b>DataJud (CNJ):</b> ${s.datajud ? '✅ chave configurada' : '⚠️ DATAJUD_API_KEY ausente no .env — copie a chave pública em <a href="https://datajud-wiki.cnj.jus.br/api-publica/acesso/" target="_blank">datajud-wiki.cnj.jus.br/api-publica/acesso</a>'}<br>
    <b>Judit:</b> ${s.judit ? '✅ configurado' : '— não configurado'} &nbsp; <b>Escavador:</b> ${s.escavador ? '✅ configurado' : '— não configurado'}<br>
    <b>Pasta de documentos:</b> <code>${esc(s.pastaDocumentos)}</code>`;
  $('#dj_tribunal').innerHTML = s.tribunais.map(t => `<option>${t}</option>`).join('');
  $('#dj2_trib').innerHTML = '<option value="">Todos os trabalhistas</option>' + (s.tribunaisDjen || []).map(t => `<option>${t}</option>`).join('');
  $('#idx_pasta').placeholder = s.pastaDocumentos;
}
let pollTimer = null;
async function acompanharTarefas() {
  clearTimeout(pollTimer);
  try {
    const ts = await api('/api/tarefas');
    const ativas = ts.filter(t => t.status === 'executando');
    const topo = $('#tarefasTopo');
    if (ativas.length) {
      const t = ativas[0]; const pct = t.total ? Math.round(100 * t.feito / t.total) : 0;
      topo.classList.remove('oculto'); $('#tarefaTxt').textContent = `${t.descricao} — ${t.total ? pct + '%' : t.feito} ${t.mensagem ? '· ' + t.mensagem : ''}`; $('#tarefaProg').style.width = (t.total ? pct : 30) + '%';
    } else topo.classList.add('oculto');
    if (!$('#view-fontes').classList.contains('oculto')) {
      $('#listaTarefas').innerHTML = ts.slice(0, 10).map(t => `<div class="tarefa"><div><div>${esc(t.descricao)} <small>${esc(t.inicio)}</small></div><small>${esc(t.mensagem || '')} ${t.erro ? '· ' + esc(t.erro) : ''}</small>${t.resultado ? `<pre class="saida">${esc(JSON.stringify(t.resultado, null, 1))}</pre>` : ''}</div><div><span class="st ${t.status}">${t.status}</span><div class="barra-prog"><div style="width:${t.total ? Math.round(100 * t.feito / t.total) : (t.status === 'executando' ? 30 : 100)}%"></div></div></div></div>`).join('') || '—';
    }
    const versao = (opcoes.versao ?? -1);
    if (ativas.length) { pollTimer = setTimeout(acompanharTarefas, 1500); if (Date.now() - (window._ultRefresh || 0) > 4000) { window._ultRefresh = Date.now(); carregarOpcoes(); buscar(); } }
    else if (window._haviaAtivas) { window._haviaAtivas = false; carregarOpcoes(); buscar(); toast('Tarefa concluída — índice atualizado'); }
    window._haviaAtivas = !!ativas.length;
  } catch (e) { pollTimer = setTimeout(acompanharTarefas, 5000); }
}
const run = async (btn, out, fn) => {
  btn.disabled = true; out.textContent = 'Iniciando…';
  try { const j = await fn(); out.textContent = j.id ? `Tarefa ${j.id} iniciada em segundo plano: ${j.descricao}. Acompanhe o progresso acima e na lista de tarefas.` : JSON.stringify(j, null, 2); acompanharTarefas(); }
  catch (e) { out.textContent = 'Erro: ' + e.message; }
  btn.disabled = false;
};
$('#dj_btnNumeros').onclick = () => run($('#dj_btnNumeros'), $('#dj_outNumeros'), () => api('/api/fontes/datajud/numero', { numeros: $('#dj_numeros').value.split(/\n/).map(s => s.trim()).filter(Boolean) }));
$('#dj_btnFiltro').onclick = () => run($('#dj_btnFiltro'), $('#dj_outFiltro'), () => api('/api/fontes/datajud/filtro', { tribunal: $('#dj_tribunal').value, classeCodigo: Number($('#dj_classe').value) || null, assuntoCodigo: Number($('#dj_assunto').value) || null, orgaoCodigo: Number($('#dj_orgao').value) || null, grau: $('#dj_grau').value || null, dataInicio: $('#dj_ini').value || null, dataFim: $('#dj_fim').value || null, maximo: Number($('#dj_max').value) || 200 }));
$('#dj2_btn').onclick = () => run($('#dj2_btn'), $('#dj2_out'), () => api('/api/fontes/djen', { nomeParte: $('#dj2_parte').value, nomeAdvogado: $('#dj2_adv').value, numeroOab: $('#dj2_oab').value, ufOab: $('#dj2_uf').value, numeroProcesso: $('#dj2_num').value, tribunal: $('#dj2_trib').value, dataInicio: $('#dj2_ini').value, dataFim: $('#dj2_fim').value, meio: $('#dj2_meio').value, maximo: Number($('#dj2_max').value) || 300, somenteTrabalhista: $('#dj2_trab').checked }));
$('#pp_btn').onclick = () => run($('#pp_btn'), $('#pp_out'), () => api('/api/fontes/pessoa', { provedor: $('#pp_provedor').value, tipo: $('#pp_tipo').value, chave: $('#pp_chave').value }));
$('#idx_btn').onclick = () => run($('#idx_btn'), $('#idx_out'), () => api('/api/indexar', { pasta: $('#idx_pasta').value || $('#idx_pasta').placeholder, reindexar: $('#idx_reindex').checked }));
$('#up_btn').onclick = () => run($('#up_btn'), $('#idx_out'), async () => { const fd = new FormData(); [...$('#up_files').files].forEach(f => fd.append('arquivos', f)); const n = $('#up_numero').value.trim(); const r = await fetch('/api/upload' + (n ? '?numeroProcesso=' + encodeURIComponent(n) : ''), { method: 'POST', body: fd }); if (!r.ok) throw new Error(await r.text()); return r.json(); });

// -------------------------------------------------------------- início
(async () => {
  atualizarFavCount(); await carregarOpcoes(); carregarFiltrosSalvos(); acompanharTarefas(); setInterval(acompanharTarefas, 8000);
  if (location.hash) { try { const h = JSON.parse(decodeURIComponent(location.hash.slice(1))); if (h.doc) abrirDocumento(h.doc, h.pag); else if (h.c) aplicarConsulta(h.c); } catch (e) {} }
  buscar();
})();
