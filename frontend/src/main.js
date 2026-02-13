const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const MOLECULOIDS_BASE = import.meta.env.VITE_MOLECULOIDS_URL || 'http://localhost:8001';

let state = {
  datasetId: null,
  family: null,
  seed: null,
  molecules: [],
  total: 0,
  selectedMolecule: null,
  sceneId: null,
};

function el(id) {
  return document.getElementById(id);
}

function renderApp() {
  const app = el('app');
  if (!app) return;
  app.innerHTML = `
    <header>
      <img src="/logo.png" alt="First Tracks Materials" />
      <h1>Molecule Explorer</h1>
    </header>
    <div class="select-dataset">
      <label>Dataset: </label>
      <select id="datasetSelect"></select>
    </div>
    <div class="breadcrumb" id="breadcrumb"></div>
    <div class="grid">
      <div class="card" id="familiesCard" style="display:none">
        <h2>Families</h2>
        <div class="families" id="families"></div>
      </div>
      <div class="card" id="seedsCard" style="display:none">
        <h2>Seeds</h2>
        <div class="seeds" id="seeds"></div>
      </div>
    </div>
    <div class="card" id="moleculesCard" style="display:none">
      <h2>Molecules <span id="totalCount"></span></h2>
      <div id="moleculesTableWrap"></div>
    </div>
    <div id="detailPanel" class="detail-panel" style="display:none"></div>
  `;
  bindDatasetSelect();
  loadDatasets();
}

async function loadDatasets() {
  const select = el('datasetSelect');
  try {
    const r = await fetch(`${API_BASE}/datasets`);
    const data = await r.json();
    select.innerHTML = '<option value="">-- Select dataset --</option>' +
      data.datasets.map(d => `<option value="${d.dataset_id}">${d.name || d.dataset_id} (${d.molecule_count || 0})</option>`).join('');
    select.addEventListener('change', () => {
      state.datasetId = select.value || null;
      state.family = null;
      state.seed = null;
      state.molecules = [];
      state.selectedMolecule = null;
      onDatasetChange();
    });
  } catch (e) {
    select.innerHTML = '<option value="">Failed to load datasets</option>';
    console.error(e);
  }
}

function bindDatasetSelect() {
  const select = el('datasetSelect');
  if (select && !select.dataset.bound) {
    select.dataset.bound = true;
  }
}

async function onDatasetChange() {
  if (!state.datasetId) {
    el('breadcrumb').innerHTML = '';
    el('familiesCard').style.display = 'none';
    el('seedsCard').style.display = 'none';
    el('moleculesCard').style.display = 'none';
    el('detailPanel').style.display = 'none';
    return;
  }
  el('breadcrumb').innerHTML = `<span data-step="dataset">${state.datasetId}</span>`;
  const bc = el('breadcrumb');
  bc.querySelector('[data-step="dataset"]').onclick = () => { state.family = null; state.seed = null; loadFamilies(); loadMolecules(); };
  await loadFamilies();
}

async function loadFamilies() {
  if (!state.datasetId) return;
  try {
    const r = await fetch(`${API_BASE}/datasets/${state.datasetId}/families`);
    const data = await r.json();
    const card = el('familiesCard');
    const div = el('families');
    card.style.display = 'block';
    div.innerHTML = data.families.length
      ? data.families.map(f => `<button type="button" data-family="${f}">${f}</button>`).join('')
      : '<span class="loading">No families</span>';
    div.querySelectorAll('button').forEach(btn => {
      btn.onclick = () => {
        state.family = btn.dataset.family;
        state.seed = null;
        div.querySelectorAll('button').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        loadSeeds();
        loadMolecules();
      };
    });
  } catch (e) {
    el('families').innerHTML = '<span class="error">Failed to load families</span>';
  }
  el('seedsCard').style.display = 'none';
  el('seeds').innerHTML = '';
}

async function loadSeeds() {
  if (!state.datasetId) return;
  const card = el('seedsCard');
  card.style.display = 'block';
  el('seeds').innerHTML = '<span class="loading">Loading seeds…</span>';
  try {
    const url = state.family
      ? `${API_BASE}/datasets/${state.datasetId}/seeds?family=${encodeURIComponent(state.family)}`
      : `${API_BASE}/datasets/${state.datasetId}/seeds`;
    const r = await fetch(url);
    const data = await r.json();
    const div = el('seeds');
    div.innerHTML = data.seeds.length
      ? data.seeds.map(s => `<button type="button" data-seed="${(s.discovery_seed || '').replace(/"/g, '&quot;')}">${s.seed_name || s.discovery_seed || '—'}</button>`).join('')
      : '<span class="loading">No seeds</span>';
    div.querySelectorAll('button').forEach(btn => {
      btn.onclick = () => {
        state.seed = btn.dataset.seed;
        div.querySelectorAll('button').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        loadMolecules();
      };
    });
  } catch (e) {
    el('seeds').innerHTML = '<span class="error">Failed to load seeds</span>';
  }
}

