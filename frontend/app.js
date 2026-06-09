/* ============================================================
   MeetIQ — Frontend Application Logic
   Three tabs: Submit Meeting | Query | Dashboard
   ============================================================ */

'use strict';

const API = window.location.protocol.startsWith('http')
  ? (window.location.port === '8000' ? window.location.origin : `${window.location.protocol}//${window.location.hostname}:8000`)
  : 'http://localhost:8000';

/* ── State ─────────────────────────────────────────────────── */
let _allTasks    = [];
let _allEsc      = [];
let _allRisks    = [];
let _queryHistory = [];

/* ════════════════════════════════════════════════════════════
   TAB ROUTING
   ════════════════════════════════════════════════════════════ */
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => {
    const active = t.dataset.tab === name;
    t.classList.toggle('active', active);
    t.setAttribute('aria-selected', active);
  });
  document.querySelectorAll('.panel').forEach(p => {
    p.classList.toggle('active', p.id === `panel-${name}`);
    p.classList.toggle('hidden', p.id !== `panel-${name}`);
  });
  if (name === 'dashboard') loadDashboard();
}

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => switchTab(tab.dataset.tab));
});

/* ════════════════════════════════════════════════════════════
   API CLIENT
   ════════════════════════════════════════════════════════════ */
async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  });
  if (res.status === 204) return null;
  const json = await res.json();
  if (!res.ok) throw new Error(json.detail || `HTTP ${res.status}`);
  return json;
}

/* ── Health check ─────────────────────────────────────────── */
async function checkHealth() {
  const dot   = document.querySelector('.dot');
  const label = document.getElementById('api-label');
  try {
    const d = await api('/health');
    dot.className  = 'dot ok';
    label.textContent = 'API Connected';
  } catch {
    dot.className  = 'dot err';
    label.textContent = 'API Offline';
  }
}

/* ════════════════════════════════════════════════════════════
   TAB 1 — SUBMIT MEETING
   ════════════════════════════════════════════════════════════ */
async function submitMeeting() {
  const text    = document.getElementById('transcript').value.trim();
  const title   = document.getElementById('meeting-title').value.trim() || null;
  const saveDb  = document.getElementById('save-db').value === 'true';

  if (!text) { toast('Please paste a meeting transcript first.', 'err'); return; }

  setLoading('extract-btn', 'extract-label', 'extract-spinner', true, 'Extracting…');

  try {
    const result = await api('/api/extract/', {
      method: 'POST',
      body: JSON.stringify({ text, title, save_to_db: saveDb }),
    });

    renderExtractionResults(result);
    toast(
      `Extracted ${result.counts.tasks} tasks, ${result.counts.escalations} escalations, ` +
      `${result.counts.risks} risks, ${result.counts.decisions} decisions.`,
      'ok'
    );
  } catch (e) {
    toast(e.message, 'err');
  } finally {
    setLoading('extract-btn', 'extract-label', 'extract-spinner', false, '⚡ Extract Intelligence');
  }
}

function clearForm() {
  document.getElementById('transcript').value      = '';
  document.getElementById('meeting-title').value   = '';
  document.getElementById('results-area').classList.add('hidden');
}

/* ── Render extraction results ────────────────────────────── */
function renderExtractionResults(r) {
  const area = document.getElementById('results-area');
  area.classList.remove('hidden');

  // Summary
  const summBox = document.getElementById('summary-box');
  if (r.summary) {
    summBox.textContent = r.summary;
    summBox.classList.remove('hidden');
  } else {
    summBox.classList.add('hidden');
  }

  // Badge counts
  document.getElementById('r-tasks-count').textContent       = r.counts.tasks;
  document.getElementById('r-escalations-count').textContent = r.counts.escalations;
  document.getElementById('r-risks-count').textContent       = r.counts.risks;
  document.getElementById('r-decisions-count').textContent   = r.counts.decisions;

  // Panels
  document.getElementById('r-tasks').innerHTML       = renderTaskCards(r.tasks);
  document.getElementById('r-escalations').innerHTML = renderEscCards(r.escalations);
  document.getElementById('r-risks').innerHTML       = renderRiskCards(r.risks);
  document.getElementById('r-decisions').innerHTML   = renderDecisionCards(r.decisions);

  // Wire result sub-tabs
  document.querySelectorAll('.rtab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.rtab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.result-panel').forEach(p => {
        const show = p.id === btn.dataset.rtab;
        p.classList.toggle('rpanel-active', show);
        p.classList.toggle('hidden', !show);
      });
    });
  });

  area.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ════════════════════════════════════════════════════════════
   TAB 2 — QUERY
   ════════════════════════════════════════════════════════════ */
