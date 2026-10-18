/** Session + semantic operation scoped retries. Never persists account tokens or grants. */
export type PendingAction = {
  session: string; key: string; operation: string; payload: Record<string, any>;
  reason?: string; blockerIds?: string[];
  patch?: { swapSearchId?: string }; promise?: Promise<any>; cancel?: () => void;
  persistenceOptional?: boolean;
  subscribers?: number;
};
type Metadata = { account: string; signature: string; key: string; created: number; acknowledged?: boolean; patch?: { swapSearchId?: string } };
type Persistence = { account: () => Promise<string>; read: () => Promise<string | null>; write: (value:string) => Promise<void> };
// SHA-256 fingerprints bind a retry to the exact original payload without storing
// its message, profile, bearer token or grant. This is not used for authentication.
export function fingerprint(text:string):string {
  const bytes=Array.from(new TextEncoder().encode(text)), bits=bytes.length*8;
  bytes.push(128); while (bytes.length%64!==56) bytes.push(0);
  for (let i=7;i>=0;i--) bytes.push(i<4 ? (bits >>> (i*8))&255 : 0);
  const k:number[]=[], h:number[]=[];
  for(let n=2;k.length<64;n++) {
    let prime=true; for(let d=2;d*d<=n;d++) if(n%d===0) { prime=false;break; }
    if(prime) { if(h.length<8) h.push((Math.sqrt(n)%1*4294967296)|0);k.push((Math.cbrt(n)%1*4294967296)|0); }
  }
  const rr=(n:number,b:number)=>(n>>>b)|(n<<(32-b));
  for(let p=0;p<bytes.length;p+=64) {
    const w:number[]=[];
    for(let i=0;i<16;i++) w[i]=(bytes[p+4*i]<<24)|(bytes[p+4*i+1]<<16)|(bytes[p+4*i+2]<<8)|bytes[p+4*i+3];
    for(let i=16;i<64;i++) w[i]=(w[i-16]+(rr(w[i-15],7)^rr(w[i-15],18)^(w[i-15]>>>3))+w[i-7]+(rr(w[i-2],17)^rr(w[i-2],19)^(w[i-2]>>>10)))|0;
    let [a,b,c,d,e,f,g,j]=h;
    for(let i=0;i<64;i++) {
      const t=(j+(rr(e,6)^rr(e,11)^rr(e,25))+((e&f)^(~e&g))+k[i]+w[i])|0;
      const u=((rr(a,2)^rr(a,13)^rr(a,22))+((a&b)^(a&c)^(b&c)))|0;
      j=g;g=f;f=e;e=(d+t)|0;d=c;c=b;b=a;a=(t+u)|0;
    }
    [a,b,c,d,e,f,g,j].forEach((v,i)=>{h[i]=(h[i]+v)|0;});
  }
  return h.map(v=>(v>>>0).toString(16).padStart(8,'0')).join('');
}
function canonical(value:any):string {
  return JSON.stringify(value,(_key,v)=>v && typeof v==='object' && !Array.isArray(v)
    ? Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])) : v);
}
export class PendingActions {
  private session = '';
  private entries = new Map<string, PendingAction>();
  private metadata: Metadata[] = [];
  private loaded?: Promise<void>;
  private writes: Promise<void> = Promise.resolve();
  private bindings = new Map<PendingAction,Metadata>();
  constructor(private identity: () => string, private nextId = () => `cmd_${Date.now()}_${Math.random().toString(36).slice(2)}`, private persistence?: Persistence) {}
  private sync() {
    const current = this.identity();
    if (current !== this.session) { this.entries.clear(); this.bindings.clear(); this.session = current; }
    return current;
  }
  begin(operation: string, payload: Record<string, any>): PendingAction {
    const session = this.sync();
    const stable = { ...payload }; delete stable.commandId; delete stable.idem;
    const signature = operation + ':' + canonical(stable);
    let action = this.entries.get(signature);
    if (!action) {
      action = { session, operation, key: String(payload.client_id || this.nextId()), payload: stable };
      this.entries.set(signature, action);
    }
    return action;
  }
  async durable(operation:string,payload:Record<string,any>) {
    const session=this.sync();
    if(!this.persistence) return this.begin(operation,payload);
    if(!this.loaded) this.loaded=this.persistence.read().then(raw=>{
      const value=raw ? JSON.parse(raw) : [];
      if(!Array.isArray(value) || !value.every(x=>x && typeof x.account==='string' && /^[0-9a-f]{64}$/.test(x.signature)
        && typeof x.key==='string' && x.key.length>0 && Number.isFinite(x.created)
        && (x.acknowledged===undefined || typeof x.acknowledged==='boolean'))) throw new Error('invalid_retry_metadata');
      this.metadata=value;
    }).catch(error=>{
      // Временный отказ чтения не должен навсегда блокировать явные повторы.
      this.loaded=undefined;
      throw error;
    });
    await this.loaded;
    const account=await this.persistence.account();
    if(!account || session!==this.sync()) throw new Error('account_changed');
    const action=this.begin(operation,payload);
    if(action.promise) return action;
    const signature=fingerprint(operation+':'+canonical(action.payload));
    let metadata=this.metadata.find(x=>x.account===account && x.signature===signature && !x.acknowledged);
    if(!metadata) { metadata={account,signature,key:action.key,created:Date.now()};this.metadata.push(metadata); }
    action.key=metadata.key; action.patch=metadata.patch; this.bindings.set(action,metadata);
    // The API may already own an uncertainty-aware in-flight cancellation guard.
    action.cancel ||= ()=>{void this.finish(action).catch(()=>{});};
    await this.persist(); // Never dispatch before retry metadata is durable.
    return action;
  }
  async patch(action:PendingAction,patch:Record<string,any>) {
    if(typeof patch.swapSearchId==='string') action.patch={swapSearchId:patch.swapSearchId};
    const meta=this.bindings.get(action);if(meta) meta.patch=action.patch;
    try { if(this.bindings.has(action)) await this.persist(); else await this.writes; }
    catch(error) { if(!action.persistenceOptional) throw error; }
  }
  async protective(operation:string,payload:Record<string,any>) {
    const session=this.sync();
    try { return await this.durable(operation,payload); }
    catch(error) {
      if(!session || session!==this.sync()) throw new Error('account_changed');
      // Only the safety API allowlist calls this. Keep an already known uncertain
      // key in memory even if storage fails; publication never takes this path.
      const action=this.begin(operation,payload);action.persistenceOptional=true;return action;
    }
  }
  private persist(rows=()=>this.metadata.filter(row=>!row.acknowledged), committed?:()=>void) {
    if(!this.persistence) return Promise.resolve();
    // These fingerprints are unresolved operations, not a history cache. Neither
    // age nor later operations prove that a dispatched command did not commit.
    this.writes=this.writes.catch(()=>{}).then(async()=>{
      await this.persistence!.write(JSON.stringify(rows()));
      committed?.();
    });
    return this.writes;
  }
  current(action: PendingAction) { return !!this.sync() && action.session === this.session && [...this.entries.values()].includes(action); }
  async finish(action: PendingAction, acknowledge=false) {
    if (!this.current(action)) return false;
    const meta=this.bindings.get(action);
    if(meta) {
      // The acknowledgement is the durable commit point, not a best-effort
      // cleanup after resolving the caller. A crash after this write cannot
      // reuse the receipt for a later semantic action with the same payload.
      await this.persist(()=>this.metadata.filter(row=>row!==meta && !row.acknowledged)
        .concat(acknowledge?[{...meta,acknowledged:true}]:[]),()=>{meta.acknowledged=true;});
    }
    if (!this.current(action)) return false;
    for (const [key,value] of this.entries) if (value === action) this.entries.delete(key);
    this.bindings.delete(action);
    // Compact only after the acknowledgement committed. Failure here is safe:
    // the durable tombstone already prevents reuse after a process restart.
    if(meta && acknowledge) await this.persist(undefined,()=>{
      this.metadata=this.metadata.filter(row=>!row.acknowledged);
    }).catch(()=>{});
    return true;
  }
  clear() { this.entries.clear(); this.session = this.identity(); }
}