async function loadMolecules() {
  if (!state.datasetId) return;
  const card = el('moleculesCard');
  card.style.display = 'block';
  el('moleculesTableWrap').innerHTML = '<span class="loading">Loading molecules…</span>';
  try {
    const body = {
      page: { limit: 100, offset: 0 },
      seed_name: state.family || undefined,
    };
    const r = await fetch(`${API_BASE}/datasets/${state.datasetId}/molecules/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    state.molecules = data.molecules || [];
    state.total = data.total ?? state.molecules.length;
    renderMoleculesTable();
    el('totalCount').textContent = `(${state.total})`;
  } catch (e) {
    el('moleculesTableWrap').innerHTML = '<span class="error">Failed to load molecules</span>';
  }
}

function renderMoleculesTable() {
  const wrap = el('moleculesTableWrap');
  if (!state.molecules.length) {
    wrap.innerHTML = '<span class="loading">No molecules</span>';
    return;
  }
  wrap.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>CID</th>
          <th>Name</th>
          <th>Formula</th>
          <th>MW</th>
          <th>Method</th>
        </tr>
      </thead>
      <tbody>
        ${state.molecules.map(m => `
          <tr data-cid="${m.cid}">
            <td>${m.cid}</td>
            <td>${(m.name || '—').slice(0, 40)}</td>
            <td>${m.molecular_formula || '—'}</td>
            <td>${m.molecular_weight != null ? m.molecular_weight.toFixed(1) : '—'}</td>
            <td>${m.discovery_method || '—'}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
  wrap.querySelectorAll('tr[data-cid]').forEach(tr => {
    tr.onclick = () => selectMolecule(parseInt(tr.dataset.cid, 10));
  });
}

async function selectMolecule(cid) {
  state.selectedMolecule = cid;
  const panel = el('detailPanel');
  panel.style.display = 'block';
  panel.innerHTML = '<span class="loading">Loading detail…</span>';
  try {
    const r = await fetch(`${API_BASE}/datasets/${state.datasetId}/molecules/${cid}`);
    const mol = await r.json();
    panel.innerHTML = `
      <h3>Molecule ${cid}</h3>
      <dl>
        <dt>Name</dt><dd>${mol.name || '—'}</dd>
        <dt>Formula</dt><dd>${mol.molecular_formula || '—'}</dd>
        <dt>MW</dt><dd>${mol.molecular_weight != null ? mol.molecular_weight.toFixed(2) : '—'}</dd>
        <dt>SMILES</dt><dd>${mol.smiles || '—'}</dd>
        <dt>InChI Key</dt><dd>${mol.inchi_key || '—'}</dd>
        <dt>Discovery</dt><dd>${mol.discovery_method || '—'} / ${mol.discovery_seed || '—'}</dd>
      </dl>
      <div class="viewer-wrap" id="viewerWrap">
        <span class="loading">Loading 3D…</span>
      </div>
    `;
    loadViewer(cid);
  } catch (e) {
    panel.innerHTML = `<span class="error">Failed to load molecule: ${e.message}</span>`;
  }
}

async function loadViewer(cid) {
  const wrap = el('viewerWrap');
  if (!wrap) return;
  try {
    const geomR = await fetch(`${API_BASE}/datasets/${state.datasetId}/molecules/${cid}/geometry?format=moleculoids_json`);
    if (!geomR.ok) {
      wrap.innerHTML = '<span class="loading">No geometry for this molecule</span>';
      return;
    }
    const sceneJson = await geomR.json();
    const postR = await fetch(`${MOLECULOIDS_BASE}/scenes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sceneJson),
    });
    if (!postR.ok) {
      wrap.innerHTML = '<span class="loading">Moleculoids server unavailable. Start it with: moleculoids serve --port 8001</span>';
      return;
    }
    const { id: sceneId } = await postR.json();
    wrap.innerHTML = `<moleculoids-viewer scene="${MOLECULOIDS_BASE}/scenes/${sceneId}" theme="dark"></moleculoids-viewer>`;
    const script = document.createElement('script');
    script.type = 'module';
    script.src = `${MOLECULOIDS_BASE}/static/assets/index.js`;
    script.onerror = () => {
      wrap.innerHTML = '<span class="loading">Load Moleculoids viewer from ' + MOLECULOIDS_BASE + '</span>';
    };
    document.head.appendChild(script);
  } catch (e) {
    wrap.innerHTML = `<span class="error">Viewer error: ${e.message}</span>`;
  }
}

renderApp();