function setQuery(text) {
  document.getElementById('query-input').value = text;
  document.getElementById('query-input').focus();
}

async function askQuery() {
  const question = document.getElementById('query-input').value.trim();
  if (!question) { toast('Please type a question first.', 'err'); return; }

  setLoading('query-btn', 'query-label', 'query-spinner', true, '…');

  const answerBox = document.getElementById('query-answer');
  answerBox.classList.add('hidden');

  try {
    const res = await api('/api/query/', {
      method: 'POST',
      body: JSON.stringify({ question }),
    });

    // Show answer
    document.getElementById('answer-text').textContent = res.answer;
    answerBox.classList.remove('hidden');

    // Sources
    const srcEl = document.getElementById('answer-sources');
    if (res.sources && res.sources.length) {
      srcEl.textContent = `📎 Sources: ${res.sources.join(' · ')}`;
      srcEl.classList.remove('hidden');
    } else {
      srcEl.classList.add('hidden');
    }

    // Save to history
    _queryHistory.unshift({ question, answer: res.answer, sources: res.sources });
    renderHistory();
    document.getElementById('query-input').value = '';

  } catch (e) {
    toast(e.message, 'err');
  } finally {
    setLoading('query-btn', 'query-label', 'query-spinner', false, 'Ask');
  }
}

function renderHistory() {
  const container = document.getElementById('query-history');
  const list      = document.getElementById('history-list');
  if (!_queryHistory.length) { container.classList.add('hidden'); return; }
  container.classList.remove('hidden');

  // Only show previous entries (skip index 0 which is the live answer)
  const prev = _queryHistory.slice(1);
  if (!prev.length) { container.classList.add('hidden'); return; }

  list.innerHTML = prev.map((h, i) => `
    <div class="history-item" onclick="restoreHistory(${i + 1})">
      <div class="history-q">❓ ${esc(h.question)}</div>
      <div class="history-a">${esc(h.answer.slice(0, 180))}${h.answer.length > 180 ? '…' : ''}</div>
    </div>
  `).join('');
}

function restoreHistory(idx) {
  const h = _queryHistory[idx];
  document.getElementById('answer-text').textContent = h.answer;
  document.getElementById('query-answer').classList.remove('hidden');
  const srcEl = document.getElementById('answer-sources');
  if (h.sources && h.sources.length) {
    srcEl.textContent = `📎 Sources: ${h.sources.join(' · ')}`;
    srcEl.classList.remove('hidden');
  } else { srcEl.classList.add('hidden'); }
}

/* ════════════════════════════════════════════════════════════
   TAB 3 — DASHBOARD
   ════════════════════════════════════════════════════════════ */
async function loadDashboard() {
  showSkeletons();
  try {
    const [stats, tasks, esc, risks] = await Promise.all([
      api('/api/stats/'),
      api('/api/tasks'),
      api('/api/escalations'),
      api('/api/risks'),
    ]);

    // Stats strip
    document.querySelector('#stat-meetings .stat-num').textContent = stats.total_meetings;
    document.querySelector('#stat-tasks .stat-num').textContent    = stats.total_tasks;
    document.querySelector('#stat-esc .stat-num').textContent      = stats.total_escalations;
    document.querySelector('#stat-risks .stat-num').textContent    = stats.total_risks;
    document.querySelector('#stat-dec .stat-num').textContent      = stats.total_decisions;

    // Store for filtering
    _allTasks = tasks;
    _allEsc   = esc;
    _allRisks = risks;

    renderDashboard(_allTasks, _allEsc, _allRisks);
  } catch (e) {
    toast(e.message, 'err');
    showError();
  }
}

