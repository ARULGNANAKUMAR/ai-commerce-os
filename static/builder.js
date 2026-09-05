/**
 * builder.js — AI Commerce OS Workflow Builder Canvas
 * Drag-and-drop node graph editor with AI execution engine integration.
 * No external dependencies — pure vanilla JS.
 */

(function () {
'use strict';

// ═══════════════════════════════════════════════════════════════════
// NODE DEFINITIONS — icons, categories, port layouts, config schemas
// ═══════════════════════════════════════════════════════════════════

const NODE_DEFS = {
  'trigger.start': {
    label: 'Start', icon: '▶', category: 'trigger',
    inPorts: [], outPorts: [{ id: 'default' }],
    schema: [{ key: 'description', type: 'text', label: 'Description', default: 'Workflow starts here' }]
  },
  'trigger.end': {
    label: 'End', icon: '⏹', category: 'trigger',
    inPorts: [{ id: 'in' }], outPorts: [],
    schema: [{ key: 'message', type: 'text', label: 'Completion message', default: 'Workflow completed.' }]
  },
  'ai.prompt': {
    label: 'AI Prompt', icon: '✨', category: 'ai',
    inPorts: [{ id: 'in' }], outPorts: [{ id: 'default' }],
    schema: [
      { key: 'prompt', type: 'textarea', label: 'Prompt template', default: 'You are a shopping assistant. Help the customer with: {{customer_query}}', hint: 'Use {{variable}} for dynamic values' },
      { key: 'temperature', type: 'number', label: 'Temperature (0–1)', default: 0.7, min: 0, max: 1, step: 0.1 }
    ]
  },
  'catalog.product_search': {
    label: 'Product Search', icon: '🔍', category: 'catalog',
    inPorts: [{ id: 'in' }], outPorts: [{ id: 'default' }],
    schema: [
      { key: 'keyword', type: 'text', label: 'Search keyword', default: '{{customer_query}}', hint: 'Use {{variable}} for dynamic values' },
      { key: 'category', type: 'text', label: 'Category filter', default: '{{category}}' },
      { key: 'max_results', type: 'number', label: 'Max results', default: 5, min: 1, max: 20 },
      { key: 'max_price', type: 'number', label: 'Max price (₹)', default: '', placeholder: 'Optional' }
    ]
  },
  'catalog.product_compare': {
    label: 'Compare Products', icon: '⚖️', category: 'catalog',
    inPorts: [{ id: 'in' }], outPorts: [{ id: 'default' }],
    schema: [{ key: 'attributes', type: 'text', label: 'Compare attributes (comma-separated)', default: 'price,stock,brand,discount' }]
  },
  'catalog.recommendation': {
    label: 'Recommendation', icon: '⭐', category: 'catalog',
    inPorts: [{ id: 'in' }], outPorts: [{ id: 'default' }],
    schema: [
      { key: 'top_n', type: 'number', label: 'Top N results', default: 3, min: 1, max: 10 },
      { key: 'ranking_criteria', type: 'select', label: 'Rank by', options: ['relevance', 'price', 'stock'], default: 'relevance' }
    ]
  },
  'sales.upsell': {
    label: 'Upsell', icon: '📈', category: 'sales',
    inPorts: [{ id: 'in' }], outPorts: [{ id: 'default' }],
    schema: [
      { key: 'upsell_percentage', type: 'number', label: 'Min price uplift %', default: 20, min: 0, max: 200 },
      { key: 'max_suggestions', type: 'number', label: 'Max suggestions', default: 2, min: 1, max: 5 }
    ]
  },
  'sales.cross_sell': {
    label: 'Cross-sell', icon: '🔀', category: 'sales',
    inPorts: [{ id: 'in' }], outPorts: [{ id: 'default' }],
    schema: [{ key: 'max_suggestions', type: 'number', label: 'Max suggestions', default: 2, min: 1, max: 5 }]
  },
  'logic.condition': {
    label: 'Condition', icon: '⚡', category: 'logic',
    inPorts: [{ id: 'in' }], outPorts: [{ id: 'true', label: 'True' }, { id: 'false', label: 'False' }],
    schema: [
      { key: 'field', type: 'text', label: 'Context field', default: 'variables.budget', hint: 'e.g. variables.budget' },
      { key: 'operator', type: 'select', label: 'Operator', options: ['>', '<', '>=', '<=', '==', '!='], default: '>' },
      { key: 'value', type: 'text', label: 'Compare to', default: '2000' }
    ]
  },
  'permission.check': {
    label: 'Permission Check', icon: '🛡', category: 'permission',
    inPorts: [{ id: 'in' }], outPorts: [{ id: 'allowed', label: 'Allowed' }, { id: 'denied', label: 'Denied' }],
    schema: [
      { key: 'capability', type: 'select', label: 'Capability', options: ['product_read','product_search','product_compare','recommendation','upsell','cross_sell','cart_create','checkout_create','payment_request','refund_request','campaign_create','customer_data_read'], default: 'product_search' }
    ]
  },
  'human.approval': {
    label: 'Human Approval', icon: '👤', category: 'approval',
    inPorts: [{ id: 'in' }], outPorts: [{ id: 'default' }],
    schema: [{ key: 'message', type: 'textarea', label: 'Approval message', default: 'Please review and approve this action.' }]
  },
  'commerce.cart': {
    label: 'Create Cart', icon: '🛒', category: 'commerce',
    inPorts: [{ id: 'in' }], outPorts: [{ id: 'default' }],
    schema: [{ key: 'note', type: 'text', label: 'Cart note', default: '' }]
  },
  'commerce.checkout_placeholder': {
    label: 'Checkout', icon: '💳', category: 'commerce',
    inPorts: [{ id: 'in' }], outPorts: [{ id: 'default' }],
    schema: [{ key: 'note', type: 'text', label: 'Note', default: 'Razorpay checkout connects in Phase 4.' }]
  },
  'utility.delay': {
    label: 'Delay', icon: '⏱', category: 'utility',
    inPorts: [{ id: 'in' }], outPorts: [{ id: 'default' }],
    schema: [{ key: 'delay_seconds', type: 'number', label: 'Delay (seconds)', default: 1, min: 0 }]
  },
};

const NODE_W = 200;
const NODE_H = 92;  // base height — multi-port nodes render taller in DOM

// ═══════════════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════════════

const state = {
  workflowId: null,
  nodes: {},   // { id: { id, type, label, position:{x,y}, config } }
  edges: [],   // [ { id, fromNode, fromPort, toNode, toPort } ]
  selected: null,
  connectingFrom: null,  // { nodeId, portId, x, y }
  dragging: null,        // { nodeId, startMouseX, startMouseY, startNodeX, startNodeY }
  panning: null,         // { startMouseX, startMouseY, startTX, startTY }
  transform: { x: 80, y: 60, scale: 1 },
  isDirty: false,
  nodeCounter: 0,
};

// ═══════════════════════════════════════════════════════════════════
// DOM REFS
// ═══════════════════════════════════════════════════════════════════

let canvasWrapper, canvasRoot, edgesSvg, nodesLayer, previewPath;
let configEmpty, configContent, configBody, configNodeLabel, configNodeType;

// ═══════════════════════════════════════════════════════════════════
// COORDINATE HELPERS
// ═══════════════════════════════════════════════════════════════════

function screenToCanvas(sx, sy) {
  const r = canvasWrapper.getBoundingClientRect();
  return {
    x: (sx - r.left - state.transform.x) / state.transform.scale,
    y: (sy - r.top  - state.transform.y) / state.transform.scale,
  };
}

function applyTransform() {
  const { x, y, scale } = state.transform;
  canvasRoot.style.transform = `translate(${x}px,${y}px) scale(${scale})`;
  document.getElementById('zoom-label').textContent = `${Math.round(scale * 100)}%`;
}

function clamp(val, min, max) { return Math.max(min, Math.min(max, val)); }

// ═══════════════════════════════════════════════════════════════════
// PORT POSITIONS  (in canvas coordinate space)
// ═══════════════════════════════════════════════════════════════════

function portPos(nodeId, side, portId) {
  const node = state.nodes[nodeId];
  if (!node) return null;
  const def   = NODE_DEFS[node.type] || {};
  const ports = side === 'in' ? (def.inPorts || []) : (def.outPorts || []);
  const idx   = ports.findIndex(p => p.id === portId);
  const total = ports.length;
  const gap   = total > 1 ? 28 : 0;
  const baseY = node.position.y + NODE_H / 2;
  const py    = total > 1 ? (baseY - gap + idx * (gap * 2 / (total - 1 || 1))) : baseY;
  const px    = side === 'in' ? node.position.x : node.position.x + NODE_W;
  return { x: px, y: py };
}

// ═══════════════════════════════════════════════════════════════════
// NODE RENDERING
// ═══════════════════════════════════════════════════════════════════

function makeNodeId() {
  return `n${++state.nodeCounter}_${Date.now().toString(36)}`;
}

function addNode(type, canvasX, canvasY, existingId = null, existingConfig = null) {
  const def = NODE_DEFS[type];
  if (!def) return;
  const id  = existingId || makeNodeId();
  state.nodes[id] = {
    id, type,
    label:    existingConfig?.label || def.label,
    position: { x: canvasX - NODE_W / 2, y: canvasY - NODE_H / 2 },
    config:   existingConfig || _defaultConfig(type),
  };
  renderNode(id);
  hidePlaceholder();
  markDirty();
  return id;
}

function _defaultConfig(type) {
  const schema = (NODE_DEFS[type] || {}).schema || [];
  const cfg = {};
  schema.forEach(f => { cfg[f.key] = f.default !== undefined ? f.default : ''; });
  return cfg;
}

function renderNode(id) {
  document.getElementById(`node-${id}`)?.remove();
  const node = state.nodes[id];
  const def  = NODE_DEFS[node.type] || { label: node.type, icon: '?', category: 'utility', inPorts: [{id:'in'}], outPorts: [{id:'default'}], schema: [] };
  const el   = document.createElement('div');
  el.className = `wf-node node-cat-${def.category}${state.selected === id ? ' selected' : ''}`;
  el.id        = `node-${id}`;
  el.style.cssText = `left:${node.position.x}px;top:${node.position.y}px`;
  el.dataset.id    = id;

  // Build port labels for display
  const outLabels = (def.outPorts || []).map(p => p.label || '').filter(Boolean).join(' / ');
  const cfgPreview = _configPreview(node);

  el.innerHTML = `
    <button class="wf-node-delete" data-id="${id}" title="Delete node">✕</button>
    <div class="wf-node-header">
      <span class="wf-node-icon">${def.icon || '?'}</span>
      <span class="wf-node-type">${def.label}</span>
    </div>
    ${node.label !== def.label ? `<div class="wf-node-label">${esc(node.label)}</div>` : ''}
    ${cfgPreview ? `<div class="wf-node-config">${cfgPreview}</div>` : ''}
    <div id="ports-${id}"></div>
  `;

  const portsEl = el.querySelector(`#ports-${id}`);

  // Input ports
  (def.inPorts || []).forEach((p, i, arr) => {
    const dot = document.createElement('div');
    dot.className = 'wf-port wf-port-in';
    dot.dataset.node = id; dot.dataset.port = p.id; dot.dataset.side = 'in';
    const gap = arr.length > 1 ? 28 : 0;
    dot.style.top = `${NODE_H / 2 - gap + i * (gap * 2 / (arr.length - 1 || 1)) - 6}px`;
    portsEl.appendChild(dot);
  });

  // Output ports
  (def.outPorts || []).forEach((p, i, arr) => {
    const dot = document.createElement('div');
    dot.className = 'wf-port wf-port-out';
    dot.dataset.node = id; dot.dataset.port = p.id; dot.dataset.side = 'out';
    const gap = arr.length > 1 ? 28 : 0;
    dot.style.top = `${NODE_H / 2 - gap + i * (gap * 2 / (arr.length - 1 || 1)) - 6}px`;
    if (p.label) {
      const lbl = document.createElement('span');
      lbl.style.cssText = 'position:absolute;right:16px;font-size:9.5px;color:var(--color-text-faint);white-space:nowrap;top:1px';
      lbl.textContent = p.label;
      dot.appendChild(lbl);
    }
    portsEl.appendChild(dot);
  });

  nodesLayer.appendChild(el);
  wireNodeEvents(el);
}

function _configPreview(node) {
  const cfg = node.config || {};
  const keys = Object.keys(cfg).slice(0, 2);
  return keys.map(k => {
    const v = String(cfg[k] || '');
    return v.length > 22 ? v.slice(0, 22) + '…' : v;
  }).filter(Boolean).join(' · ');
}

function rerenderNode(id) { renderNode(id); renderEdges(); }

function removeNode(id) {
  document.getElementById(`node-${id}`)?.remove();
  delete state.nodes[id];
  state.edges = state.edges.filter(e => e.fromNode !== id && e.toNode !== id);
  if (state.selected === id) deselectAll();
  renderEdges();
  markDirty();
  if (!Object.keys(state.nodes).length) showPlaceholder();
}

// ═══════════════════════════════════════════════════════════════════
// EDGE RENDERING
// ═══════════════════════════════════════════════════════════════════

function bezier(x1, y1, x2, y2) {
  const cx = Math.abs(x2 - x1) * 0.55 + 40;
  return `M${x1},${y1} C${x1+cx},${y1} ${x2-cx},${y2} ${x2},${y2}`;
}

function renderEdges() {
  // Remove old edge elements (not preview, not defs)
  edgesSvg.querySelectorAll('.wf-edge').forEach(e => e.remove());
  state.edges.forEach(edge => {
    const fromP = portPos(edge.fromNode, 'out', edge.fromPort || 'default');
    const toP   = portPos(edge.toNode,   'in',  edge.toPort   || 'in');
    if (!fromP || !toP) return;

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.classList.add('wf-edge');
    path.dataset.id = edge.id;
    path.setAttribute('d', bezier(fromP.x, fromP.y, toP.x, toP.y));
    path.setAttribute('marker-end', 'url(#arrow)');
    edgesSvg.insertBefore(path, previewPath);

    path.addEventListener('click', (e) => {
      e.stopPropagation();
      const confirmed = confirm('Delete this connection?');
      if (confirmed) {
        state.edges = state.edges.filter(ed => ed.id !== edge.id);
        renderEdges();
        markDirty();
      }
    });
  });
}

// ═══════════════════════════════════════════════════════════════════
// NODE EVENTS (drag, select, port interaction)
// ═══════════════════════════════════════════════════════════════════

function wireNodeEvents(el) {
  const id = el.dataset.id;

  // Delete button
  el.querySelector('.wf-node-delete')?.addEventListener('click', e => {
    e.stopPropagation();
    if (Object.keys(state.nodes).length === 1 || confirm('Delete this node?')) removeNode(id);
  });

  // Select + drag start on the node body (not ports)
  el.addEventListener('mousedown', e => {
    if (e.target.classList.contains('wf-port') || e.target.closest('.wf-node-delete')) return;
    e.stopPropagation();
    selectNode(id);

    state.dragging = {
      nodeId:      id,
      startMouseX: e.clientX,
      startMouseY: e.clientY,
      startNodeX:  state.nodes[id].position.x,
      startNodeY:  state.nodes[id].position.y,
    };
  });

  // Port mousedown — start edge connection
  el.querySelectorAll('.wf-port-out').forEach(portEl => {
    portEl.addEventListener('mousedown', e => {
      e.stopPropagation();
      const nodeId = portEl.dataset.node;
      const portId = portEl.dataset.port;
      const pp = portPos(nodeId, 'out', portId);
      if (!pp) return;
      state.connectingFrom = { nodeId, portId, x: pp.x, y: pp.y };
      portEl.classList.add('active');
    });
  });

  // Port mouseup on input port — complete edge
  el.querySelectorAll('.wf-port-in').forEach(portEl => {
    portEl.addEventListener('mouseup', e => {
      e.stopPropagation();
      if (!state.connectingFrom) return;
      const toNode = portEl.dataset.node;
      const toPort = portEl.dataset.port;
      const fromNode = state.connectingFrom.nodeId;

      // Prevent self-loop or duplicate
      if (fromNode === toNode) { cancelConnect(); return; }
      const dup = state.edges.find(ed => ed.fromNode === fromNode && ed.toNode === toNode && ed.fromPort === state.connectingFrom.portId);
      if (dup) { cancelConnect(); return; }

      const edgeId = `e${Date.now().toString(36)}`;
      state.edges.push({ id: edgeId, fromNode, fromPort: state.connectingFrom.portId, toNode, toPort });
      cancelConnect();
      renderEdges();
      markDirty();
    });
  });
}

function cancelConnect() {
  edgesSvg.querySelectorAll('.wf-port-out.active').forEach(p => p.classList.remove('active'));
  nodesLayer.querySelectorAll('.wf-port.active').forEach(p => p.classList.remove('active'));
  state.connectingFrom = null;
  previewPath.setAttribute('d', '');
}

// ═══════════════════════════════════════════════════════════════════
// SELECTION + CONFIG PANEL
// ═══════════════════════════════════════════════════════════════════

function selectNode(id) {
  deselectAll();
  state.selected = id;
  document.getElementById(`node-${id}`)?.classList.add('selected');
  renderConfigPanel(id);
}

function deselectAll() {
  if (state.selected) document.getElementById(`node-${state.selected}`)?.classList.remove('selected');
  state.selected = null;
  configEmpty.hidden = false;
  configContent.hidden = true;
}

function renderConfigPanel(id) {
  const node = state.nodes[id];
  if (!node) return;
  const def = NODE_DEFS[node.type] || { label: node.type, schema: [] };
  configEmpty.hidden   = true;
  configContent.hidden = false;
  configNodeLabel.textContent = node.label || def.label;
  configNodeType.textContent  = node.type;

  configBody.innerHTML = '';

  // Label field always first
  const labelField = mkField({ key: '_label', type: 'text', label: 'Node label' }, node.label || def.label);
  configBody.appendChild(labelField);

  // Type-specific fields
  (def.schema || []).forEach(fieldDef => {
    const val = node.config?.[fieldDef.key] !== undefined ? node.config[fieldDef.key] : (fieldDef.default || '');
    configBody.appendChild(mkField(fieldDef, val));
  });
}

function mkField(fieldDef, value) {
  const wrap = document.createElement('div');
  wrap.className = 'config-field';
  let input;

  if (fieldDef.type === 'select') {
    input = document.createElement('select');
    input.dataset.key = fieldDef.key;
    (fieldDef.options || []).forEach(opt => {
      const o = document.createElement('option');
      o.value = opt; o.textContent = opt;
      if (String(value) === opt) o.selected = true;
      input.appendChild(o);
    });
  } else if (fieldDef.type === 'textarea') {
    input = document.createElement('textarea');
    input.dataset.key = fieldDef.key;
    input.value = value;
    input.rows  = 3;
  } else {
    input = document.createElement('input');
    input.type     = fieldDef.type || 'text';
    input.dataset.key = fieldDef.key;
    input.value    = value;
    if (fieldDef.min  !== undefined) input.min  = fieldDef.min;
    if (fieldDef.max  !== undefined) input.max  = fieldDef.max;
    if (fieldDef.step !== undefined) input.step = fieldDef.step;
    if (fieldDef.placeholder) input.placeholder = fieldDef.placeholder;
  }

  wrap.innerHTML = `<label>${esc(fieldDef.label)}</label>`;
  wrap.appendChild(input);
  if (fieldDef.hint) {
    const hint = document.createElement('div');
    hint.className = 'config-hint';
    hint.textContent = fieldDef.hint;
    wrap.appendChild(hint);
  }
  return wrap;
}

function saveConfig() {
  const id = state.selected;
  if (!id || !state.nodes[id]) return;
  const fields = configBody.querySelectorAll('[data-key]');
  const node   = state.nodes[id];
  fields.forEach(f => {
    if (f.dataset.key === '_label') {
      node.label = f.value.trim() || NODE_DEFS[node.type]?.label || node.label;
    } else {
      node.config = node.config || {};
      node.config[f.dataset.key] = f.value;
    }
  });
  rerenderNode(id);
  selectNode(id);
  markDirty();
}

// ═══════════════════════════════════════════════════════════════════
// PALETTE INTERACTION (click to add at smart position)
// ═══════════════════════════════════════════════════════════════════

function wirePalette() {
  document.querySelectorAll('.palette-node').forEach(item => {
    const type = item.dataset.type;

    // Click to add at next auto-position
    item.addEventListener('click', () => {
      const nodeCount = Object.keys(state.nodes).length;
      const cx = 300 + nodeCount * 240;
      const cy = 250;
      const id = addNode(type, cx, cy);
      selectNode(id);
      renderEdges();
    });

    // Drag to drop on canvas
    item.addEventListener('mousedown', e => {
      if (e.button !== 0) return;
      const ghost = item.cloneNode(true);
      ghost.style.cssText = `position:fixed;pointer-events:none;opacity:0.75;z-index:9999;border:1px solid var(--color-primary);background:var(--color-surface);border-radius:8px;padding:6px 10px;font-size:13px;`;
      document.body.appendChild(ghost);

      const onMove = ev => {
        ghost.style.left = (ev.clientX - 60) + 'px';
        ghost.style.top  = (ev.clientY - 18) + 'px';
        const r = canvasWrapper.getBoundingClientRect();
        canvasWrapper.classList.toggle('drag-over', ev.clientX > r.left);
      };
      const onUp = ev => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        ghost.remove();
        canvasWrapper.classList.remove('drag-over');
        const r = canvasWrapper.getBoundingClientRect();
        if (ev.clientX > r.left && ev.clientX < r.right && ev.clientY > r.top && ev.clientY < r.bottom) {
          const cp = screenToCanvas(ev.clientX, ev.clientY);
          const id = addNode(type, cp.x, cp.y);
          selectNode(id);
          renderEdges();
        }
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  });
}

// ═══════════════════════════════════════════════════════════════════
// GLOBAL MOUSE EVENTS (drag node, edge preview, pan)
// ═══════════════════════════════════════════════════════════════════

function wireCanvasEvents() {
  // Click empty canvas to deselect
  canvasWrapper.addEventListener('mousedown', e => {
    if (e.target === canvasWrapper || e.target === canvasRoot || e.target === nodesLayer || e.target === edgesSvg) {
      if (e.button === 1 || (e.button === 0 && e.altKey)) {
        // Middle mouse or alt+drag = pan
        state.panning = { startMouseX: e.clientX, startMouseY: e.clientY, startTX: state.transform.x, startTY: state.transform.y };
        canvasWrapper.style.cursor = 'grabbing';
      } else if (e.button === 0 && !state.connectingFrom) {
        deselectAll();
        state.panning = { startMouseX: e.clientX, startMouseY: e.clientY, startTX: state.transform.x, startTY: state.transform.y };
        canvasWrapper.style.cursor = 'grab';
      }
    }
  });

  document.addEventListener('mousemove', e => {
    // Node dragging
    if (state.dragging) {
      const dx = (e.clientX - state.dragging.startMouseX) / state.transform.scale;
      const dy = (e.clientY - state.dragging.startMouseY) / state.transform.scale;
      const node = state.nodes[state.dragging.nodeId];
      node.position.x = state.dragging.startNodeX + dx;
      node.position.y = state.dragging.startNodeY + dy;
      const el = document.getElementById(`node-${state.dragging.nodeId}`);
      if (el) { el.style.left = node.position.x + 'px'; el.style.top = node.position.y + 'px'; }
      renderEdges();
    }

    // Edge preview
    if (state.connectingFrom) {
      const cp = screenToCanvas(e.clientX, e.clientY);
      previewPath.setAttribute('d', bezier(state.connectingFrom.x, state.connectingFrom.y, cp.x, cp.y));
    }

    // Canvas pan
    if (state.panning) {
      state.transform.x = state.panning.startTX + (e.clientX - state.panning.startMouseX);
      state.transform.y = state.panning.startTY + (e.clientY - state.panning.startMouseY);
      applyTransform();
    }
  });

  document.addEventListener('mouseup', e => {
    state.dragging = null;
    if (state.panning) { state.panning = null; canvasWrapper.style.cursor = ''; }
    if (state.connectingFrom) cancelConnect();
  });

  // Zoom
  canvasWrapper.addEventListener('wheel', e => {
    e.preventDefault();
    const delta   = e.deltaY > 0 ? 0.9 : 1.1;
    const newScale = clamp(state.transform.scale * delta, 0.3, 2.5);
    const r       = canvasWrapper.getBoundingClientRect();
    const mx      = e.clientX - r.left;
    const my      = e.clientY - r.top;
    state.transform.x = mx - (mx - state.transform.x) * (newScale / state.transform.scale);
    state.transform.y = my - (my - state.transform.y) * (newScale / state.transform.scale);
    state.transform.scale = newScale;
    applyTransform();
  }, { passive: false });

  // Keyboard shortcuts
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { cancelConnect(); deselectAll(); }
    if (e.key === 'Delete' && state.selected) removeNode(state.selected);
    if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); saveWorkflow(); }
  });
}

