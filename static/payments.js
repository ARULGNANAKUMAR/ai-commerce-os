/**
 * payments.js — Razorpay Test Mode payment management page
 */
let currentOrderId = null;
let currentOrderPaid = false;

document.addEventListener('DOMContentLoaded', () => {
  ACOS.requireAuth().then(profile => {
    if (!profile) return;
    ACOS.renderSidebarUser(profile);
    ACOS.wireLogout(); ACOS.wireMobileSidebar();
    loadOrders(); loadWebhooks();
    wireButtons();

    // Pre-fill session from active chat session
    const stored = sessionStorage.getItem('acos_chat_session');
    if (stored) document.getElementById('session-input').value = stored;
  });
});

function wireButtons() {
  document.getElementById('create-order-btn').addEventListener('click', createOrder);
  document.getElementById('simulate-success-btn').addEventListener('click', simulateSuccess);
  document.getElementById('simulate-fail-btn').addEventListener('click', simulateFailure);
  document.getElementById('retry-btn').addEventListener('click', retryOrder);
  document.getElementById('refund-btn').addEventListener('click', refundOrder);
}

async function createOrder() {
  const sid = document.getElementById('session-input').value.trim();
  if (!sid) { showError('Enter a chat session ID.'); return; }
  const btn = document.getElementById('create-order-btn');
  ACOS.setLoading(btn, true, 'Create order');
  clearMessages();
  try {
    const res = await ACOS.apiFetch('/api/payments/create', { method: 'POST', body: { session_id: sid } });
    const d = res.data;
    currentOrderId = d.order_id;
    currentOrderPaid = false;
    document.getElementById('razorpay-order-id').textContent = `Order ID: ${d.order_id}  |  Razorpay: ${d.razorpay_order_id}  |  ₹${d.amount.toLocaleString('en-IN')}`;
    document.getElementById('order-created-card').hidden = false;
    document.getElementById('simulate-success-btn').disabled = false;
    document.getElementById('simulate-fail-btn').disabled = false;
    document.getElementById('retry-btn').disabled = true;
    document.getElementById('refund-btn').disabled = true;
    showSuccess(`Order created (Razorpay Test Mode). Razorpay order: ${d.razorpay_order_id}`);
    loadOrders();
  } catch (err) { showError(err.message || 'Order creation failed.'); }
  ACOS.setLoading(btn, false, 'Create order');
}

async function simulateSuccess() {
  if (!currentOrderId) return;
  const btn = document.getElementById('simulate-success-btn');
  ACOS.setLoading(btn, true, 'Simulate success');
  try {
    const res = await ACOS.apiFetch('/api/payments/simulate/capture', { method: 'POST', body: { order_id: currentOrderId } });
    currentOrderPaid = true;
    showSuccess('✅ Payment captured! (Simulated Razorpay Test Mode)');
    document.getElementById('simulate-success-btn').disabled = true;
    document.getElementById('simulate-fail-btn').disabled = true;
    document.getElementById('retry-btn').disabled = true;
    document.getElementById('refund-btn').disabled = false;
    loadOrders(); loadWebhooks();
  } catch (err) { showError(err.message); }
  ACOS.setLoading(btn, false, 'Simulate success');
}

async function simulateFailure() {
  if (!currentOrderId) return;
  const btn = document.getElementById('simulate-fail-btn');
  ACOS.setLoading(btn, true, 'Simulate failure');
  try {
    await ACOS.apiFetch('/api/payments/simulate/failure', { method: 'POST', body: { order_id: currentOrderId } });
    showError('❌ Payment failed (simulated). You can retry up to 3 times.');
    document.getElementById('retry-btn').disabled = false;
    loadOrders(); loadWebhooks();
  } catch (err) { showError(err.message); }
  ACOS.setLoading(btn, false, 'Simulate failure');
}

