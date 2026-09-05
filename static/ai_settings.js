/**
 * ai_settings.js — AI Provider configuration page
 * Depends on app.js (ACOS namespace).
 */
(function () {
  let providerMeta = {};    // { gemini: { models, ... }, openai: { ... } }
  let currentConfig = null; // serialized provider from API (no key)

  document.addEventListener('DOMContentLoaded', () => {
    ACOS.requireAuth().then(profile => {
      if (!profile) return;
      ACOS.renderSidebarUser(profile);
      ACOS.wireLogout();
      ACOS.wireMobileSidebar();
      loadMeta().then(loadCurrentConfig);
      wireUI();
    });
  });

  // ── Data loading ─────────────────────────────────────────────────

  async function loadMeta() {
    try {
      const res = await ACOS.apiFetch('/api/ai/providers/meta');
      providerMeta = res.data.providers;
    } catch (e) { /* non-fatal */ }
  }

  async function loadCurrentConfig() {
    try {
      const res = await ACOS.apiFetch('/api/ai/providers');
      currentConfig = res.data.provider;
      renderCurrentConfig(currentConfig);
    } catch (e) { /* no provider yet */ }
  }

  function renderCurrentConfig(config) {
    const statusIcon  = q('status-icon');
    const statusLabel = q('status-label');
    const statusSub   = q('status-sub');
    const statusBadge = q('status-badge');
    const removeBtn   = q('remove-btn');
    const testBtn     = q('test-btn');
    const hintRow     = q('key-hint-display');
    const hintCode    = q('key-hint-code');

    if (!config) {
      statusLabel.textContent = 'No AI provider connected';
      statusSub.textContent   = 'Connect a provider below to enable the AI agent in Phase 3.';
      statusBadge.textContent = 'Not connected';
      statusBadge.className   = 'badge badge-neutral';
      statusIcon.style.color  = 'var(--color-text-faint)';
      removeBtn.hidden = true;
      testBtn.disabled = true;
      hintRow.hidden   = true;
      return;
    }

    // Populate form
    q('ai-provider').value = config.provider;
    populateModels(config.provider, config.model);
    hintCode.textContent = config.key_hint ? `...${config.key_hint}` : '????';
    hintRow.hidden = false;
    testBtn.disabled = false;
    removeBtn.hidden = false;

    // Status display
    const statusMap = {
      connected:    { label: 'Connected',     badge: 'badge-success', sub: `${providerLabel(config.provider)} · ${config.model}` },
      error:        { label: 'Connection error', badge: 'badge-warning', sub: 'Last test failed. Re-check your API key.' },
      disconnected: { label: 'Not tested yet',   badge: 'badge-neutral', sub: 'Click "Test connection" to verify your key.' },
    };
    const info = statusMap[config.status] || statusMap.disconnected;
    statusLabel.textContent = info.label;
    statusSub.textContent   = config.last_tested
      ? `${info.sub} · Tested ${ACOS.formatRelativeTime(config.last_tested)}`
      : info.sub;
    statusBadge.textContent = info.label;
    statusBadge.className   = `badge ${info.badge}`;
    statusIcon.style.color  = config.status === 'connected' ? 'var(--color-success)' : 'var(--color-text-faint)';
  }

  function populateModels(provider, selectedModel) {
    const sel = q('ai-model');
    const meta = providerMeta[provider];
    if (!meta) { sel.innerHTML = '<option value="">Unknown provider</option>'; sel.disabled = true; return; }
    sel.disabled = false;
    sel.innerHTML = meta.models.map(m =>
      `<option value="${m}"${m === (selectedModel || meta.default_model) ? ' selected' : ''}>${m}</option>`
    ).join('');
  }

  function providerLabel(pid) {
    return (providerMeta[pid] && providerMeta[pid].label) || pid;
  }

  // ── Save ────────────────────────────────────────────────────────

  async function saveProvider(e) {
    e.preventDefault();
    hideMessages();
    const provider = q('ai-provider').value;
    const model    = q('ai-model').value;
    const apiKey   = q('ai-key').value.trim();

    if (!provider) { showError('Select an AI provider.'); return; }
    if (!model)    { showError('Select a model.'); return; }
    if (!apiKey && !currentConfig) { showError('Enter your API key.'); return; }

    const payload = { provider, model };
    if (apiKey) payload.api_key = apiKey;
    else if (currentConfig) {
      // Re-saving without a new key: we still need to send the existing key.
      // Since we never store it client-side, prompt the user.
      showError('Enter your API key to save. We never store it in the browser.');
      return;
    }

    const btn = q('save-btn');
    ACOS.setLoading(btn, true, 'Save provider');

    try {
      const res = await ACOS.apiFetch('/api/ai/providers', { method: 'POST', body: payload });
      q('ai-key').value = ''; // clear from DOM immediately
      currentConfig = res.data.provider;
      renderCurrentConfig(currentConfig);
      showSuccess('Provider saved. Click "Test connection" to verify.');
    } catch (err) {
      showError(err.message || 'Could not save provider.');
    } finally {
      ACOS.setLoading(btn, false, 'Save provider');
    }
  }

  // ── Test ────────────────────────────────────────────────────────

  async function testConnection() {
    hideMessages();
    const btn = q('test-btn');
    ACOS.setLoading(btn, true, 'Test connection');
    q('test-result-card').hidden = true;

    try {
      const res = await ACOS.apiFetch('/api/ai/providers/test', { method: 'POST' });
      const d = res.data;
      currentConfig = { ...currentConfig, status: d.status, last_tested: new Date().toISOString() };
      renderCurrentConfig(currentConfig);

      q('test-result-body').innerHTML = d.success
        ? `<div class="banner banner-success" style="margin:0">${esc(d.message)}</div>`
        : `<div class="banner banner-error"   style="margin:0">${esc(d.message)}</div>`;
      q('test-result-card').hidden = false;
    } catch (err) {
      q('test-result-body').innerHTML = `<div class="banner banner-error" style="margin:0">${esc(err.message || 'Test failed.')}</div>`;
      q('test-result-card').hidden = false;
    } finally {
      ACOS.setLoading(btn, false, 'Test connection');
    }
  }

  // ── Remove ──────────────────────────────────────────────────────

  async function removeProvider() {
    if (!confirm('Disconnect the AI provider? This will disable AI agent capabilities.')) return;
    try {
      await ACOS.apiFetch('/api/ai/providers', { method: 'DELETE' });
      currentConfig = null;
      q('ai-provider').value = '';
      q('ai-model').innerHTML = '<option value="">Select provider first</option>';
      q('ai-model').disabled = true;
      q('ai-key').value = '';
      q('key-hint-display').hidden = true;
      q('test-result-card').hidden = true;
      renderCurrentConfig(null);
      showSuccess('AI provider disconnected.');
    } catch (err) {
      showError(err.message || 'Could not disconnect provider.');
    }
  }

  // ── Wire UI ──────────────────────────────────────────────────────

  function wireUI() {
    q('ai-form').addEventListener('submit', saveProvider);
    q('test-btn').addEventListener('click', testConnection);
    q('remove-btn').addEventListener('click', removeProvider);

    q('ai-provider').addEventListener('change', function () {
      populateModels(this.value, null);
      if (this.value) q('key-warning').hidden = false;
    });

    // Key visibility toggle
    q('key-toggle-btn').addEventListener('click', () => {
      const inp = q('ai-key');
      inp.type = inp.type === 'password' ? 'text' : 'password';
    });
  }

  // ── Helpers ──────────────────────────────────────────────────────

  function q(id)    { return document.getElementById(id); }
  function esc(s)   { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
  function showError(msg)   { const e = q('page-error');   e.textContent = msg; e.hidden = false; q('page-success').hidden = true; }
  function showSuccess(msg) { const e = q('page-success'); e.textContent = msg; e.hidden = false; q('page-error').hidden = true; setTimeout(() => e.hidden = true, 6000); }
  function hideMessages()   { q('page-error').hidden = q('page-success').hidden = true; }
})();