// ═══════════════════════════════════════════════════════════════════
// TOOLBAR CONTROLS
// ═══════════════════════════════════════════════════════════════════

function wireToolbar() {
  document.getElementById('save-btn').addEventListener('click', saveWorkflow);
  document.getElementById('publish-btn').addEventListener('click', publishWorkflow);
  document.getElementById('run-btn').addEventListener('click', openExecModal);
  document.getElementById('analyze-btn').addEventListener('click', openAnalyzeModal);

  document.getElementById('zoom-in-btn').addEventListener('click', () => {
    state.transform.scale = clamp(state.transform.scale * 1.2, 0.3, 2.5); applyTransform();
  });
  document.getElementById('zoom-out-btn').addEventListener('click', () => {
    state.transform.scale = clamp(state.transform.scale / 1.2, 0.3, 2.5); applyTransform();
  });
  document.getElementById('fit-btn').addEventListener('click', fitToScreen);
  document.getElementById('clear-btn').addEventListener('click', () => {
    if (confirm('Clear all nodes? This cannot be undone.')) clearCanvas();
  });

  document.getElementById('config-save-btn').addEventListener('click', saveConfig);
  document.getElementById('wf-name').addEventListener('change', markDirty);
}

function fitToScreen() {
  const ids = Object.keys(state.nodes);
  if (!ids.length) return;
  const xs = ids.map(id => state.nodes[id].position.x);
  const ys = ids.map(id => state.nodes[id].position.y);
  const minX = Math.min(...xs) - 60, minY = Math.min(...ys) - 60;
  const maxX = Math.max(...xs) + NODE_W + 60, maxY = Math.max(...ys) + NODE_H + 60;
  const r   = canvasWrapper.getBoundingClientRect();
  const sx  = r.width / (maxX - minX);
  const sy  = r.height / (maxY - minY);
  state.transform.scale = clamp(Math.min(sx, sy), 0.3, 1.5);
  state.transform.x = (r.width  - (maxX - minX) * state.transform.scale) / 2 - minX * state.transform.scale;
  state.transform.y = (r.height - (maxY - minY) * state.transform.scale) / 2 - minY * state.transform.scale;
  applyTransform();
}

