/**
 * chat.js — AI Shopping Chat page
 */
let sessionId = null;

document.addEventListener('DOMContentLoaded', () => {
  ACOS.requireAuth().then(profile => {
    if (!profile) return;
    ACOS.renderSidebarUser(profile);
    ACOS.wireLogout();
    ACOS.wireMobileSidebar();

    sessionId = sessionStorage.getItem('acos_chat_session') || null;

    document.getElementById('chat-form').addEventListener('submit', onSend);
    document.getElementById('new-session-btn').addEventListener('click', () => {
      sessionId = null;
      sessionStorage.removeItem('acos_chat_session');
      document.getElementById('chat-messages').innerHTML = '';
      addMessage('assistant', "Started a new conversation. What are you looking for?");
    });
    document.querySelectorAll('.chat-lang-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        document.getElementById('chat-input').value = pill.dataset.msg;
        sendMessage(pill.dataset.msg);
      });
    });
  });
});

function onSend(e) {
  e.preventDefault();
  const input = document.getElementById('chat-input');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  sendMessage(msg);
}

async function sendMessage(message) {
  addMessage('user', message);
  showTyping();

  try {
    const res = await ACOS.apiFetch('/api/chat', { method: 'POST', body: { message, session_id: sessionId } });
    const d = res.data;
    sessionId = d.session_id;
    sessionStorage.setItem('acos_chat_session', sessionId);
    document.getElementById('lang-badge').textContent = d.language.toUpperCase();

    removeTyping();
    addMessage('assistant', d.reply, d.data);
  } catch (err) {
    removeTyping();
    addMessage('assistant', 'Sorry, something went wrong: ' + (err.message || 'unknown error'));
  }
}

function addMessage(role, text, data) {
  const container = document.getElementById('chat-messages');
  const wrap = document.createElement('div');
  wrap.className = `chat-msg ${role}`;
  const avatar = role === 'user' ? 'You' : '🤖';

  let productsHtml = '';
  const products = data?.products || data?.recommendations || data?.items;
  if (Array.isArray(products) && products.length) {
    productsHtml = `<div class="chat-product-cards">${products.slice(0, 5).map(p => `
      <div class="chat-product-card">
        <div class="chat-product-card-name">${esc(p.name)}</div>
        <div class="chat-product-card-price">₹${(p.price||0).toLocaleString('en-IN')}</div>
      </div>`).join('')}</div>`;
  }

  wrap.innerHTML = `
    <div class="chat-msg-avatar">${avatar}</div>
    <div>
      <div class="chat-msg-bubble">${esc(text)}</div>
      ${productsHtml}
      <div class="chat-msg-meta">${new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</div>
    </div>`;
  container.appendChild(wrap);
  container.scrollTop = container.scrollHeight;
}

function showTyping() {
  const container = document.getElementById('chat-messages');
  const wrap = document.createElement('div');
  wrap.className = 'chat-msg assistant';
  wrap.id = 'typing-indicator';
  wrap.innerHTML = `<div class="chat-msg-avatar">🤖</div><div class="chat-msg-bubble"><div class="chat-typing"><span></span><span></span><span></span></div></div>`;
  container.appendChild(wrap);
  container.scrollTop = container.scrollHeight;
}
function removeTyping() { document.getElementById('typing-indicator')?.remove(); }
function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
