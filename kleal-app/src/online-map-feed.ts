/**
 * Privacy boundary between the backend online map-feed and OnlineIntentGlobe.
 *
 * The globe adapter intentionally accepts explicit country fields from several row shapes. A
 * backend projection can therefore erase whether a country was confirmed or inferred from city,
 * area, coordinates, IP, or locale. Until the backend contract guarantees confirmed-only country
 * facts, this boundary requires an explicit trusted provenance and strips every untrusted country
 * field. The intent remains visible in the globe's unknown-location list.
 */

const TRUSTED_COUNTRY_SOURCES = new Set(['confirmed_profile_country']);

const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};

const sourceOf = (row: Record<string, unknown>) =>
  String(row.countrySource ?? row.country_source ?? '').trim().toLowerCase();

const withoutCountry = (value: Record<string, unknown>) => {
  const next = { ...value };
  delete next.country;
  delete next.countryCode;
  delete next.country_code;
  return next;
};

export function confirmedOnlineCountryRows(rows: unknown[]): unknown[] {
  return (Array.isArray(rows) ? rows : []).map((raw) => {
    const row = record(raw);
    const trusted = row.locationAvailable === true && TRUSTED_COUNTRY_SOURCES.has(sourceOf(row));
    if (trusted) return raw;
    const safe = withoutCountry(row);
    safe.locationAvailable = false;
    if (row.intent && typeof row.intent === 'object' && !Array.isArray(row.intent)) {
      safe.intent = withoutCountry(record(row.intent));
    }
    return safe;
  });
}