function clearCanvas() {
  Object.keys(state.nodes).forEach(id => document.getElementById(`node-${id}`)?.remove());
  state.nodes = {}; state.edges = []; state.selected = null;
  renderEdges(); showPlaceholder(); markDirty();
}

// ═══════════════════════════════════════════════════════════════════
// WORKFLOW SAVE / LOAD / PUBLISH
// ═══════════════════════════════════════════════════════════════════

function getWorkflowData() {
  return {
    name:  document.getElementById('wf-name').value.trim() || 'Untitled Workflow',
    nodes: Object.values(state.nodes).map(n => ({
      id: n.id, type: n.type, label: n.label, position: n.position, config: n.config,
    })),
    edges: state.edges,
  };
}

async function saveWorkflow() {
  const btn = document.getElementById('save-btn');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    const data = getWorkflowData();
    let res;
    if (state.workflowId) {
      res = await ACOS.apiFetch(`/api/workflows/${state.workflowId}`, { method: 'PUT', body: data });
    } else {
      res = await ACOS.apiFetch('/api/workflows', { method: 'POST', body: data });
      state.workflowId = res.data.workflow.id;
      window.history.replaceState({}, '', `/builder/${state.workflowId}`);
    }
    setStatus(res.data.workflow.status);
    state.isDirty = false;
    btn.textContent = 'Saved ✓';
    setTimeout(() => { btn.textContent = 'Save'; }, 2000);
  } catch (err) {
    alert('Save failed: ' + (err.message || 'Unknown error'));
    btn.textContent = 'Save';
  }
  btn.disabled = false;
}

