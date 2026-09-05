/**
 * auth.js
 * ───────
 * Form handling for login.html and signup.html. Depends on app.js
 * being loaded first (for ACOS.apiFetch / setTokens).
 */

(function () {
  const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

  function showFieldError(fieldId, show) {
    const field = document.getElementById(`field-${fieldId}`);
    if (!field) return;
    field.classList.toggle('has-error', show);
  }

  function showFormBanner(id, message) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = message;
    el.hidden = !message;
  }

  function isStrongPassword(password) {
    return password.length >= 8 && /[A-Za-z]/.test(password) && /[0-9]/.test(password);
  }

  // ── Login form ───────────────────────────────────────────────

  const loginForm = document.getElementById('login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      showFormBanner('form-error', '');

      const email = document.getElementById('email').value.trim();
      const password = document.getElementById('password').value;

      let valid = true;
      const emailOk = EMAIL_RE.test(email);
      showFieldError('email', !emailOk);
      if (!emailOk) valid = false;

      showFieldError('password', !password);
      if (!password) valid = false;

      if (!valid) return;

      const btn = document.getElementById('login-submit');
      ACOS.setLoading(btn, true, 'Log in');

      try {
        const res = await ACOS.apiFetch('/api/auth/login', {
          method: 'POST',
          skipAuth: true,
          body: { email, password },
        });
        ACOS.setTokens(res.data);
        window.location.href = '/dashboard';
      } catch (err) {
        showFormBanner('form-error', err.message || 'Could not log in.');
      } finally {
        ACOS.setLoading(btn, false, 'Log in');
      }
    });
  }

  // ── Forgot password (inline swap, no page navigation) ──────────

  const forgotLink = document.getElementById('forgot-password-link');
  if (forgotLink) {
    forgotLink.addEventListener('click', async (e) => {
      e.preventDefault();
      const email = document.getElementById('email').value.trim();
      if (!EMAIL_RE.test(email)) {
        showFieldError('email', true);
        showFormBanner('form-error', 'Enter your email above first, then click "Forgot password?" again.');
        return;
      }
      showFormBanner('form-error', '');
      forgotLink.textContent = 'Sending…';
      try {
        const res = await ACOS.apiFetch('/api/auth/forgot-password', {
          method: 'POST',
          skipAuth: true,
          body: { email },
        });
        showFormBanner('form-success', res.message);
      } catch (err) {
        showFormBanner('form-error', err.message || 'Could not send reset email.');
      } finally {
        forgotLink.textContent = 'Forgot password?';
      }
    });
  }

  // ── Signup form ──────────────────────────────────────────────

  const signupForm = document.getElementById('signup-form');
  if (signupForm) {
    signupForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      showFormBanner('form-error', '');

      const merchantName = document.getElementById('merchant_name').value.trim();
      const companyName = document.getElementById('company_name').value.trim();
      const phone = document.getElementById('phone').value.trim();
      const businessType = document.getElementById('business_type').value;
      const email = document.getElementById('email').value.trim();
      const password = document.getElementById('password').value;

      let valid = true;

      showFieldError('merchant_name', !merchantName);
      if (!merchantName) valid = false;

      const emailOk = EMAIL_RE.test(email);
      showFieldError('email', !emailOk);
      if (!emailOk) valid = false;

      const passwordOk = isStrongPassword(password);
      showFieldError('password', !passwordOk);
      if (!passwordOk) valid = false;

      if (!valid) return;

      const btn = document.getElementById('signup-submit');
      ACOS.setLoading(btn, true, 'Create account');

      try {
        const res = await ACOS.apiFetch('/api/auth/signup', {
          method: 'POST',
          skipAuth: true,
          body: {
            merchant_name: merchantName,
            company_name: companyName,
            phone,
            business_type: businessType,
            email,
            password,
          },
        });
        ACOS.setTokens(res.data);
        window.location.href = '/dashboard';
      } catch (err) {
        showFormBanner('form-error', err.message || 'Could not create your account.');
      } finally {
        ACOS.setLoading(btn, false, 'Create account');
      }
    });
  }
})();
