/** Deterministic rows for adapter tests and the isolated native QA harness. */
export const ONLINE_INTENT_GLOBE_FIXTURES: unknown[] = [
  {
    intentId: 'es-online-11', title: 'Spanish conversation', who: 'Marta',
    topics: ['Spanish'], mode: 'online', format: '1:1', countryCode: 'ES',
    lat: 1.2345, lon: 2.3456, ipCountryCode: 'DE', status: 'active',
  },
  {
    intentId: 'es-hybrid-group', title: 'Remote running club', who: 'Leo',
    topics: ['Running'], mode: 'hybrid', format: 'group', groupSize: 8, country: 'Spain',
    lat: 55.7558, lon: 37.6173,
  },
  {
    id: 'us-online-group', title: 'Indie game night', who: 'Alex',
    topics: ['Games'], mode: 'remote', size: 'large', min_total: 6, max_total: 20,
    country: { code: 'US', name: 'United States' },
  },
  {
    intentId: 'jp-hybrid-11', title: 'Sketch together', who: 'Aoi',
    topics: ['Art'], intent: { mode: 'hybrid', format: '1:1', country_code: 'JP' },
  },
  {
    intentId: 'unknown-online', title: 'Open source pairing', who: 'Sam',
    topics: ['Programming'], mode: 'online', format: '1:1',
    ipCountryCode: 'CA', timezone: 'America/Toronto', lat: 43.6532, lon: -79.3832,
  },
  { intentId: 'offline-hidden', mode: 'offline', countryCode: 'PT', title: 'Local walk' },
  { intentId: 'closed-hidden', mode: 'online', countryCode: 'FR', status: 'closed', title: 'Closed' },
  { intentId: 'deleted-hidden', mode: 'hybrid', countryCode: 'DE', deleted: true, title: 'Deleted' },
  { mode: 'online', countryCode: 'IT', title: 'Missing id' },
];

export function largeOnlineIntentGlobeFixture(count = 2_000): unknown[] {
  return Array.from({ length: count }, (_, index) => ({
    intentId: `bulk-${index}`,
    title: `Intent ${index}`,
    who: `Person ${index}`,
    mode: index % 5 === 0 ? 'hybrid' : 'online',
    format: index % 3 === 0 ? 'group' : '1:1',
    groupSize: index % 3 === 0 ? 12 : undefined,
    countryCode: index % 2 === 0 ? 'ES' : 'US',
    status: 'active',
  }));
}
