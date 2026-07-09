/* =============================================================================
   profile.js — the Profile tab.

   Read-only overview of the profile handed over by kleal_v2 onboarding: summary,
   basics, interests (with roles), languages, location and safety.

   Exposes a global `renderProfile(container, onRestart)`.
   ============================================================================= */
(function (global) {
  const esc = s => String(s == null ? '' : s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const card = (title, valueHTML) =>
    `<div class="pcard"><div class="pt">${esc(title)}</div><div class="pv">${valueHTML}</div></div>`;

  function renderProfile(container, onRestart) {
    const p = Store.profile;
    const ints = (p.interests || []).map(i => `${esc(i.name)}${i.role ? ' · ' + esc(i.role) : ''}`).join('<br>') || '—';
    const langs = (p.languages || []).join(', ') || '—';
    const areas = (p.areas || []).join(', ');
    const loc = [esc(p.city || ''), areas ? esc(areas) : '', p.maxTravelKm ? 'within ' + p.maxTravelKm + ' km' : '']
      .filter(Boolean).join(' · ') || '—';
    const sf = p.safety || {}, pm = p.permissions || {};
    const safety = [
      sf.publicPlacesOnly ? 'public places by default' : null,
      pm.useProfileForMatching ? 'matching on' : null,
      pm.allowAdjacent ? 'adjacent suggestions on' : null,
    ].filter(Boolean).join(' · ') || '—';
    const basics = [esc(p.name || '—'), p.age ? p.age : null].filter(Boolean).join(', ');

    container.innerHTML =
      `<div class="scr-head"><h2>My Profile</h2><p>What Kleal knows about you</p></div>
       <div class="scr-body">
         ${p.summary ? `<div class="psum">${esc(p.summary)}</div>` : ''}
         ${card('You', basics)}
         ${card('Interests', ints)}
         ${card('Languages', langs)}
         ${card('Location', loc)}
         ${card('Safety & permissions', safety)}
         <button class="link" id="restart" style="align-self:center;margin-top:6px">Restart onboarding</button>
       </div>`;

    const rb = container.querySelector('#restart');
    if (rb && onRestart) rb.onclick = onRestart;
  }

  global.renderProfile = renderProfile;
})(window);