async function retryOrder() {
  if (!currentOrderId) return;
  const btn = document.getElementById('retry-btn');
  ACOS.setLoading(btn, true, 'Retry');
  try {
    const res = await ACOS.apiFetch('/api/payments/retry', { method: 'POST', body: { order_id: currentOrderId } });
    const d = res.data;
    document.getElementById('razorpay-order-id').textContent =
      `Order ID: ${currentOrderId}  |  New Razorpay: ${d.razorpay_order_id}  |  Attempt ${d.retry_count+1}/3`;
    showSuccess(`Retry attempt created. ${d.can_retry ? `${3-d.retry_count} attempts remaining.` : 'Max retries reached.'}`);
    document.getElementById('simulate-success-btn').disabled = false;
    document.getElementById('simulate-fail-btn').disabled = d.retry_count >= 3;
    document.getElementById('retry-btn').disabled = !d.can_retry;
    loadOrders();
  } catch (err) { showError(err.message); }
  ACOS.setLoading(btn, false, 'Retry');
}

async function refundOrder() {
  if (!currentOrderId || !currentOrderPaid) return;
  if (!confirm('Issue a full refund for this order? (Test Mode)')) return;
  const btn = document.getElementById('refund-btn');
  ACOS.setLoading(btn, true, 'Refund');
  try {
    await ACOS.apiFetch('/api/payments/refund', { method: 'POST', body: { order_id: currentOrderId } });
    showSuccess('↩️ Refund processed (Test Mode).');
    document.getElementById('refund-btn').disabled = true;
    loadOrders(); loadWebhooks();
  } catch (err) { showError(err.message); }
  ACOS.setLoading(btn, false, 'Refund');
}

async function loadOrders() {
  try {
    const res = await ACOS.apiFetch('/api/orders');
    const orders = res.data.orders;
    const tbody  = document.getElementById('orders-tbody');
    if (!orders.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="table-empty">No orders yet. Create one above.</td></tr>';
      return;
    }
    const statusColors = { paid:'badge-success', created:'badge-neutral', failed:'badge-danger', refunded:'badge-warning', signature_failed:'badge-danger' };
    tbody.innerHTML = orders.map(o => `<tr>
      <td><code class="sku-code">${o.id.slice(-8)}</code></td>
      <td>₹${(o.amount||0).toLocaleString('en-IN')}</td>
      <td><span class="badge ${statusColors[o.status]||'badge-neutral'}">${o.status}</span></td>
      <td>${o.retry_count||0}</td>
      <td>${o.created_at ? ACOS.formatRelativeTime(o.created_at) : '—'}</td>
      <td><button class="btn btn-secondary btn-sm" onclick="selectOrder('${o.id}','${o.status}')">Select</button></td>
    </tr>`).join('');
  } catch (e) {}
}

function selectOrder(id, status) {
  currentOrderId = id;
  currentOrderPaid = status === 'paid';
  document.getElementById('order-created-card').hidden = false;
  document.getElementById('razorpay-order-id').textContent = `Selected order: ${id} (${status})`;
  document.getElementById('simulate-success-btn').disabled = status === 'paid';
  document.getElementById('simulate-fail-btn').disabled = status === 'paid';
  document.getElementById('retry-btn').disabled = status !== 'failed';
  document.getElementById('refund-btn').disabled = status !== 'paid';
}

async function loadWebhooks() {
  try {
    const res   = await ACOS.apiFetch('/api/payments/webhooks');
    const hooks = res.data.webhooks;
    const el    = document.getElementById('webhook-list');
    if (!hooks.length) {
      el.innerHTML = '<div class="empty-state" style="padding:var(--space-4)"><p>No webhooks yet — they appear after payment events.</p></div>';
      return;
    }
    const statusColors = { delivered:'badge-success', failed:'badge-danger', no_endpoint:'badge-neutral', received:'badge-warning' };
    el.innerHTML = hooks.map(w => `
      <div class="activity-row">
        <span class="badge ${statusColors[w.status]||'badge-neutral'}">${w.status}</span>
        <span class="activity-action">${esc(w.event)}</span>
        ${w.error ? `<span style="font-size:11px;color:var(--color-danger)">${esc(w.error.slice(0,60))}</span>` : ''}
        <span class="activity-time">${ACOS.formatRelativeTime(w.created_at)}</span>
      </div>`).join('');
  } catch (e) {}
}

function showError(msg)   { const e=document.getElementById('page-error');   e.textContent=msg; e.hidden=false; }
function showSuccess(msg) { const e=document.getElementById('page-success'); e.textContent=msg; e.hidden=false; setTimeout(()=>e.hidden=true,5000); }
function clearMessages()  { document.getElementById('page-error').hidden=true; document.getElementById('page-success').hidden=true; }
function esc(s) { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }
