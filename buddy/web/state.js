/* =============================================================================
   state.js — profile state for the app interface (option A).

   The profile is produced by kleal_v2 onboarding and handed over in the URL as
   ?p=<base64 utf-8 json> (the same handoff kleal_v2 already uses for the profile
   card). Here we decode it, map the kleal_v2 shape to Buddy's, persist it, and
   POST it to /buddy/onboard so the user becomes matchable. Falls back to a
   previously stored profile on a plain reload.

   Exposes a global `Store`.
   ============================================================================= */
(function (global) {
  const LS_PROFILE = 'kleal_profile', LS_UID = 'kleal_uid';

  let uid = localStorage.getItem(LS_UID);
  if (!uid) { uid = 'usr_' + Math.random().toString(36).slice(2, 10); localStorage.setItem(LS_UID, uid); }

  // Raw ?p= value (URL-encoded base64) — reused as-is to embed the full profile card
  // (kleal_profile expects the kleal_v2 shape, so we pass the original, not the mapped one).
  const rawP = ((/[?&]p=([^&]+)/.exec(location.search)) || [])[1] || localStorage.getItem('kleal_rawp') || '';

  /* Map the kleal_v2 onboarding profile → Buddy's flatter shape. */
  function mapOnboarding(v) {
    if (!v || typeof v !== 'object') return null;
    const geo = v.geo || {};
    const langs = (v.languages && v.languages.comfortable) || (Array.isArray(v.languages) ? v.languages : []);
    const explicit = (v.interests && v.interests.explicit) || [];
    const roles = (v.interests && v.interests.roles) || {};
    const perm = v.permissions || {};
    return {
      name: v.name || '', age: v.age || null, city: v.city || '',
      areas: geo.comfortableAreas || [], maxTravelKm: geo.maxDistanceKm || null,
      languages: Array.isArray(langs) ? langs : [],
      interests: explicit.map(n => ({ name: n, role: (roles && roles[n]) || 'discuss' })),
      safety: v.safety || {},
      permissions: { useProfileForMatching: !!perm.useProfileForMatching, allowAdjacent: perm.allowAdjacentMatches !== false },
      summary: v.summary || '',
    };
  }

  /* Decode ?p=<base64 utf-8 json> from the URL (kleal_v2 handoff). */
  function fromParam() {
    const m = /[?&]p=([^&]+)/.exec(location.search);
    if (!m) return null;
    try {
      const json = decodeURIComponent(escape(atob(decodeURIComponent(m[1]))));
      return mapOnboarding(JSON.parse(json));
    } catch (e) { return null; }
  }

  function load() { try { return JSON.parse(localStorage.getItem(LS_PROFILE) || 'null'); } catch (e) { return null; } }

  const handoff = fromParam();               // fresh profile from onboarding, if any
  const profile = handoff || load() || { name: '', interests: [], languages: [] };

  const Store = {
    uid, profile, rawP,
    fromHandoff: !!handoff,
    save() { localStorage.setItem(LS_PROFILE, JSON.stringify(this.profile)); },

    /* Persist to backend → user becomes matchable + summary refreshed. Non-blocking. */
    async sync() {
      try {
        const r = await fetch('/buddy/onboard', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: this.uid, profile: this.profile }),
        });
        const d = await r.json();
        if (d.summary) { this.profile.summary = d.summary; this.save(); }
      } catch (e) { /* keep local profile; UI works without the summary */ }
    },

    reset() { localStorage.removeItem(LS_PROFILE); this.profile = { name: '', interests: [], languages: [] }; },
  };

  // On a fresh handoff, persist locally + push to the backend (fire and forget).
  if (Store.fromHandoff) { Store.save(); Store.sync(); if (rawP) localStorage.setItem('kleal_rawp', rawP); }

  global.Store = Store;
})(window);