function applyFilters() {
  const owner    = document.getElementById('filter-owner').value.trim().toLowerCase();
  const status   = document.getElementById('filter-status').value;
  const priority = document.getElementById('filter-priority').value;

  const fTasks = _allTasks.filter(t =>
    (!owner    || (t.owner || '').toLowerCase().includes(owner)) &&
    (!status   || t.status === status) &&
    (!priority || t.priority === priority)
  );
  const fEsc = _allEsc.filter(e =>
    (!owner    || (e.owner || '').toLowerCase().includes(owner)) &&
    (!status   || e.status === status) &&
    (!priority || e.severity === priority)
  );
  const fRisks = _allRisks.filter(r =>
    (!owner    || (r.owner || '').toLowerCase().includes(owner)) &&
    (!priority || r.impact === priority)
  );

  renderDashboard(fTasks, fEsc, fRisks);
}

function clearFilters() {
  document.getElementById('filter-owner').value    = '';
  document.getElementById('filter-status').value   = '';
  document.getElementById('filter-priority').value = '';
  renderDashboard(_allTasks, _allEsc, _allRisks);
}

function renderDashboard(tasks, esc, risks) {
  document.getElementById('tasks-total').textContent   = `${tasks.length} items`;
  document.getElementById('esc-total').textContent     = `${esc.length} items`;
  document.getElementById('risks-total').textContent   = `${risks.length} items`;

  document.getElementById('tasks-list').innerHTML  = renderTaskCards(tasks, true);
  document.getElementById('esc-list').innerHTML    = renderEscCards(esc, true);
  document.getElementById('risks-list').innerHTML  = renderRiskCards(risks, false);
}

function showSkeletons() {
  ['tasks-list','esc-list','risks-list'].forEach(id => {
    document.getElementById(id).innerHTML = '<div class="skeleton-row"></div>';
  });
}
function showError() {
  ['tasks-list','esc-list','risks-list'].forEach(id => {
    document.getElementById(id).innerHTML = '<div class="empty-state">Failed to load data. Is the API running?</div>';
  });
}

/* ── Status update (tasks) ────────────────────────────────── */
async function updateTaskStatus(id, value) {
  try {
    await api(`/api/items/tasks/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: value }),
    });
    // Update in local state
    const t = _allTasks.find(t => t.id === id);
    if (t) t.status = value;
    toast('Task updated', 'ok');
  } catch (e) { toast(e.message, 'err'); }
}

async function updateEscStatus(id, value) {
  try {
    await api(`/api/items/escalations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: value }),
    });
    const e = _allEsc.find(e => e.id === id);
    if (e) e.status = value;
    toast('Escalation updated', 'ok');
  } catch (e) { toast(e.message, 'err'); }
}

/* ════════════════════════════════════════════════════════════
   CARD RENDERERS
   ════════════════════════════════════════════════════════════ */
function renderTaskCards(tasks, editable = false) {
  if (!tasks || !tasks.length) return emptyState('No tasks found.');
  return `<div class="cards-grid">${tasks.map(t => `
    <div class="item-card">
      <div class="item-top">
        <div class="item-desc">${esc(t.description)}</div>
        <div style="display:flex;gap:6px;align-items:center;flex-shrink:0">
          ${prioBadge(t.priority)}
          ${editable && t.id && !t.id.startsWith('preview')
            ? `<select class="status-select" onchange="updateTaskStatus('${t.id}', this.value)">
                 ${statusOptions(t.status, ['open','in_progress','done','cancelled'])}
               </select>`
            : statusBadge(t.status)
          }
        </div>
      </div>
      <div class="item-meta">
        ${t.owner    ? `<span class="meta-tag">👤 ${esc(t.owner)}</span>` : ''}
        ${t.deadline ? `<span class="meta-tag">📅 ${esc(t.deadline)}</span>` : ''}
      </div>
    </div>
  `).join('')}</div>`;
}

function renderEscCards(list, editable = false) {
  if (!list || !list.length) return emptyState('No escalations found.');
  return `<div class="cards-grid">${list.map(e => `
    <div class="item-card">
      <div class="item-top">
        <div class="item-desc">${esc(e.description)}</div>
        <div style="display:flex;gap:6px;align-items:center;flex-shrink:0">
          ${sevBadge(e.severity)}
          ${editable && e.id && !e.id.startsWith('preview')
            ? `<select class="status-select" onchange="updateEscStatus('${e.id}', this.value)">
                 ${statusOptions(e.status, ['open','acknowledged','resolved'])}
               </select>`
            : statusBadge(e.status)
          }
        </div>
      </div>
      <div class="item-meta">
        ${e.owner    ? `<span class="meta-tag">👤 ${esc(e.owner)}</span>` : ''}
        ${e.due_date ? `<span class="meta-tag">📅 ${esc(e.due_date)}</span>` : ''}
      </div>
    </div>
  `).join('')}</div>`;
}

