import { api, getSession } from './api';
import { isMembership, Membership } from './monetization';

const PREFIX = '/api/onboarding/monetization';
export type MembershipView = { session: string; data: Membership | null; busy: boolean; error: 'network' | 'sign_in' | null };
type Transport = { get(): Promise<unknown>; start(): Promise<unknown> };

/** Per-screen controller: no persisted entitlement cache and no optimistic grant. */
export class MembershipClient {
  view: MembershipView = { session: '', data: null, busy: false, error: null };
  private generation = 0;
  private listeners = new Set<(v: MembershipView) => void>();
  constructor(private session = getSession, private transport: Transport = {
    get: () => api.get(PREFIX + '/v2/status'),
    start: () => api.post(PREFIX + '/preview', { consent: true }),
  }) {}
  subscribe(fn: (v: MembershipView) => void) { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; }
  private publish(v: MembershipView) { this.view = v; this.listeners.forEach((fn) => fn(v)); }
  dispose() {
    this.generation++;
    this.listeners.clear();
    // React StrictMode can mount effects again on the same controller instance.
    this.view = { session: '', data: null, busy: false, error: null };
  }
  async load() { return this.run(false); }
  async start() { return this.run(true); }
  private async run(start: boolean) {
    const session = this.session();
    if (this.view.busy && this.view.session === session) return false;
    const generation = ++this.generation;
    this.publish({ session, data: null, busy: !!session, error: session ? null : 'sign_in' });
    if (!session) return false;
    try {
      const value = await (start ? this.transport.start() : this.transport.get());
      if (!isMembership(value)) throw new Error('invalid membership response');
      if (generation === this.generation && session === this.session()) {
        this.publish({ session, data: value, busy: false, error: null });
        return true;
      }
    } catch (error) {
      if (generation === this.generation && session === this.session())
        this.publish({ session, data: null, busy: false, error: (error as { status?: number })?.status === 401 ? 'sign_in' : 'network' });
    }
    return false;
  }
}
