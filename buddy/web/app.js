/* =============================================================================
   app.js — the app interface controller (loaded last).

   Option A: onboarding lives in kleal_v2. This app opens straight into the
   bottom tab-bar (profile already collected, arriving via ?p=). No onboarding
   phase here.

   Tabs: My Intents · Search · [Buddy] · Messages · Profile
   Buddy is the raised center button and the default screen. Profile is
   functional; the other three are documented placeholders.

   Exposes a global `App` ({ start }).
   ============================================================================= */
(function (global) {
  const app = document.getElementById('app');
  let active = 'buddy';

  function start() { renderShell(); }

  /* shell = active-screen content area + fixed bottom tab-bar */
  function renderShell() {
    app.innerHTML =
      `<div id="content" style="flex:1;display:flex;flex-direction:column;min-height:0"></div>
       <nav class="nav">
         ${tab('intents', ICON.intents, 'My Intents')}
         ${tab('search', ICON.search, 'Search')}
         <button class="tab spacer"><span>·</span></button>
         ${tab('messages', ICON.messages, 'Messages')}
         ${tab('profile', ICON.profile, 'Profile')}
         <button class="fab" data-k="buddy" aria-label="Buddy">${ICON.spark}</button>
       </nav>`;
    app.querySelectorAll('[data-k]').forEach(el => el.onclick = () => { active = el.dataset.k; renderShell(); });
    renderActive();
  }

  const tab = (key, icon, label) =>
    `<button class="tab ${active === key ? 'on' : ''}" data-k="${key}">${icon}<span>${label}</span></button>`;

  function renderActive() {
    const c = app.querySelector('#content');
    if (active === 'buddy') renderChat(c);
    else if (active === 'profile') renderProfile(c, restart);
    else placeholder(c, active);
  }

  const PLACEHOLDER = {
    intents: { icon: ICON.intents, title: 'My Intents', sub: 'Your active and past plans will live here.' },
    search: { icon: ICON.search, title: 'Search', sub: 'Browse people, rooms and events near you.' },
    messages: { icon: ICON.messages, title: 'Messages', sub: 'Chats open once a match is confirmed.' },
  };
  function placeholder(c, key) {
    const p = PLACEHOLDER[key];
    c.innerHTML =
      `<div class="scr-head"><h2>${p.title}</h2></div>
       <div class="empty"><div class="ei">${p.icon}</div><div>${p.sub}</div>
         <div style="font-size:13px">Coming soon</div></div>`;
  }

  /* Onboarding is a separate app (kleal_v2); "Restart" clears local state and
     drops the ?p= handoff so the profile view is empty until the user onboards
     again. (Wiring a redirect to the onboarding URL is a follow-up.) */
  function restart() { Store.reset(); location.href = location.pathname; }

  global.App = { start };
  start();
})(window);