function renderRiskCards(list) {
  if (!list || !list.length) return emptyState('No risks found.');
  return `<div class="cards-grid">${list.map(r => `
    <div class="item-card">
      <div class="item-top">
        <div class="item-desc">${esc(r.description)}</div>
        <div style="display:flex;gap:6px;flex-shrink:0">
          ${impactBadge(r.impact)}
          <span class="badge badge-${r.likelihood}">🎲 ${cap(r.likelihood)}</span>
        </div>
      </div>
      <div class="item-meta">
        ${r.owner ? `<span class="meta-tag">👤 ${esc(r.owner)}</span>` : ''}
      </div>
      ${r.mitigation ? `<div class="item-mitigation">🛡 ${esc(r.mitigation)}</div>` : ''}
    </div>
  `).join('')}</div>`;
}

function renderDecisionCards(list) {
  if (!list || !list.length) return emptyState('No decisions found.');
  return `<div class="cards-grid">${list.map(d => `
    <div class="item-card">
      <div class="item-desc" style="margin-bottom:8px">${esc(d.description)}</div>
      <div class="item-meta">
        ${d.made_by    ? `<span class="meta-tag">👤 ${esc(d.made_by)}</span>` : ''}
        ${d.decided_at ? `<span class="meta-tag">📅 ${esc(d.decided_at)}</span>` : ''}
      </div>
      ${d.rationale ? `<div class="item-mitigation">💬 ${esc(d.rationale)}</div>` : ''}
    </div>
  `).join('')}</div>`;
}

/* ── Badge helpers ────────────────────────────────────────── */
const _STATUS_LABELS = {
  open: 'Open', in_progress: 'In Progress', done: 'Done',
  cancelled: 'Cancelled', acknowledged: 'Acknowledged', resolved: 'Resolved',
};
const _STATUS_DOTS = {
  open: '🔵', in_progress: '🟣', done: '🟢',
  cancelled: '⚫', acknowledged: '🟡', resolved: '🟢',
};

function statusBadge(s) {
  const label = _STATUS_LABELS[s] || cap(s);
  const dot   = _STATUS_DOTS[s]   || '⚪';
  return `<span class="badge badge-${s}">${dot} ${label}</span>`;
}
function prioBadge(p)   { return `<span class="badge badge-${p}">🔥 ${cap(p)}</span>`; }
function sevBadge(s)    { return `<span class="badge badge-${s}">⚡ ${cap(s)}</span>`; }
function impactBadge(i) { return `<span class="badge badge-${i}">💥 ${cap(i)}</span>`; }

function statusOptions(current, opts) {
  return opts.map(o =>
    `<option value="${o}" ${o === current ? 'selected' : ''}>${_STATUS_LABELS[o] || cap(o)}</option>`
  ).join('');
}

function emptyState(msg) {
  return `<div class="empty-state">${msg}</div>`;
}

/* ════════════════════════════════════════════════════════════
   UTILITIES
   ════════════════════════════════════════════════════════════ */
function esc(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function cap(s) {
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1).replace('_', ' ');
}
function setLoading(btnId, labelId, spinnerId, loading, labelText) {
  const btn = document.getElementById(btnId);
  btn.disabled = loading;
  document.getElementById(labelId).textContent = labelText;
  document.getElementById(spinnerId).classList.toggle('hidden', !loading);
}
function toast(msg, type = 'inf') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

/* ════════════════════════════════════════════════════════════
   INIT
   ════════════════════════════════════════════════════════════ */
checkHealth();
// Pre-load dashboard data in the background so it's instant when user clicks
api('/api/tasks').then(d => _allTasks = d || []).catch(() => {});
api('/api/escalations').then(d => _allEsc   = d || []).catch(() => {});
api('/api/risks').then(d => _allRisks = d || []).catch(() => {});
