import type { ExplorePin } from './explore';

export type MapIntentMode = 'offline' | 'online' | 'hybrid';
export type MapIntentKind = 'one_to_one' | 'group';

export type MapFeedItem = {
  id: string;
  title: string;
  mode: MapIntentMode;
  kind: MapIntentKind;
  status: 'launched';
  address?: string;
  lat?: number;
  lng?: number;
  /** Transitional alias promised by the backend contract; `lng` remains canonical. */
  lon?: number;
  country?: string;
  countryCode?: string;
  count: number;
  owner: { id?: string; displayName: string; photo?: string };
  privacy: 'exact_intent_location' | 'country_only';
};

export type MapFeedResponse = {
  items?: unknown[];
  partial?: boolean;
  unavailableCount?: number;
};

export type OfflineIntentMapModel = {
  pins: ExplorePin[];
  partial: boolean;
  unavailableCount: number;
  rejectedCount: number;
};

const text = (value: unknown) => String(value ?? '').trim();

const number = (value: unknown): number | undefined => {
  if (value === '' || value === null || value === undefined) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
};

const validCoordinates = (lat: number | undefined, lon: number | undefined) =>
  lat !== undefined && lon !== undefined &&
  lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180 &&
  !(lat === 0 && lon === 0);

/**
 * Converts the privacy-safe backend map-feed contract into the existing production Map model.
 *
 * This is intentionally strict. Legacy explore rows have neither mode nor status and therefore
 * cannot be assumed to be public Offline intents. The adapter never falls back to profile/IP
 * coordinates, and it accepts only the explicitly published intent-address privacy class.
 */
export function buildOfflineIntentMapModel(payload: MapFeedResponse | null | undefined): OfflineIntentMapModel {
  const rows = Array.isArray(payload?.items) ? payload.items : [];
  const pins: ExplorePin[] = [];
  const seen = new Set<string>();
  let rejectedCount = 0;
  let missingCoordinates = 0;

  for (const raw of rows) {
    const row = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
    const id = text(row.id);
    const mode = text(row.mode).toLowerCase();
    const status = text(row.status).toLowerCase();
    const kind = text(row.kind).toLowerCase();
    const privacy = text(row.privacy).toLowerCase();

    if (!id || seen.has(id)) { rejectedCount += 1; continue; }
    if (mode !== 'offline' && mode !== 'hybrid') { rejectedCount += 1; continue; }
    if (status !== 'launched') { rejectedCount += 1; continue; }
    if (kind !== 'one_to_one' && kind !== 'group') { rejectedCount += 1; continue; }
    if (privacy !== 'exact_intent_location') { rejectedCount += 1; continue; }

    const lat = number(row.lat);
    const lon = number(row.lng) ?? number(row.lon);
    if (!validCoordinates(lat, lon)) {
      seen.add(id);
      missingCoordinates += 1;
      continue;
    }

    const owner = (row.owner && typeof row.owner === 'object' ? row.owner : {}) as Record<string, unknown>;
    const title = text(row.title);
    const address = text(row.address);
    const count = Math.max(1, Math.trunc(number(row.count) ?? 1));
    const displayName = text(owner.displayName);

    seen.add(id);
    pins.push({
      id,
      who: displayName,
      photo: text(owner.photo) || undefined,
      verified: false,
      topics: title ? [title] : [],
      title,
      when: '',
      area: address,
      lat: lat as number,
      lon: lon as number,
      mode: mode as 'offline' | 'hybrid',
      kind: kind as MapIntentKind,
      count,
    });
  }

  const serverUnavailable = Math.max(0, Math.trunc(number(payload?.unavailableCount) ?? 0));
  const unavailableCount = Math.max(serverUnavailable, missingCoordinates);
  return {
    pins,
    partial: Boolean(payload?.partial) || unavailableCount > 0,
    unavailableCount,
    rejectedCount,
  };
}
