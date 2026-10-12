/* Legal Research Local — frontend (vanilla JS) */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const LIMITE = 30;
let deslocamento = 0, ultimoTotal = 0, opcoes = {};

const api = async (url, body, method) => {
  const r = await fetch(url, { method: method || (body ? 'POST' : 'GET'), headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
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

async function buscar(reset = true) {
  if (reset) deslocamento = 0;
  const q = montarConsulta();
  location.hash = encodeURIComponent(JSON.stringify({ q: $('#q').value, c: q }));
  $('#resultados').innerHTML = '<p class="meta">Buscando…</p>';
  try {
    const [r, m] = await Promise.all([api(`/api/documento?limite=${LIMITE}&deslocamento=${deslocamento}`, q), api('/api/documento/obterMenuLateral', q)]);
    ultimoTotal = r.totalTrechos;
    $('#contagem').innerHTML = `<b>${r.totalProcessos.toLocaleString('pt-BR')}</b> processos · <b>${r.totalDocumentos.toLocaleString('pt-BR')}</b> documentos · <b>${r.totalTrechos.toLocaleString('pt-BR')}</b> trechos`;
    $('#juriN').textContent = r.totalProcessos.toLocaleString('pt-BR');
    renderResultados(r.resultados, $('#resultados'));
    renderFacetas(m);
    const pag = Math.floor(deslocamento / LIMITE) + 1, tot = Math.max(1, Math.ceil(ultimoTotal / LIMITE));
    $('#pagInfo').textContent = `página ${pag} de ${tot}`;
    $('#prev').disabled = deslocamento === 0; $('#next').disabled = deslocamento + LIMITE >= ultimoTotal;
  } catch (e) { $('#resultados').innerHTML = `<p class="meta">Erro: ${esc(e.message)}</p>`; }
}

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
$$('.tab').forEach(b => b.onclick = () => { $$('.tab').forEach(x => x.classList.remove('ativo')); b.classList.add('ativo'); $$('.view').forEach(v => v.classList.add('oculto')); $('#view-' + b.dataset.view).classList.remove('oculto'); if (b.dataset.view === 'favoritos') renderFavoritos(); if (b.dataset.view === 'painel') renderPainel(); if (b.dataset.view === 'fontes') statusFontes(); });
$('#formBusca').onsubmit = e => { e.preventDefault(); buscar(); };
$('#btnAplicar').onclick = () => buscar();
$('#ordem').onchange = () => buscar();
$('#prev').onclick = () => { deslocamento = Math.max(0, deslocamento - LIMITE); buscar(false); };
$('#next').onclick = () => { deslocamento += LIMITE; buscar(false); };

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
  $('#statusFontes').innerHTML = `<b>DataJud (CNJ):</b> ${s.datajud ? '✅ chave configurada' : '⚠️ DATAJUD_API_KEY ausente no .env — copie a chave pública em <a href="https://datajud-wiki.cnj.jus.br/api-publica/acesso/" target="_blank">datajud-wiki.cnj.jus.br/api-publica/acesso</a>'}<br>
    <b>Judit:</b> ${s.judit ? '✅ configurado' : '— não configurado'} &nbsp; <b>Escavador:</b> ${s.escavador ? '✅ configurado' : '— não configurado'}<br>
    <b>Pasta de documentos:</b> <code>${esc(s.pastaDocumentos)}</code>`;
  $('#dj_tribunal').innerHTML = s.tribunais.map(t => `<option>${t}</option>`).join('');
  $('#idx_pasta').placeholder = s.pastaDocumentos;
}
const run = async (btn, out, fn) => { btn.disabled = true; out.textContent = 'Processando…'; try { out.textContent = JSON.stringify(await fn(), null, 2); carregarOpcoes(); } catch (e) { out.textContent = 'Erro: ' + e.message; } btn.disabled = false; };
$('#dj_btnNumeros').onclick = () => run($('#dj_btnNumeros'), $('#dj_outNumeros'), () => api('/api/fontes/datajud/numero', { numeros: $('#dj_numeros').value.split(/\n/).map(s => s.trim()).filter(Boolean) }));
$('#dj_btnFiltro').onclick = () => run($('#dj_btnFiltro'), $('#dj_outFiltro'), () => api('/api/fontes/datajud/filtro', { tribunal: $('#dj_tribunal').value, classeCodigo: Number($('#dj_classe').value) || null, assuntoCodigo: Number($('#dj_assunto').value) || null, orgaoCodigo: Number($('#dj_orgao').value) || null, grau: $('#dj_grau').value || null, dataInicio: $('#dj_ini').value || null, dataFim: $('#dj_fim').value || null, maximo: Number($('#dj_max').value) || 200 }));
$('#pp_btn').onclick = () => run($('#pp_btn'), $('#pp_out'), () => api('/api/fontes/pessoa', { provedor: $('#pp_provedor').value, tipo: $('#pp_tipo').value, chave: $('#pp_chave').value }));
$('#idx_btn').onclick = () => run($('#idx_btn'), $('#idx_out'), () => api('/api/indexar', { pasta: $('#idx_pasta').value || $('#idx_pasta').placeholder, reindexar: $('#idx_reindex').checked }));
$('#up_btn').onclick = () => run($('#up_btn'), $('#idx_out'), async () => { const fd = new FormData(); [...$('#up_files').files].forEach(f => fd.append('arquivos', f)); const n = $('#up_numero').value.trim(); const r = await fetch('/api/upload' + (n ? '?numeroProcesso=' + encodeURIComponent(n) : ''), { method: 'POST', body: fd }); if (!r.ok) throw new Error(await r.text()); return r.json(); });

// -------------------------------------------------------------- início
(async () => {
  atualizarFavCount(); await carregarOpcoes(); carregarFiltrosSalvos();
  if (location.hash) { try { const h = JSON.parse(decodeURIComponent(location.hash.slice(1))); if (h.doc) abrirDocumento(h.doc, h.pag); else if (h.c) aplicarConsulta(h.c); } catch (e) {} }
  buscar();
})();
