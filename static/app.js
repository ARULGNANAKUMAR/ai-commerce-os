/**
 * app.js
 * ──────
 * Shared client-side core used by every authenticated page
 * (dashboard.html, settings.html) and referenced by auth.js.
 *
 * Responsibilities:
 *   - Token storage (access + refresh) in localStorage
 *   - apiFetch(): a fetch wrapper that attaches the access token,
 *     unwraps the { success, data, error } envelope from utils.py,
 *     and transparently refreshes an expired access token once
 *     before failing.
 *   - requireAuth(): the client-side route guard for protected pages
 *   - Small render/format helpers shared across dashboard + settings
 *
 * Everything is namespaced under `window.ACOS` so page-level <script>
 * blocks stay small and declarative.
 */

(function () {
  const ACCESS_TOKEN_KEY = 'acos_access_token';
  const REFRESH_TOKEN_KEY = 'acos_refresh_token';

  // ── Token storage ────────────────────────────────────────────

  function getAccessToken() {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  }

  function getRefreshToken() {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  }

  function setTokens({ access_token, refresh_token }) {
    if (access_token) localStorage.setItem(ACCESS_TOKEN_KEY, access_token);
    if (refresh_token) localStorage.setItem(REFRESH_TOKEN_KEY, refresh_token);
  }

  function clearTokens() {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  }

  // ── Authenticated fetch wrapper ──────────────────────────────

  async function apiFetch(url, options = {}) {
    const { method = 'GET', body, skipAuth = false, _retried = false } = options;

    const headers = { 'Content-Type': 'application/json' };
    if (!skipAuth) {
      const token = getAccessToken();
      if (token) headers['Authorization'] = `Bearer ${token}`;
    }

    const res = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    let payload;
    try {
      payload = await res.json();
    } catch (e) {
      throw new Error('Unexpected response from server.');
    }

    if (res.ok) {
      return payload;
    }

    const errCode = payload?.error?.code;

    // Access token expired mid-session — refresh once, then retry the
    // original call transparently so the caller never has to know.
    if (errCode === 'TOKEN_EXPIRED' && !skipAuth && !_retried) {
      const refreshed = await tryRefreshAccessToken();
      if (refreshed) {
        return apiFetch(url, { ...options, _retried: true });
      }
    }

    const error = new Error(payload?.error?.message || 'Something went wrong.');
    error.code = errCode;
    error.status = res.status;
    throw error;
  }

  async function tryRefreshAccessToken() {
    const refreshToken = getRefreshToken();
    if (!refreshToken) return false;
    try {
      const res = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return false;
      const payload = await res.json();
      setTokens({ access_token: payload.data.access_token });
      return true;
    } catch (e) {
      return false;
    }
  }

  // ── Route guard for protected pages ──────────────────────────

  async function requireAuth() {
    if (!getAccessToken()) {
      window.location.href = '/login';
      return null;
    }
    try {
      const res = await apiFetch('/api/merchant/profile');
      return res.data;
    } catch (err) {
      clearTokens();
      window.location.href = '/login';
      return null;
    }
  }

  // ── Sidebar user card ─────────────────────────────────────────

  function renderSidebarUser(profile) {
    const name = profile.merchant?.merchant_name || profile.user.email.split('@')[0];
    const initials = name.trim().split(/\s+/).map(p => p[0]).slice(0, 2).join('').toUpperCase();
    const nameEl = document.getElementById('sidebar-user-name');
    const emailEl = document.getElementById('sidebar-user-email');
    const avatarEl = document.getElementById('sidebar-avatar');
    if (nameEl) nameEl.textContent = name;
    if (emailEl) emailEl.textContent = profile.user.email;
    if (avatarEl) avatarEl.textContent = initials || '?';
  }

  // ── Logout ───────────────────────────────────────────────────

  function wireLogout() {
    const btn = document.getElementById('logout-btn');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      try {
        await apiFetch('/api/auth/logout', { method: 'POST', body: { refresh_token: getRefreshToken() } });
      } catch (e) {
        // Even if the network call fails, clear local tokens so the
        // user isn't stuck "logged in" on a client that can't reach the API.
      }
      clearTokens();
      window.location.href = '/login';
    });
  }

  // ── Mobile sidebar toggle ────────────────────────────────────

  function wireMobileSidebar() {
    const menuBtn = document.getElementById('mobile-menu-btn');
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    if (!menuBtn || !sidebar) return;

    const open = () => { sidebar.classList.add('open'); backdrop.classList.add('open'); };
    const close = () => { sidebar.classList.remove('open'); backdrop.classList.remove('open'); };

    menuBtn.addEventListener('click', open);
    backdrop.addEventListener('click', close);
  }

  // ── Formatting helpers ───────────────────────────────────────

  const ACTION_LABELS = {
    signup: 'Account created',
    login: 'Logged in',
    logout: 'Logged out',
    email_verified: 'Email verified',
    profile_updated: 'Profile updated',
    password_reset_requested: 'Password reset requested',
    password_reset_completed: 'Password changed',
    // Phase 2
    product_created:          'Product created',
    product_updated:          'Product updated',
    product_deleted:          'Product deactivated',
    product_imported:         'Products imported',
    ai_provider_connected:    'AI provider connected',
    ai_provider_disconnected: 'AI provider disconnected',
    ai_provider_tested:       'AI connection tested',
    ai_key_updated:           'AI key updated',
    permission_updated:       'Permission updated',
    // Phase 3
    workflow_created:         'Agent workflow created',
    workflow_updated:         'Agent workflow saved',
    workflow_deleted:         'Agent workflow deleted',
    workflow_published:       'Agent workflow published',
    workflow_cloned:          'Agent workflow cloned',
    workflow_executed:        'Agent workflow executed',
    template_used:            'Template used to create agent',
    // Phase 4
    checkout_requested:       'Checkout requested',
    checkout_approved:        'Checkout approved',
    checkout_rejected:        'Checkout rejected',
    copilot_query:            'Asked merchant copilot',
  };

  function formatAction(action) {
    return ACTION_LABELS[action] || action.replace(/_/g, ' ');
  }

  function formatRelativeTime(isoString) {
    const then = new Date(isoString).getTime();
    const now = Date.now();
    const diffSec = Math.max(0, Math.floor((now - then) / 1000));

    if (diffSec < 60) return 'just now';
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return `${diffDay}d ago`;
    return new Date(isoString).toLocaleDateString();
  }

  function setLoading(button, isLoading, labelText) {
    if (!button) return;
    button.disabled = isLoading;
    if (isLoading) {
      button.dataset.originalLabel = button.innerHTML;
      button.innerHTML = `<span class="spinner"></span> Please wait…`;
    } else {
      button.innerHTML = button.dataset.originalLabel || `<span class="btn-label">${labelText || ''}</span>`;
    }
  }

  window.ACOS = {
    getAccessToken,
    getRefreshToken,
    setTokens,
    clearTokens,
    apiFetch,
    requireAuth,
    renderSidebarUser,
    wireLogout,
    wireMobileSidebar,
    formatAction,
    formatRelativeTime,
    setLoading,
  };
})();
