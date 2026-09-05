/**
 * products.js — Product catalog page logic
 * Depends on app.js (ACOS namespace).
 */
(function () {
  let currentPage = 1;
  let totalPages  = 1;
  let categories  = new Set();
  const searchDebounce = debounce(loadProducts, 350);

  // ── Boot ────────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', () => {
    ACOS.requireAuth().then(profile => {
      if (!profile) return;
      ACOS.renderSidebarUser(profile);
      ACOS.wireLogout();
      ACOS.wireMobileSidebar();
      loadProducts();
      wireUI();
    });
  });

  // ── Load / render ────────────────────────────────────────────────

  async function loadProducts(page) {
    if (page) currentPage = page;
    const params = new URLSearchParams({
      page:    currentPage,
      limit:   15,
      keyword: q('search-input').value.trim(),
      availability: q('filter-availability').value,
      category: q('filter-category').value,
    });

    try {
      const res = await ACOS.apiFetch(`/api/products?${params}`);
      renderTable(res.data.products);
      renderPagination(res.data.pagination);
      updateCategoryFilter(res.data.products);
    } catch (err) {
      showError(err.message || 'Failed to load products.');
    }
  }

  function renderTable(products) {
    const tbody = q('product-tbody');
    if (!products.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="table-empty">
        No products yet. <a href="#" id="empty-add-link">Add your first product</a> or import a catalog.
      </td></tr>`;
      const link = document.getElementById('empty-add-link');
      if (link) link.addEventListener('click', e => { e.preventDefault(); openAddModal(); });
      q('table-pagination').hidden = true;
      return;
    }
    tbody.innerHTML = products.map(p => `
      <tr data-id="${p.id}">
        <td>
          <div class="product-name">${esc(p.name)}</div>
          ${p.category ? `<div class="product-category">${esc(p.category)}</div>` : ''}
        </td>
        <td><code class="sku-code">${esc(p.sku) || '—'}</code></td>
        <td>₹${(+p.price).toLocaleString('en-IN', {minimumFractionDigits: 0})}
          ${p.discount > 0 ? `<span class="discount-tag">${p.discount}% off</span>` : ''}
        </td>
        <td>${p.stock}</td>
        <td>${availBadge(p.availability)}</td>
        <td>${statusBadge(p.status)}</td>
        <td class="row-actions">
          <button class="btn btn-secondary btn-sm" data-action="edit" data-id="${p.id}">Edit</button>
          <button class="btn btn-danger-ghost btn-sm" data-action="delete" data-id="${p.id}">Delete</button>
        </td>
      </tr>`).join('');

    tbody.querySelectorAll('[data-action="edit"]').forEach(btn =>
      btn.addEventListener('click', () => openEditModal(btn.dataset.id)));
    tbody.querySelectorAll('[data-action="delete"]').forEach(btn =>
      btn.addEventListener('click', () => deleteProduct(btn.dataset.id)));
  }

  function renderPagination(pg) {
    const wrap = q('table-pagination');
    if (pg.pages <= 1) { wrap.hidden = true; return; }
    wrap.hidden = false;
    totalPages  = pg.pages;
    q('pagination-info').textContent = `Page ${pg.page} of ${pg.pages} (${pg.total} products)`;
    q('prev-btn').disabled = pg.page <= 1;
    q('next-btn').disabled = pg.page >= pg.pages;
  }

  function updateCategoryFilter(products) {
    products.forEach(p => { if (p.category) categories.add(p.category); });
    const sel  = q('filter-category');
    const cur  = sel.value;
    const opts = ['<option value="">All categories</option>',
      ...[...categories].sort().map(c => `<option value="${c}"${c===cur?' selected':''}>${esc(c)}</option>`)];
    sel.innerHTML = opts.join('');
  }

  // ── Add / Edit modal ─────────────────────────────────────────────

  function openAddModal() {
    q('modal-title').textContent = 'Add product';
    q('product-form').reset();
    q('editing-product-id').value = '';
    q('modal-error').hidden = true;
    showModal('product-modal-backdrop');
  }

  async function openEditModal(id) {
    try {
      const res = await ACOS.apiFetch(`/api/products/${id}`);
      const p   = res.data.product;
      q('modal-title').textContent = 'Edit product';
      q('editing-product-id').value = p.id;
      q('p-name').value         = p.name;
      q('p-sku').value          = p.sku || '';
      q('p-description').value  = p.description || '';
      q('p-category').value     = p.category || '';
      q('p-brand').value        = p.brand || '';
      q('p-price').value        = p.price;
      q('p-discount').value     = p.discount || 0;
      q('p-stock').value        = p.stock;
      q('p-availability').value = p.availability;
      q('p-status').value       = p.status;
      q('p-tags').value         = (p.tags || []).join(', ');
      q('modal-error').hidden   = true;
      showModal('product-modal-backdrop');
    } catch (err) {
      showError(err.message);
    }
  }

  async function saveProduct(e) {
    e.preventDefault();
    const editId  = q('editing-product-id').value;
    const payload = {
      name:         q('p-name').value.trim(),
      sku:          q('p-sku').value.trim(),
      description:  q('p-description').value.trim(),
      category:     q('p-category').value.trim(),
      brand:        q('p-brand').value.trim(),
      price:        parseFloat(q('p-price').value) || 0,
      discount:     parseFloat(q('p-discount').value) || 0,
      stock:        parseInt(q('p-stock').value)   || 0,
      availability: q('p-availability').value,
      status:       q('p-status').value,
      tags:         q('p-tags').value.split(',').map(t => t.trim()).filter(Boolean),
    };

    const btn = q('modal-save-btn');
    ACOS.setLoading(btn, true, 'Save product');
    q('modal-error').hidden = true;

    try {
      if (editId) {
        await ACOS.apiFetch(`/api/products/${editId}`, { method: 'PUT', body: payload });
      } else {
        await ACOS.apiFetch('/api/products', { method: 'POST', body: payload });
      }
      hideModal('product-modal-backdrop');
      showSuccess(editId ? 'Product updated.' : 'Product created.');
      loadProducts();
    } catch (err) {
      const errEl = q('modal-error');
      errEl.textContent = err.message || 'Could not save product.';
      errEl.hidden = false;
    } finally {
      ACOS.setLoading(btn, false, 'Save product');
    }
  }

  async function deleteProduct(id) {
    if (!confirm('Deactivate this product? It will no longer appear in your catalog.')) return;
    try {
      await ACOS.apiFetch(`/api/products/${id}`, { method: 'DELETE' });
      showSuccess('Product deactivated.');
      loadProducts();
    } catch (err) {
      showError(err.message || 'Could not delete product.');
    }
  }

  // ── Import ───────────────────────────────────────────────────────

  let importFile = null;

  function wireImport() {
    const input = q('import-file-input');
    const zone  = q('import-drop-zone');

    input.addEventListener('change', () => {
      importFile = input.files[0] || null;
      q('import-file-name').textContent = importFile ? importFile.name : '';
      q('import-submit-btn').disabled   = !importFile;
    });

    zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      importFile = e.dataTransfer.files[0] || null;
      if (importFile) {
        q('import-file-name').textContent = importFile.name;
        q('import-submit-btn').disabled = false;
      }
    });

    q('import-submit-btn').addEventListener('click', doImport);
    q('import-close-btn').addEventListener('click', () => hideModal('import-modal-backdrop'));
    q('import-cancel-btn').addEventListener('click', () => hideModal('import-modal-backdrop'));
  }

  async function doImport() {
    if (!importFile) return;
    const btn  = q('import-submit-btn');
    q('import-error').hidden   = true;
    q('import-success').hidden = true;
    q('import-result').hidden  = true;
    ACOS.setLoading(btn, true, 'Upload & Import');

    try {
      const fd = new FormData();
      fd.append('file', importFile);
      const token = ACOS.getAccessToken();
      const res   = await fetch('/api/products/import', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: fd,
      });
      const payload = await res.json();
      if (!payload.success && payload.data?.imported === undefined) throw new Error(payload.error?.message || 'Import failed.');

      const d = payload.data;
      q('import-success').textContent = payload.message;
      q('import-success').hidden = false;
      const resultEl = q('import-result');
      resultEl.innerHTML = `
        <div class="import-stats">
          <span class="stat ok">${d.imported} imported</span>
          ${d.failed > 0 ? `<span class="stat fail">${d.failed} failed</span>` : ''}
          ${d.duplicates > 0 ? `<span class="stat warn">${d.duplicates} duplicates</span>` : ''}
        </div>
        ${d.errors?.length ? `<ul class="import-errors">${d.errors.slice(0,10).map(e => `<li>Row ${e.row}: ${esc(e.reason)}</li>`).join('')}</ul>` : ''}
      `;
      resultEl.hidden = false;
      if (d.imported > 0) loadProducts();
    } catch (err) {
      const e = q('import-error');
      e.textContent = err.message || 'Import failed.';
      e.hidden = false;
    } finally {
      ACOS.setLoading(btn, false, 'Upload & Import');
    }
  }

  // ── Wire UI ──────────────────────────────────────────────────────

  function wireUI() {
    q('add-product-btn').addEventListener('click', openAddModal);
    q('import-btn').addEventListener('click', () => {
      importFile = null;
      q('import-file-name').textContent = '';
      q('import-submit-btn').disabled = true;
      q('import-error').hidden = q('import-success').hidden = q('import-result').hidden = true;
      showModal('import-modal-backdrop');
    });
    q('modal-close-btn').addEventListener('click', () => hideModal('product-modal-backdrop'));
    q('modal-cancel-btn').addEventListener('click', () => hideModal('product-modal-backdrop'));
    q('product-form').addEventListener('submit', saveProduct);
    q('prev-btn').addEventListener('click', () => loadProducts(currentPage - 1));
    q('next-btn').addEventListener('click', () => loadProducts(currentPage + 1));
    q('search-input').addEventListener('input', searchDebounce);
    q('filter-availability').addEventListener('change', () => loadProducts(1));
    q('filter-category').addEventListener('change', () => loadProducts(1));
    q('clear-filters-btn').addEventListener('click', () => {
      q('search-input').value = '';
      q('filter-availability').value = '';
      q('filter-category').value = '';
      loadProducts(1);
    });
    wireImport();
  }

  // ── Helpers ──────────────────────────────────────────────────────

  function q(id)  { return document.getElementById(id); }
  function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
  function showModal(id) { q(id).hidden = false; document.body.style.overflow = 'hidden'; }
  function hideModal(id) { q(id).hidden = true;  document.body.style.overflow = ''; }
  function showError(msg)   { q('page-error').textContent = msg; q('page-error').hidden = false; q('page-success').hidden = true; }
  function showSuccess(msg) { q('page-success').textContent = msg; q('page-success').hidden = false; q('page-error').hidden = true; setTimeout(() => { q('page-success').hidden = true; }, 4000); }
  function debounce(fn, delay) { let t; return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), delay); }; }

  function availBadge(a) {
    const map = { in_stock: ['badge-success','In stock'], out_of_stock: ['badge-neutral','Out of stock'], pre_order: ['badge-warning','Pre-order'] };
    const [cls, label] = map[a] || ['badge-neutral', a];
    return `<span class="badge ${cls}">${label}</span>`;
  }
  function statusBadge(s) {
    return s === 'active'
      ? `<span class="badge badge-success">Active</span>`
      : `<span class="badge badge-neutral">${s}</span>`;
  }
})();
