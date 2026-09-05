/**
 * compare.js — Product comparison page
 */
let selected = new Set();
let allProducts = [];

document.addEventListener('DOMContentLoaded', () => {
  ACOS.requireAuth().then(async profile => {
    if (!profile) return;
    ACOS.renderSidebarUser(profile);
    ACOS.wireLogout(); ACOS.wireMobileSidebar();
    await loadProducts();
    document.getElementById('compare-btn').addEventListener('click', runCompare);
  });
});

async function loadProducts() {
  try {
    const res = await ACOS.apiFetch('/api/products?limit=50');
    allProducts = res.data.products;
    const picker = document.getElementById('product-picker');
    if (!allProducts.length) {
      picker.innerHTML = '<p class="text-muted" style="font-size:13px">No products yet. <a href="/products">Add some first</a>.</p>';
      return;
    }
    picker.innerHTML = allProducts.map(p => `
      <button class="chat-lang-pill" type="button" data-id="${p.id}" style="padding:8px 14px">
        ${esc(p.name)} · ₹${(p.price||0).toLocaleString('en-IN')}
      </button>`).join('');
    picker.querySelectorAll('button[data-id]').forEach(btn => {
      btn.addEventListener('click', () => toggleSelect(btn));
    });
  } catch (err) {
    document.getElementById('page-error').textContent = err.message;
    document.getElementById('page-error').hidden = false;
  }
}

function toggleSelect(btn) {
  const id = btn.dataset.id;
  if (selected.has(id)) {
    selected.delete(id);
    btn.style.background = '';
    btn.style.color = '';
    btn.style.borderColor = '';
  } else {
    if (selected.size >= 6) return;
    selected.add(id);
    btn.style.background = 'var(--color-primary)';
    btn.style.color = '#fff';
    btn.style.borderColor = 'var(--color-primary)';
  }
  document.getElementById('selected-count').textContent = selected.size;
  document.getElementById('compare-btn').disabled = selected.size < 2;
}

async function runCompare() {
  const btn = document.getElementById('compare-btn');
  ACOS.setLoading(btn, true, 'Compare');
  document.getElementById('page-error').hidden = true;

  try {
    const res = await ACOS.apiFetch('/api/compare', { method: 'POST', body: { product_ids: [...selected] } });
    renderResult(res.data);
  } catch (err) {
    document.getElementById('page-error').textContent = err.message || 'Comparison failed.';
    document.getElementById('page-error').hidden = false;
  } finally {
    ACOS.setLoading(btn, false, `Compare selected (${selected.size})`);
  }
}

function renderResult(data) {
  document.getElementById('result-card').hidden = false;
  document.getElementById('summary-list').innerHTML = data.summary.map(s =>
    `<div class="analysis-suggestion" style="color:var(--color-text)">${esc(s)}</div>`).join('');

  const rows = data.products;
  const attrs = [
    { key: 'price', label: 'Price', fmt: v => v != null ? `₹${v.toLocaleString('en-IN')}` : 'N/A' },
    { key: 'rating', label: 'Rating', fmt: (v, r) => v != null ? `${v}/5 <span style="color:var(--color-text-faint);font-size:10px">(est.)</span>` : 'N/A' },
    { key: 'stock', label: 'Stock', fmt: v => v != null ? `${v} units` : 'N/A' },
    { key: 'discount', label: 'Discount', fmt: v => v ? `${v}% off` : 'None' },
    { key: 'delivery_estimate', label: 'Delivery', fmt: v => v || 'N/A' },
    { key: 'features', label: 'Features', fmt: v => (v && v.length) ? v.join(', ') : 'N/A' },
    { key: 'specifications', label: 'Specifications', fmt: v => {
      if (!v || Object.keys(v).length === 0 || v.note) return 'No specifications provided';
      return Object.entries(v).map(([k,val]) => `${k}: ${val}`).join(', ');
    }},
  ];

  const table = document.getElementById('compare-table');
  table.innerHTML = `
    <thead><tr><th></th>${rows.map(r => `<th class="compare-col-header">${esc(r.name)}</th>`).join('')}</tr></thead>
    <tbody>
      ${attrs.filter(a => rows[0][a.key] !== undefined).map(a => `
        <tr>
          <td>${a.label}</td>
          ${rows.map(r => `<td>${a.fmt(r[a.key], r)}</td>`).join('')}
        </tr>`).join('')}
    </tbody>`;
}

function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
