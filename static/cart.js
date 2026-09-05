/**
 * cart.js — Cart management page (reads the active chat session's cart)
 */
let sessionId = null;

document.addEventListener('DOMContentLoaded', () => {
  ACOS.requireAuth().then(profile => {
    if (!profile) return;
    ACOS.renderSidebarUser(profile);
    ACOS.wireLogout(); ACOS.wireMobileSidebar();

    sessionId = sessionStorage.getItem('acos_chat_session');
    if (!sessionId) {
      document.getElementById('no-session-notice').hidden = false;
      return;
    }
    document.getElementById('cart-container').hidden = false;
    loadCart();
    document.getElementById('checkout-btn').addEventListener('click', requestCheckout);
  });
});

async function loadCart() {
  try {
    const res = await ACOS.apiFetch(`/api/cart/${sessionId}`);
    renderCart(res.data);
  } catch (err) {
    showError(err.message || 'Failed to load cart.');
  }
}

function renderCart(cart) {
  const itemsEl = document.getElementById('cart-items');
  if (!cart.items.length) {
    itemsEl.innerHTML = '<div class="empty-state"><h4>Cart is empty</h4><p>Add items from <a href="/chat">AI Shopping Chat</a>.</p></div>';
    document.getElementById('checkout-btn').disabled = true;
  } else {
    itemsEl.innerHTML = cart.items.map(i => `
      <div class="cart-item-row" data-pid="${i.product_id}">
        <div style="flex:1">
          <div class="cart-item-name">${esc(i.name)}</div>
          <div class="cart-item-price">₹${i.price.toLocaleString('en-IN')} each</div>
        </div>
        <div class="cart-qty-control">
          <button class="cart-qty-btn" data-action="dec">−</button>
          <span class="cart-qty-val">${i.quantity}</span>
          <button class="cart-qty-btn" data-action="inc">+</button>
        </div>
        <button class="btn btn-danger-ghost btn-sm" data-action="remove">Remove</button>
      </div>`).join('');
    document.getElementById('checkout-btn').disabled = false;

    itemsEl.querySelectorAll('.cart-item-row').forEach(row => {
      const pid = row.dataset.pid;
      row.querySelector('[data-action="inc"]').addEventListener('click', () => changeQty(pid, 1, row));
      row.querySelector('[data-action="dec"]').addEventListener('click', () => changeQty(pid, -1, row));
      row.querySelector('[data-action="remove"]').addEventListener('click', () => removeItem(pid));
    });
  }
  document.getElementById('summary-count').textContent = cart.item_count;
  document.getElementById('summary-total').textContent = `₹${cart.total.toLocaleString('en-IN')}`;
}

async function changeQty(pid, delta, row) {
  const valEl = row.querySelector('.cart-qty-val');
  const newQty = Math.max(0, parseInt(valEl.textContent) + delta);
  try {
    const res = await ACOS.apiFetch(`/api/cart/${sessionId}/items/${pid}`, { method: 'PUT', body: { quantity: newQty } });
    renderCart(res.data);
  } catch (err) { showError(err.message); }
}

async function removeItem(pid) {
  try {
    const res = await ACOS.apiFetch(`/api/cart/${sessionId}/items/${pid}`, { method: 'DELETE' });
    renderCart(res.data);
  } catch (err) { showError(err.message); }
}

async function requestCheckout() {
  const btn = document.getElementById('checkout-btn');
  ACOS.setLoading(btn, true, 'Request checkout approval');
  try {
    const res = await ACOS.apiFetch('/api/approval/request', { method: 'POST', body: { session_id: sessionId } });
    const a = res.data;
    const card = document.getElementById('approval-result-card');
    const statusMap = {
      approved: ['badge-success', 'Approved — ready for checkout!'],
      pending:  ['badge-warning', 'Pending merchant approval'],
      rejected: ['badge-danger', 'Rejected'],
    };
    const [cls, label] = statusMap[a.status] || ['badge-neutral', a.status];
    card.innerHTML = `
      <h3>Checkout request</h3>
      <p class="panel-desc">${esc(a.reason || '')}</p>
      <span class="badge ${cls}">${label}</span>
      <p style="margin-top:var(--space-3);font-size:13px">Amount: ₹${a.amount.toLocaleString('en-IN')}</p>
    `;
    card.hidden = false;
    showSuccess('Checkout request submitted.');
  } catch (err) {
    showError(err.message || 'Checkout request failed.');
  } finally {
    ACOS.setLoading(btn, false, 'Request checkout approval');
  }
}

function showError(msg)   { const e = document.getElementById('page-error');   e.textContent = msg; e.hidden = false; }
function showSuccess(msg) { const e = document.getElementById('page-success'); e.textContent = msg; e.hidden = false; setTimeout(()=>e.hidden=true, 3000); }
function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