async function publishWorkflow() {
  if (!state.workflowId) { await saveWorkflow(); }
  if (!state.workflowId) return;
  try {
    const res = await ACOS.apiFetch(`/api/workflows/${state.workflowId}/publish`, { method: 'POST' });
    setStatus('published');
    alert('Workflow published!');
  } catch (err) { alert('Publish failed: ' + err.message); }
}

function setStatus(status) {
  const el = document.getElementById('toolbar-status');
  el.textContent = status.charAt(0).toUpperCase() + status.slice(1);
  el.className   = `toolbar-status badge ${status === 'published' ? 'badge-success' : 'badge-neutral'}`;
}

function loadWorkflow(data) {
  clearCanvas();
  document.getElementById('wf-name').value = data.name || 'Untitled Workflow';
  setStatus(data.status || 'draft');
  (data.nodes || []).forEach(n => {
    state.nodeCounter++;
    state.nodes[n.id] = { id: n.id, type: n.type, label: n.label, position: n.position, config: n.config || {} };
    renderNode(n.id);
  });
  state.edges = data.edges || [];
  renderEdges();
  if (data.nodes?.length) { hidePlaceholder(); fitToScreen(); }
}

// ═══════════════════════════════════════════════════════════════════
// EXECUTION MODAL
// ═══════════════════════════════════════════════════════════════════

