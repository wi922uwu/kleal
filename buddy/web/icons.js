/* =============================================================================
   icons.js — shared inline-SVG icon set (stroke 1.8, currentColor).
   Exposes a global `ICON` map used by the tab-bar and chat input.
   ============================================================================= */
(function (global) {
  const s = (inner, w) =>
    `<svg width="${w || 24}" height="${w || 24}" viewBox="0 0 24 24" fill="none" ` +
    `stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;

  global.ICON = {
    intents: s('<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>'),
    search: s('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>'),
    messages: s('<path d="M4 5h16a1 1 0 011 1v10a1 1 0 01-1 1H9l-4 4V6a1 1 0 011-1z"/>'),
    profile: s('<circle cx="12" cy="8" r="3.6"/><path d="M5.5 20a6.5 6.5 0 0113 0"/>'),
    spark: '<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17l-1.9-5.1L4.5 10l5.6-1.4L12 3z"/></svg>',
    mic: s('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0014 0M12 18v3"/>', 22),
    send: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>',
  };
})(window);