type Interaction = {
  before?: () => Promise<void>;
  blocked?: (action: PendingAction, retry: (patch?: Record<string, any>) => Promise<any>) => Promise<any>;
  changed?: () => void;
};
let interaction: Interaction = {};
export function configureMonetization(value: Interaction) { interaction = value; }
export const monetizationInteraction = () => interaction;

type ReturnOrigin = { pathname: string; params?: Record<string, any> };
type ReturnAction = { action: PendingAction; retry: (patch?: Record<string, any>) => Promise<any>; resolve: (v:any)=>void; reject:(e:Error)=>void; running?:Promise<any>; screen:string; leaving?:string; routeId:string; origin?:ReturnOrigin };
let returning: ReturnAction | null = null;
let recoverySequence = 0;
const retiredRecoveryIds = new Set<string>();
/** Remove only abandoned recovery overlays, retaining the current origin/key and
 * every ordinary route in the same order. A tab-away can leave overlays below it;
 * a new nonce must not accumulate another pair on every later recovery attempt. */
export function captureReturnOrigin(navigation:{getCurrentRoute:()=>unknown;getRootState:()=>any;resetRoot:(state:any)=>void}):ReturnOrigin | undefined {
  const origin=navigation.getCurrentRoute() as {key:string;name:string;params?:Record<string,unknown>} | undefined;
  if (!origin) return;
  const state=navigation.getRootState();
  if (state?.type==='stack' && state.routes.some((r:any)=>r.key===origin.key)) {
    const routes=state.routes.filter((r:any)=>r.key===origin.key || !retiredRecoveryIds.has(r.params?.recoveryId));
    if (routes.length!==state.routes.length) navigation.resetRoot({...state,routes,index:routes.findIndex((r:any)=>r.key===origin.key)});
    const remaining=new Set(routes.map((r:any)=>r.params?.recoveryId));
    for (const id of retiredRecoveryIds) if (!remaining.has(id)) retiredRecoveryIds.delete(id);
  }
  return {pathname:'/'+origin.name,params:{...origin.params}};
}
/** Only the recovery overlay has a second identity; ordinary screens stay singular. */
export function recoveryScreenIdentity(name:string, params:Record<string,unknown>) {
  return typeof params.recoveryId==='string' && params.recoveryId
    ? `${name}:recovery:${params.recoveryId}` : name;
}
export function deferAction(action: PendingAction, retry: ReturnAction['retry'], origin?:ReturnOrigin) {
  cancelReturnAction();
  return new Promise((resolve,reject) => { returning = { action,retry,resolve,reject,screen:'plus',origin,
    routeId:`recovery_${Date.now()}_${++recoverySequence}` }; });
}
export function returnActionRoute(session:string, screen:'plus'|'conversation') {
  if (!returnAction(session) || !returning) return null;
  return { pathname:screen==='plus'?'/plus' as const:'/conversation' as const, params:{recoveryId:returning.routeId} };
}
/** Explicit recovery navigation is the only transition that survives blur. */
export function navigateReturnAction(session:string, from:string, to:string) {
  if (!returnAction(session) || !returning || returning.screen!==from) return false;
  returning.leaving=from; returning.screen=to; return true;
}
export function recoveryAction(session:string,screen:string) {
  return returnAction(session) && returning?.screen===screen ? returning.action : null;
}
export function blurReturnAction(session:string,screen:string) {
  if (!returnAction(session) || !returning) return;
  if (returning.leaving===screen) { returning.leaving=undefined; return; }
  if (returning.screen===screen) cancelReturnAction();
}
export function returnAction(session: string) {
  if (returning && returning.action.session !== session) cancelReturnAction();
  return returning?.action || null;
}
export function cancelReturnAction() {
  const old = returning; returning = null;
  if (old) retiredRecoveryIds.add(old.routeId);
  old?.action.cancel?.();
  old?.reject(new Error('action_cancelled'));
}
export function abortableAction<T>(promise:Promise<T>,signal:AbortSignal|undefined,cancel:()=>void):Promise<T> {
  if(!signal) return promise;
  return new Promise((resolve,reject)=>{
    const abort=()=>{cancel();reject(new Error('action_cancelled'));};
    // Даже уже отменённая операция может завершиться ошибкой после await.
    promise.then(resolve,reject).finally(()=>signal.removeEventListener('abort',abort));
    if(signal.aborted) { abort(); return; }
    signal.addEventListener('abort',abort,{once:true});
  });
}
export async function resumeReturnAction(session: string, patch?: Record<string, any>, beforeResolve?: (origin?:ReturnOrigin) => void) {
  if (!returnAction(session) || !returning) return;
  const pending = returning;
  const result = await (pending.running ||= pending.retry(patch).finally(()=>{pending.running=undefined;}));
  if (returning === pending) { returning = null; retiredRecoveryIds.add(pending.routeId); beforeResolve?.(pending.origin); pending.resolve(result); }
  return result;
}

export function gatedOperation(path: string, payload: Record<string, any>) {
  return /^\/api\/agent\/(match|plan|confirm|expand|search-command|propose|message|thread-end|block|respond|ginvite-respond|gintent-(create|approve|role-respond|takeover|takeover-vote|takeover-back|leave)|group-(create|join|leave|recover)|[mg]plan-(cancel|status|feedback|respond|hold-answer))$/.test(path)
    || (path.endsWith('/intent-save') && payload.launched === true);
}

export function protectiveOperation(path: string, payload: Record<string, any>) {
  return /^\/api\/agent\/(thread-end|block|group-leave|gintent-leave|[mg]plan-cancel)$/.test(path)
    || path === '/api/agent/respond' && payload.decision === 'decline'
    || /^\/api\/agent\/(ginvite-respond|gintent-role-respond)$/.test(path) && payload.accept === false;
}