function openExecModal() {
  document.getElementById('exec-results').hidden = true;
  document.getElementById('exec-modal').hidden = false;
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('exec-close-btn').addEventListener('click', () => { document.getElementById('exec-modal').hidden = true; });
  document.getElementById('exec-cancel-btn').addEventListener('click', () => { document.getElementById('exec-modal').hidden = true; });
  document.getElementById('exec-run-btn').addEventListener('click', runExecution);
  document.getElementById('analyze-close-btn').addEventListener('click', () => { document.getElementById('analyze-modal').hidden = true; });
  document.getElementById('analyze-ok-btn').addEventListener('click', () => { document.getElementById('analyze-modal').hidden = true; });
});

async function runExecution() {
  if (!state.workflowId) { await saveWorkflow(); }
  if (!state.workflowId) return;

  const btn = document.getElementById('exec-run-btn');
  btn.disabled = true; btn.textContent = '⏳ Running…';

  const triggerData = {
    customer_query: document.getElementById('td-query').value,
    budget:         parseFloat(document.getElementById('td-budget').value) || 2000,
    category:       document.getElementById('td-category').value,
    customer_name:  document.getElementById('td-name').value,
  };

  try {
    const res   = await ACOS.apiFetch(`/api/workflows/${state.workflowId}/execute`, { method: 'POST', body: { trigger_data: triggerData } });
    const exec  = res.data.execution;
    renderExecResults(exec);
  } catch (err) {
    alert('Execution failed: ' + (err.message || 'Unknown error'));
  }
  btn.disabled = false; btn.textContent = '▶ Run workflow';
}

