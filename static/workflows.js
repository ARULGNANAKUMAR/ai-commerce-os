/**
 * workflows.js — My Agents list page
 */
document.addEventListener('DOMContentLoaded', () => {
  ACOS.requireAuth().then(async profile => {
    if (!profile) return;
    ACOS.renderSidebarUser(profile);
    ACOS.wireLogout();
    ACOS.wireMobileSidebar();
    await loadWorkflows();
  });
});

async function loadWorkflows() {
  const grid = document.getElementById('wf-grid');
  try {
    const res = await ACOS.apiFetch('/api/workflows');
    const workflows = res.data.workflows;

    if (!workflows.length) {
      grid.innerHTML = `
        <div class="empty-state" style="grid-column:1/-1">
          <div class="empty-state-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="6" height="6" rx="1"/><rect x="15" y="3" width="6" height="6" rx="1"/><rect x="9" y="15" width="6" height="6" rx="1"/><path d="M6 9v3a3 3 0 003 3h6a3 3 0 003-3V9"/></svg>
          </div>
          <h4>No agents yet</h4>
          <p>Build your first AI shopping agent visually, or start from a template.</p>
          <div style="display:flex;gap:8px;justify-content:center;margin-top:var(--space-4)">
            <a class="btn btn-primary btn-sm" href="/builder">+ New agent</a>
            <a class="btn btn-secondary btn-sm" href="/templates">Browse templates</a>
          </div>
        </div>`;
      return;
    }

    grid.innerHTML = workflows.map(w => `
      <div class="wf-card">
        <div class="wf-card-header">
          <span style="font-size:24px">🤖</span>
          ${statusBadge(w.status)}
        </div>
        <div class="wf-card-name">${esc(w.name)}</div>
        <div class="wf-card-meta">${esc(w.description) || 'No description'}</div>
        <div class="wf-card-stats">
          <span class="wf-stat">🔗 ${w.node_count} nodes</span>
          <span class="wf-stat">v${w.version}</span>
          <span class="wf-stat">${ACOS.formatRelativeTime(w.updated_at)}</span>
        </div>
        <div class="wf-card-actions">
          <a class="btn btn-primary btn-sm" href="/builder/${w.id}">Edit</a>
          <button class="btn btn-secondary btn-sm" data-action="clone" data-id="${w.id}">Clone</button>
          <button class="btn btn-danger-ghost btn-sm" data-action="delete" data-id="${w.id}">Delete</button>
        </div>
      </div>`).join('');

    grid.querySelectorAll('[data-action="clone"]').forEach(btn =>
      btn.addEventListener('click', () => cloneWorkflow(btn.dataset.id)));
    grid.querySelectorAll('[data-action="delete"]').forEach(btn =>
      btn.addEventListener('click', () => deleteWorkflow(btn.dataset.id)));

  } catch (err) {
    document.getElementById('page-error').textContent = err.message || 'Failed to load agents.';
    document.getElementById('page-error').hidden = false;
    grid.innerHTML = '';
  }
}

async function cloneWorkflow(id) {
  try {
    await ACOS.apiFetch(`/api/workflows/${id}/clone`, { method: 'POST', body: {} });
    loadWorkflows();
  } catch (err) {
    alert('Clone failed: ' + (err.message || 'Unknown error'));
  }
}

async function deleteWorkflow(id) {
  if (!confirm('Delete this agent? This cannot be undone.')) return;
  try {
    await ACOS.apiFetch(`/api/workflows/${id}`, { method: 'DELETE' });
    loadWorkflows();
  } catch (err) {
    alert('Delete failed: ' + (err.message || 'Unknown error'));
  }
}

function statusBadge(status) {
  const map = { draft: 'badge-neutral', published: 'badge-success', archived: 'badge-warning' };
  return `<span class="badge ${map[status] || 'badge-neutral'}" style="margin-left:auto">${status}</span>`;
}
function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
