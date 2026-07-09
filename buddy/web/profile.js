/* =============================================================================
   profile.js — the Profile tab.

   Reuses the full profile card app (kleal_profile, :7073) — Overview, Interests,
   Social Style, Availability & Places, Goals, Safety & Privacy toggles, matching
   permissions, Agent Memory — by embedding it in an iframe, passing the original
   ?p= handoff (Store.rawP) so all profile sections + settings live in one place.

   Falls back to a thin read-only summary if no card URL is configured
   (GET /buddy/config -> {profile_url}).

   Exposes a global `renderProfile(container, onRestart)`.
   ============================================================================= */
(function (global) {
  const esc = s => String(s == null ? '' : s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const card = (title, valueHTML) =>
    `<div class="pcard"><div class="pt">${esc(title)}</div><div class="pv">${valueHTML}</div></div>`;

  /* Fallback: a compact read-only summary built from the mapped profile. */
  function thinCard(container, onRestart) {
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

  function renderProfile(container, onRestart) {
    container.innerHTML = '<div class="empty"><div>Loading profile…</div></div>';
    fetch('/buddy/config')
      .then(r => r.json())
      .then(cfg => {
        const url = cfg && cfg.profile_url;
        if (url && Store.rawP) {
          const src = url.replace(/\/$/, '') + '/?p=' + Store.rawP;   // rawP is already URL-encoded
          container.innerHTML =
            `<iframe title="Profile" src="${src}" style="flex:1;border:0;width:100%;height:100%"></iframe>`;
        } else {
          thinCard(container, onRestart);
        }
      })
      .catch(() => thinCard(container, onRestart));
  }

  global.renderProfile = renderProfile;
})(window);