function renderExecResults(exec) {
  const badge = document.getElementById('exec-status-badge');
  badge.textContent = exec.status;
  badge.className   = `badge ${exec.status === 'completed' ? 'badge-success' : 'badge-warning'}`;
  document.getElementById('exec-duration').textContent = exec.duration_ms ? `${exec.duration_ms}ms` : '';

  const stepsList = document.getElementById('exec-steps-list');
  stepsList.innerHTML = (exec.steps || []).map(s => `
    <div class="exec-step step-${s.status}">
      <div class="exec-step-num">${s.step}</div>
      <div class="exec-step-info">
        <div class="exec-step-label">${esc(s.node_label || s.node_type)}</div>
        <div class="exec-step-type">${s.node_type}</div>
      </div>
      <div class="exec-step-ms">${s.duration_ms}ms</div>
    </div>`).join('');

  if (exec.result && Object.keys(exec.result).length) {
    const pre = document.getElementById('exec-result-pre');
    const display = {};
    if (exec.result.message) display.message = exec.result.message;
    if (exec.result.ai_response) display.ai_response = exec.result.ai_response;
    if (exec.result.products?.length) display.product_count = exec.result.products.length;
    if (exec.result.summary) display.summary = exec.result.summary;
    pre.textContent = JSON.stringify(display, null, 2);
    document.getElementById('exec-result-box').hidden = false;
  }

  document.getElementById('exec-results').hidden = false;
}

