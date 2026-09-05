/**
 * permissions.js — Capability permissions page
 * Depends on app.js (ACOS namespace).
 */
(function () {
  const FINANCIAL_CAPS = new Set(['payment_request', 'refund_request']);

  document.addEventListener('DOMContentLoaded', () => {
    ACOS.requireAuth().then(profile => {
      if (!profile) return;
      ACOS.renderSidebarUser(profile);
      ACOS.wireLogout();
      ACOS.wireMobileSidebar();
      loadPermissions();
      wireTestPanel();
    });
  });

  // ── Load & render ────────────────────────────────────────────────

  async function loadPermissions() {
    try {
      const res  = await ACOS.apiFetch('/api/permissions');
      const caps = res.data.permissions;
      renderCapabilities(caps);
      populateTestSelector(caps);
    } catch (err) {
      q('capabilities-container').innerHTML =
        `<div class="banner banner-error">${err.message || 'Failed to load permissions.'}</div>`;
    }
  }

  function renderCapabilities(caps) {
    const groups = {};
    caps.forEach(c => {
      if (!groups[c.category]) groups[c.category] = [];
      groups[c.category].push(c);
    });

    const categoryLabels = { information: 'Information', sales: 'Sales', financial: 'Financial', advanced: 'Advanced' };
    const container = q('capabilities-container');
    container.innerHTML = '';

    for (const [cat, items] of Object.entries(groups)) {
      const section = document.createElement('div');
      section.className = 'card section-card';
      section.style.marginBottom = 'var(--space-4)';
      section.innerHTML = `
        <div class="section-card-header">
          <h3>${categoryLabels[cat] || cat} capabilities</h3>
          ${cat === 'financial' ? `<span class="badge badge-warning">Requires limits</span>` : ''}
        </div>`;

      items.forEach(cap => {
        const row = document.createElement('div');
        row.className = 'capability-row';
        row.dataset.capability = cap.capability;
        row.innerHTML = `
          <div class="cap-info">
            <div class="cap-name">${esc(cap.label)}</div>
            <div class="cap-desc">${esc(cap.description)}</div>
          </div>
          <div class="cap-controls">
            ${cap.has_limits && cap.enabled ? renderLimitControls(cap) : ''}
            <label class="toggle-switch" title="${cap.enabled ? 'Enabled' : 'Disabled'}">
              <input type="checkbox" class="cap-toggle" data-cap="${cap.capability}" ${cap.enabled ? 'checked' : ''}>
              <span class="toggle-slider"></span>
            </label>
          </div>`;
        section.appendChild(row);
      });

      container.appendChild(section);
    }

    // Wire all toggles
    container.querySelectorAll('.cap-toggle').forEach(toggle => {
      toggle.addEventListener('change', () => handleToggle(toggle));
    });

    // Wire limit inputs (financial caps)
    container.querySelectorAll('.limit-input').forEach(input => {
      input.addEventListener('change', () => saveLimit(input));
    });
    container.querySelectorAll('.approval-toggle').forEach(chk => {
      chk.addEventListener('change', () => saveLimit(chk));
    });
  }

  function renderLimitControls(cap) {
    const lim = cap.limits || {};
    return `
      <div class="limit-controls">
        <label class="limit-label">Max amount (₹)</label>
        <input type="number" class="limit-input" data-cap="${cap.capability}"
               data-field="max_amount" min="0" step="100" value="${lim.max_amount ?? 2000}">
        <label class="approval-label">
          <input type="checkbox" class="approval-toggle" data-cap="${cap.capability}"
                 ${lim.approval_required !== false ? 'checked' : ''}>
          Require approval
        </label>
      </div>`;
  }

  // ── Toggle handler ────────────────────────────────────────────────

  async function handleToggle(toggleEl) {
    const cap     = toggleEl.dataset.cap;
    const enabled = toggleEl.checked;
    const row     = toggleEl.closest('.capability-row');
    toggleEl.disabled = true;

    try {
      const body = { enabled };
      // Send current limit values if this is a financial capability
      if (FINANCIAL_CAPS.has(cap)) {
        const maxInput = row.querySelector(`.limit-input[data-cap="${cap}"]`);
        const approvalChk = row.querySelector(`.approval-toggle[data-cap="${cap}"]`);
        if (maxInput || approvalChk) {
          body.limits = {};
          if (maxInput)   body.limits.max_amount = parseFloat(maxInput.value) || 2000;
          if (approvalChk) body.limits.approval_required = approvalChk.checked;
        }
      }
      await ACOS.apiFetch(`/api/permissions/${cap}`, { method: 'PUT', body });

      // If enabling a financial cap, show limit controls; if disabling, hide them
      const existingLimits = row.querySelector('.limit-controls');
      if (enabled && FINANCIAL_CAPS.has(cap) && !existingLimits) {
        const capsData = await ACOS.apiFetch('/api/permissions');
        const capInfo  = capsData.data.permissions.find(p => p.capability === cap);
        if (capInfo) {
          const controls = document.createElement('div');
          controls.innerHTML = renderLimitControls(capInfo);
          row.querySelector('.cap-controls').prepend(controls.firstElementChild);
          row.querySelectorAll('.limit-input').forEach(i => i.addEventListener('change', () => saveLimit(i)));
          row.querySelectorAll('.approval-toggle').forEach(c => c.addEventListener('change', () => saveLimit(c)));
        }
      } else if (!enabled && existingLimits) {
        existingLimits.remove();
      }

      showSuccess(`${cap.replace(/_/g,' ')} ${enabled ? 'enabled' : 'disabled'}.`);
    } catch (err) {
      toggleEl.checked = !enabled; // revert
      showError(err.message || 'Could not update permission.');
    } finally {
      toggleEl.disabled = false;
    }
  }

  async function saveLimit(inputEl) {
    const cap = inputEl.dataset.cap;
    const row = inputEl.closest('.capability-row');
    const maxInput  = row.querySelector(`.limit-input[data-cap="${cap}"]`);
    const approvalChk = row.querySelector(`.approval-toggle[data-cap="${cap}"]`);
    const toggleChk   = row.querySelector(`.cap-toggle[data-cap="${cap}"]`);

    try {
      await ACOS.apiFetch(`/api/permissions/${cap}`, { method: 'PUT', body: {
        enabled: toggleChk ? toggleChk.checked : true,
        limits: {
          max_amount: maxInput ? parseFloat(maxInput.value) || 0 : undefined,
          approval_required: approvalChk ? approvalChk.checked : undefined,
        },
      }});
      showSuccess('Limit updated.');
    } catch (err) {
      showError(err.message || 'Could not update limit.');
    }
  }

  // ── Sandbox tester ────────────────────────────────────────────────

  function populateTestSelector(caps) {
    const sel = q('test-capability');
    sel.innerHTML = '<option value="">Select capability…</option>' +
      caps.map(c => `<option value="${c.capability}">${c.label}</option>`).join('');
  }

  function wireTestPanel() {
    q('test-capability').addEventListener('change', function() {
      q('test-amount-field').hidden = !FINANCIAL_CAPS.has(this.value);
      q('permission-decision').hidden = true;
    });
    q('test-check-btn').addEventListener('click', runPermissionCheck);
  }

  async function runPermissionCheck() {
    const cap    = q('test-capability').value;
    if (!cap) return;
    const amount = q('test-amount').value;
    const body   = { capability: cap };
    if (FINANCIAL_CAPS.has(cap) && amount) body.context = { amount: parseFloat(amount) };

    try {
      const res = await ACOS.apiFetch('/api/permissions/check', { method: 'POST', body });
      const d   = res.data;
      const decisionMap = {
        ALLOW:             { cls: 'decision-allow',    icon: '✅', label: 'ALLOW' },
        DENY:              { cls: 'decision-deny',     icon: '🚫', label: 'DENY' },
        REQUIRES_APPROVAL: { cls: 'decision-approval', icon: '⏳', label: 'REQUIRES APPROVAL' },
        LIMIT_EXCEEDED:    { cls: 'decision-limit',    icon: '🔴', label: 'LIMIT EXCEEDED' },
      };
      const info = decisionMap[d.decision] || decisionMap.DENY;
      const decEl = q('permission-decision');
      decEl.className = `permission-decision ${info.cls}`;
      decEl.innerHTML = `<span class="decision-icon">${info.icon}</span><strong>${info.label}</strong>`;
      decEl.hidden = false;
    } catch (err) {
      showError(err.message || 'Check failed.');
    }
  }

  // ── Helpers ──────────────────────────────────────────────────────

  function q(id)    { return document.getElementById(id); }
  function esc(s)   { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
  function showError(msg)   { const e = q('page-error');   e.textContent = msg; e.hidden = false; q('page-success').hidden = true; }
  function showSuccess(msg) { const e = q('page-success'); e.textContent = msg; e.hidden = false; q('page-error').hidden = true; setTimeout(() => e.hidden = true, 3000); }
})();
