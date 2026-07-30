
let all = [];
const $ = id => document.getElementById(id);
const local = JSON.parse(localStorage.getItem('radar-appalti-user') || '{}');

async function load() {
  try {
    const res = await fetch(`data/gare.json?v=${Date.now()}`);
    const payload = await res.json();
    all = payload.gare || [];
    $('lastUpdate').textContent = `Ultimo aggiornamento: ${payload.updated_at || 'non disponibile'}`;
    fillRegions();
    renderSources(payload.sources_status || []);
    render();
  } catch (e) {
    $('tbody').innerHTML = `<tr><td colspan="9" class="empty">Impossibile caricare data/gare.json</td></tr>`;
  }
}

function renderSources(items){
  const el=$('sourcesStatus');
  if(!items.length){el.textContent='Nessun controllo ancora eseguito.';return}
  el.innerHTML=items.map(x=>`<span class="source-pill ${x.ok?'source-ok':'source-ko'}" title="${esc(x.errore||'')}">${x.ok?'✓':'⚠'} ${esc(x.fonte)} (${x.trovate||0})</span>`).join(' ');
}
function fillRegions() {
  const values = [...new Set(all.map(x => x.regione).filter(Boolean))].sort();
  $('region').innerHTML = '<option value="">Tutte le regioni</option>' + values.map(x => `<option>${esc(x)}</option>`).join('');
}

function userState(id) {
  return local[id] || {preferito:false, stato:'Nuova'};
}

function saveState(id, patch) {
  local[id] = {...userState(id), ...patch};
  localStorage.setItem('radar-appalti-user', JSON.stringify(local));
  render();
}

function render() {
  const q = $('search').value.toLowerCase();
  const cat = $('category').value;
  const reg = $('region').value;
  const status = $('status').value;

  const filtered = all.filter(x => {
    const state = userState(x.id);
    return (!q || Object.values(x).join(' ').toLowerCase().includes(q))
      && (!cat || x.categoria === cat)
      && (!reg || x.regione === reg)
      && (!status || state.stato === status);
  });

  const active = all.filter(x => !['Scartata','Chiusa'].includes(userState(x.id).stato));
  $('total').textContent = active.length;
  $('newCount').textContent = active.filter(x => userState(x.id).stato === 'Nuova').length;
  $('urgent').textContent = active.filter(x => { const d=daysLeft(x.scadenza); return d !== null && d >= 0 && d <= 7 }).length;
  $('favorites').textContent = active.filter(x => userState(x.id).preferito).length;
  $('count').textContent = `${filtered.length} risultati`;

  $('tbody').innerHTML = filtered.length ? filtered.map(rowHtml).join('') :
    '<tr><td colspan="9" class="empty">Nessun risultato con i filtri selezionati.</td></tr>';
}

function rowHtml(x) {
  const state = userState(x.id);
  const days = daysLeft(x.scadenza);
  const cls = days !== null && days <= 3 ? 'urgent' : days !== null && days <= 7 ? 'soon' : 'ok';
  return `<tr>
    <td><button class="star ${state.preferito?'on':''}" onclick="saveState('${attr(x.id)}',{preferito:${!state.preferito}})">★</button></td>
    <td><div class="title">${esc(x.titolo)}</div><div class="entity">${esc(x.ente||'')}${x.regione?' · '+esc(x.regione):''}${x.cpv?' · CPV '+esc(x.cpv):''}</div></td>
    <td><span class="score">${esc(x.punteggio||0)}</span></td>
    <td><span class="tag">${esc(x.categoria||'Servizi')}</span></td>
    <td>${esc(x.pubblicazione||'–')}</td>
    <td class="deadline ${cls}">${esc(x.scadenza||'Da verificare')}${days!==null?`<div>${days} giorni</div>`:''}</td>
    <td>${x.importo ? '€ '+esc(x.importo) : '–'}</td>
    <td><select onchange="saveState('${attr(x.id)}',{stato:this.value})">
      ${['Nuova','In valutazione','Da segnalare','Scartata','Chiusa'].map(s=>`<option ${state.stato===s?'selected':''}>${s}</option>`).join('')}
    </select></td>
    <td>${x.url?`<a class="open" href="${attr(x.url)}" target="_blank" rel="noopener">Apri</a>`:''}</td>
  </tr>`;
}

function daysLeft(s) {
  const m = String(s||'').match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (!m) return null;
  const d = new Date(+m[3], +m[2]-1, +m[1], 23,59,59);
  return Math.ceil((d - new Date()) / 86400000);
}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function attr(s){return esc(s).replace(/`/g,'')}

['search','category','region','status'].forEach(id => $(id).addEventListener(id==='search'?'input':'change', render));

let deferredPrompt;
window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault(); deferredPrompt = e; $('installBtn').hidden = false;
});
$('installBtn').addEventListener('click', async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt(); await deferredPrompt.userChoice; deferredPrompt = null; $('installBtn').hidden = true;
});
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js');
load();