// ═══════════════════════════════════════════════════════════════════
// ANALYSIS MODAL
// ═══════════════════════════════════════════════════════════════════

async function openAnalyzeModal() {
  document.getElementById('analyze-modal').hidden = false;
  document.getElementById('analyze-modal-body').innerHTML = '<div style="text-align:center;padding:var(--space-6);color:var(--color-text-faint)">Analysing…</div>';

  const data   = getWorkflowData();
  try {
    const res    = await ACOS.apiFetch('/api/agent/analyze', { method: 'POST', body: { nodes: data.nodes, edges: data.edges } });
    const a      = res.data.analysis;
    document.getElementById('analyze-modal-body').innerHTML = `
      <div style="display:flex;align-items:center;gap:var(--space-3);margin-bottom:var(--space-4)">
        <span class="analysis-badge ${a.ready_to_execute ? 'ready' : 'warning'}">${a.ready_to_execute ? '✅ Ready to run' : '⚠ Needs attention'}</span>
        <span style="font-size:12px;color:var(--color-text-muted)">${a.task?.description || ''}</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-3);margin-bottom:var(--space-4)">
        <div class="card" style="padding:var(--space-3)">
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--color-text-faint);margin-bottom:4px">Task type</div>
          <div style="font-size:13.5px;font-weight:600;color:var(--color-navy)">${a.task?.task_type?.replace(/_/g,' ') || '—'}</div>
        </div>
        <div class="card" style="padding:var(--space-3)">
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--color-text-faint);margin-bottom:4px">Est. duration</div>
          <div style="font-size:13.5px;font-weight:600;color:var(--color-navy)">${a.execution_plan?.estimated_duration_ms || 0}ms</div>
        </div>
      </div>
      <div style="font-size:12.5px;font-weight:600;color:var(--color-navy);margin-bottom:var(--space-2)">Execution sequence</div>
      <div style="font-size:12.5px;color:var(--color-text-muted);margin-bottom:var(--space-4)">${(a.architecture?.execution_sequence || []).join(' → ')}</div>
      ${a.suggestions?.length ? `
        <div style="font-size:12.5px;font-weight:600;color:var(--color-navy);margin-bottom:var(--space-2)">Suggestions</div>
        ${a.suggestions.map(s => `<div class="analysis-suggestion">${esc(s)}</div>`).join('')}
      ` : ''}
      ${a.memory?.pattern_found ? `<div style="margin-top:var(--space-4);font-size:12px;color:var(--color-success)">✅ This pattern has been used ${a.memory.past_executions} times successfully (avg ${a.memory.avg_duration_ms}ms).</div>` : ''}
    `;
  } catch (err) {
    document.getElementById('analyze-modal-body').innerHTML = `<div class="banner banner-error">Analysis failed: ${esc(err.message)}</div>`;
  }
}

