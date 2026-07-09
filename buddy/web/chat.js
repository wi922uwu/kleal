/* =============================================================================
   chat.js — the Buddy tab (center of the tab-bar).

   Conversational agent + matching. Greets the user by name (from the profile
   handed over by kleal_v2 onboarding), offers quick-idea chips, and posts each
   message to POST /buddy/chat. On a social intent the backend returns matches.

   Exposes a global `renderChat(container)`.
   ============================================================================= */
(function (global) {
  const esc = s => (s || '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const md = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .split('\n').map(l => l.replace(/^\s*[\*\-]\s+(.*)/, '<span class="li">• $1</span>')).join('\n');

  const CHIPS = ['Coffee', 'Watch a match', 'Play a game', 'Language practice', 'A walk', 'A chat'];

  function renderChat(container) {
    container.innerHTML =
      `<div class="chat" id="chat"></div>
       <div class="inbar">
         <div class="inwrap"><input id="m" placeholder="Message…" autocomplete="off">
           <span class="mic">${ICON.mic}</span></div>
         <button class="send" id="s">${ICON.send}</button>
       </div>`;

    const chat = container.querySelector('#chat');
    const inp = container.querySelector('#m');
    const btn = container.querySelector('#s');

    const scroll = () => { chat.scrollTop = chat.scrollHeight; };
    const el = (cls, html) => { const d = document.createElement('div'); d.className = cls; d.innerHTML = html; chat.appendChild(d); scroll(); return d; };
    const bubble = (who, html) => el('b ' + who, html);
    const klabel = () => el('klabel', 'Kleal');
    let typingEl = null;
    const typing = on => { if (on) typingEl = el('typing', 'Kleal is typing…'); else if (typingEl) { typingEl.remove(); typingEl = null; } };
    const cards = ms => {
      const w = el('mcards', '');
      ms.forEach(m => {
        const c = document.createElement('div'); c.className = 'mcard';
        c.innerHTML = `<b>${esc(m.name)}</b> <span class="sc">· ${m.score}</span><div class="r">${esc(m.reason)}</div>`;
        w.appendChild(c);
      });
    };

    const name = (Store.profile.name || '').trim();
    klabel();
    bubble('bot', name ? `Hey ${esc(name)}! What do you feel like doing?` : 'Hey! What do you feel like doing?');
    el('hint', 'Pick some or write your own');
    const chipRow = el('chips', '');
    CHIPS.forEach(t => {
      const c = document.createElement('div'); c.className = 'chip'; c.textContent = t;
      c.onclick = () => { chipRow.remove(); send(t); };
      chipRow.appendChild(c);
    });

    async function send(text) {
      text = (text || '').trim(); if (!text) return;
      inp.value = ''; btn.disabled = true;
      bubble('me', esc(text)); typing(true);
      try {
        const r = await fetch('/buddy/chat', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: Store.uid, message: text }),
        });
        const d = await r.json(); typing(false); klabel();
        if (d.error) bubble('bot', '⚠️ ' + esc(d.error));
        else { bubble('bot', md(d.reply)); if (d.matches && d.matches.length) cards(d.matches); }
      } catch (e) { typing(false); klabel(); bubble('bot', '⚠️ ' + esc(String(e))); }
      btn.disabled = false; inp.focus();
    }

    btn.onclick = () => send(inp.value);
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') send(inp.value); });
  }

  global.renderChat = renderChat;
})(window);