// ═══════════════════════════════════════════════════════════════════
// UTILITY
// ═══════════════════════════════════════════════════════════════════

function markDirty() {
  state.isDirty = true;
  const s = document.getElementById('toolbar-status');
  if (!s.textContent.includes('•')) s.textContent = s.textContent + ' •';
}

function hidePlaceholder() { document.getElementById('canvas-hint').style.display = 'none'; }
function showPlaceholder() { document.getElementById('canvas-hint').style.display = ''; }
function esc(s) { const d = document.createElement('div'); d.textContent = String(s || ''); return d.innerHTML; }

// ═══════════════════════════════════════════════════════════════════
// BOOT
// ═══════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  ACOS.requireAuth().then(async profile => {
    if (!profile) return;

    canvasWrapper = document.getElementById('canvas-wrapper');
    canvasRoot    = document.getElementById('canvas-root');
    edgesSvg      = document.getElementById('edges-svg');
    nodesLayer    = document.getElementById('nodes-layer');
    previewPath   = document.getElementById('edge-preview');
    configEmpty   = document.getElementById('config-empty');
    configContent = document.getElementById('config-content');
    configBody    = document.getElementById('config-body');
    configNodeLabel = document.getElementById('config-node-label');
    configNodeType  = document.getElementById('config-node-type');

    applyTransform();
    wirePalette();
    wireCanvasEvents();
    wireToolbar();

    // Load existing workflow if URL has an ID
    const pathParts = window.location.pathname.split('/');
    const urlId = pathParts[pathParts.length - 1];
    if (urlId && urlId !== 'builder') {
      try {
        const res = await ACOS.apiFetch(`/api/workflows/${urlId}`);
        state.workflowId = urlId;
        loadWorkflow(res.data.workflow);
      } catch (e) { /* new workflow */ }
    }

    // Warn on unsaved changes
    window.addEventListener('beforeunload', e => {
      if (state.isDirty) { e.preventDefault(); e.returnValue = ''; }
    });
  });
});

})();
