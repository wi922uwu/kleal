import { T, dateLocale } from './i18n';

export type Product = { id: 'plus_monthly' | 'plus_annual'; period: 'month' | 'year'; referencePriceCents: number; currency: string };
export type FoundationMembership = {
  ok: true; state: 'free' | 'preview' | 'expired'; plan: 'free' | 'plus'; source: 'preview' | 'none';
  serverTime: number; previewStartedAt: number | null; expiresAt: number | null;
  canStartPreview: boolean; previewEnabled: boolean; previewDays: number;
  purchaseAvailable: false; restoreAvailable: false; enforcementEnabled: false; phase: 'foundation'; products: Product[];
};
export type MembershipV2 = {
  ok: true; version: 2; phase: 'phase2a'; state: 'free' | 'preview' | 'plus'; plan: 'free' | 'plus';
  serverTime: number; previewStartedAt: number | null; expiresAt: number | null;
  plusExpiresAt?: number | null;
  entitlementSources?: { source: 'preview' | 'manual' | 'paid'; expiresAt: number }[];
  previewEligible: boolean; previewNotice: boolean; enforcementEnabled: true;
  purchaseAvailable: false; restoreAvailable: false;
  permissions: { publishSearch: boolean; initiateChat: boolean; reply: true; groupChat: true; manualCoordination: true; basicFilters: true };
  usage: { activeSearches: number; initiatedChats: number };
  limits: { activeSearches: number | null; initiatedChats: number | null };
  reasons: { publishSearch: string | null; initiateChat: string | null };
  blockerIds: { searches: string[]; chats: string[] };
  chatBlockers?: {sessionId:string;peerId:string;peerName:string}[];
  recoverableGroups?: {gid:string;title:string;model:'legacy'}[];
  searches: { id: string; state: 'active' | 'paused' | 'draft'; title: string; publishedAt: number | null }[];
  keepSearchId: string | null;
};
export type Membership = FoundationMembership | MembershipV2;

export function isMembershipV2(value: unknown): value is MembershipV2 {
  const v = value as MembershipV2 | null;
  return !!v && v.ok === true && v.version === 2 && v.phase === 'phase2a'
    && ['free','preview','plus'].includes(v.state) && v.plan === (v.state === 'free' ? 'free' : 'plus')
    && Number.isFinite(v.serverTime) && v.enforcementEnabled === true
    && v.purchaseAvailable === false && v.restoreAvailable === false
    && typeof v.previewEligible === 'boolean' && typeof v.previewNotice === 'boolean'
    && (v.entitlementSources === undefined && v.plusExpiresAt === undefined || Array.isArray(v.entitlementSources)
      && v.entitlementSources.every(s => !!s && ['preview','manual','paid'].includes(s.source)
        && Number.isFinite(s.expiresAt) && s.expiresAt > v.serverTime)
      && new Set(v.entitlementSources.map(s => s.source)).size === v.entitlementSources.length
      && v.entitlementSources.every(s => s.source !== 'preview' || s.expiresAt === v.expiresAt)
      && v.entitlementSources.some(s => s.source === 'preview') === (v.state === 'preview')
      && v.plusExpiresAt === (v.entitlementSources.length ? Math.max(...v.entitlementSources.map(s => s.expiresAt)) : null)
      && (v.entitlementSources.length > 0) === (v.plan === 'plus'))
    && (v.previewStartedAt === null ? v.expiresAt === null : Number.isFinite(v.previewStartedAt)
      && Number.isFinite(v.expiresAt) && Number(v.expiresAt) - v.previewStartedAt === 1209600)
    && (v.state !== 'preview' || Number(v.expiresAt) > v.serverTime)
    && !!v.permissions && ['publishSearch','initiateChat'].every(k => typeof (v.permissions as any)[k] === 'boolean')
    && ['reply','groupChat','manualCoordination','basicFilters'].every(k => (v.permissions as any)[k] === true)
    && !!v.usage && [v.usage.activeSearches,v.usage.initiatedChats].every(n => Number.isInteger(n) && n >= 0)
    && !!v.limits && [v.limits.activeSearches,v.limits.initiatedChats].every(n => n === (v.plan==='free' ? 1 : null))
    && !!v.reasons && v.reasons.publishSearch === (v.permissions.publishSearch ? null : 'search_quota')
    && v.reasons.initiateChat === (v.permissions.initiateChat ? null : 'chat_quota') && !!v.blockerIds
    && [v.blockerIds.searches,v.blockerIds.chats].every(a => Array.isArray(a) && a.every(x => typeof x === 'string'))
    && (v.chatBlockers===undefined || Array.isArray(v.chatBlockers) && v.chatBlockers.every(b=>!!b && typeof b.peerId==='string' && !!b.peerId
      && typeof b.peerName==='string' && v.blockerIds.chats.includes(b.sessionId)))
    && (v.recoverableGroups===undefined || Array.isArray(v.recoverableGroups) && v.recoverableGroups.every(g=>!!g && typeof g.gid==='string'
      && !!g.gid && typeof g.title==='string' && g.model==='legacy'))
    && (v.keepSearchId===null || typeof v.keepSearchId==='string')
    && Array.isArray(v.searches) && v.searches.every(r => !!r && typeof r.id === 'string' && typeof r.title === 'string'
      && (r.publishedAt===null || Number.isFinite(r.publishedAt)) && ['active','paused','draft'].includes(r.state));
}

/** In phase 1 a malformed/future response must never look like a successful payment. */
export function isMembership(value: unknown): value is Membership {
  if (isMembershipV2(value)) return true;
  const v = value as FoundationMembership | null;
  return !!v && v.ok === true && ['free', 'preview', 'expired'].includes(v.state)
    && v.plan === (v.state === 'preview' ? 'plus' : 'free')
    && v.source === (v.state === 'free' ? 'none' : 'preview')
    && Number.isFinite(v.serverTime) && v.phase === 'foundation'
    && v.purchaseAvailable === false && v.restoreAvailable === false && v.enforcementEnabled === false
    && typeof v.canStartPreview === 'boolean' && typeof v.previewEnabled === 'boolean'
    && v.previewDays === 14
    && (!v.canStartPreview || (v.previewEnabled && v.state === 'free'))
    && (v.state === 'free' ? v.expiresAt === null && v.previewStartedAt === null
      : Number.isFinite(v.expiresAt) && Number.isFinite(v.previewStartedAt)
        && Number(v.expiresAt) > Number(v.previewStartedAt)
        && (v.state !== 'preview' || (v.previewEnabled && Number(v.expiresAt) > v.serverTime)))
    && Array.isArray(v.products) && v.products.length === 2
    && v.products.every((p, i) => !!p && p.id === ['plus_monthly', 'plus_annual'][i]
      && p.period === ['month', 'year'][i] && p.currency === 'EUR'
      && Number.isInteger(p.referencePriceCents) && p.referencePriceCents > 0);
}

export function referencePrice(product: Product): string {
  return new Intl.NumberFormat(dateLocale(), { style: 'currency', currency: product.currency })
    .format(product.referencePriceCents / 100);
}

export function expiresLabel(seconds: number): string {
  return new Date(seconds * 1000).toLocaleDateString(dateLocale(), { day: 'numeric', month: 'long', year: 'numeric' });
}

export const PLUS = {
  title: () => 'Kleal Plus',
  setting: () => T('Тариф и Plus Preview', 'Plan and Plus Preview', 'Plan y Plus Preview'),
  lead: () => T('Больше возможностей для твоих планов', 'More possibilities for your plans', 'Más posibilidades para tus planes'),
  stage: () => T('Без оплаты', 'No payment', 'Sin pago'),
  stageNote: () => T('Сейчас проверяем тарифный flow. Preview меняет тестовый статус аккаунта; новые лимиты и платные инструменты ещё не включены.',
    'We are testing the membership flow. Preview changes your test membership status; new limits and paid tools are not enabled yet.',
    'Estamos probando el flujo de planes. Preview cambia el estado de prueba; los nuevos límites y herramientas de pago aún no están habilitados.'),
  free: () => T('Сейчас Free', 'Currently Free', 'Actualmente Free'),
  preview: () => T('Plus Preview активен', 'Plus Preview is active', 'Plus Preview está activo'),
  active: () => T('Plus активен', 'Plus is active', 'Plus está activo'),
  expired: () => T('Preview завершён · Free', 'Preview ended · Free', 'Preview finalizado · Free'),
  until: (date: string) => T(`До ${date}`, `Until ${date}`, `Hasta el ${date}`),
  plusUntil: (date: string) => T(`Plus до ${date}`, `Plus until ${date}`, `Plus hasta el ${date}`),
  manualSource: () => T('Plus предоставлен командой Kleal', 'Plus granted by the Kleal team', 'Plus concedido por el equipo de Kleal'),
  previewSource: () => T('14-дневный Plus Preview', '14-day Plus Preview', 'Plus Preview de 14 días'),
  paidSource: () => T('Подписка Plus', 'Plus subscription', 'Suscripción Plus'),
  endedOn: (date: string) => T(`Preview завершён ${date}`, `Preview ended on ${date}`, `Preview finalizó el ${date}`),
  preserved: () => T('Встречи, переписки и безопасность остаются доступными. Автоматического списания нет.',
    'Meetups, chats and safety remain available. There is no automatic charge.',
    'Las quedadas, los chats y la seguridad siguen disponibles. No hay cobro automático.'),
  compare: () => T('Планируемые тарифы', 'Proposed plans', 'Planes propuestos'),
  monthly: () => T('Месяц', 'Monthly', 'Mensual'),
  annual: () => T('Год', 'Annual', 'Anual'),
  period: (p: Product['period']) => p === 'month' ? T('за месяц', 'per month', 'al mes') : T('за год целиком', 'for the full year', 'por el año completo'),
  priceNote: () => T('Ориентиры из предложения. Это не предложение оплаты: окончательная цена будет показана магазином перед покупкой.',
    'Reference prices from the proposal, not a checkout offer. The store will show the final price before purchase.',
    'Precios de referencia de la propuesta, no una oferta de pago. La tienda mostrará el precio final antes de comprar.'),
  features: () => T('В планах Plus: параллельные интенты и личные диалоги. Качество подбора и безопасность одинаковы для всех.',
    'Planned for Plus: parallel intents and personal chats. Matching quality and safety are the same for everyone.',
    'Previsto para Plus: propuestas y chats personales simultáneos. La calidad de las coincidencias y la seguridad son iguales para todos.'),
  start: () => T('Попробовать Preview · 14 дней', 'Try Preview · 14 days', 'Probar Preview · 14 días'),
  consent: () => T('Начать 14 дней сейчас?', 'Start your 14 days now?', '¿Empezar los 14 días ahora?'),
  consentNote: () => T('Карта не нужна. Срок считается сервером с этого момента, повторный запуск не продлевает его. После Preview вернётся Free без списания.',
    'No card required. The server starts the clock now; restarting will not extend it. You return to Free afterwards, with no charge.',
    'No necesitas tarjeta. El servidor cuenta desde ahora; reiniciarlo no amplía el plazo. Después volverás a Free sin cargos.'),
  confirm: () => T('Начать без оплаты', 'Start without payment', 'Empezar sin pagar'),
  cancel: () => T('Не сейчас', 'Not now', 'Ahora no'),
  purchase: () => T('Покупка пока недоступна', 'Purchases are not available yet', 'Compras aún no disponibles'),
  restore: () => T('Восстановление покупок появится после подключения магазина', 'Purchase restoration will be available when a store is connected', 'La restauración de compras estará disponible al conectar una tienda'),
  unavailable: () => T('Preview ещё не включён на этом сервере.', 'Preview is not enabled on this server yet.', 'Preview aún no está habilitado en este servidor.'),
  loading: () => T('Проверяем тариф…', 'Checking your plan…', 'Comprobando tu plan…'),
  retry: () => T('Обновить статус', 'Refresh status', 'Actualizar estado'),
  error: () => T('Не удалось проверить тариф. Повтори запрос.', 'Could not check your plan. Retry the request.', 'No se pudo comprobar tu plan. Reintenta la solicitud.'),
  login: () => T('Войди в аккаунт, чтобы проверить тариф.', 'Sign in to check your plan.', 'Inicia sesión para comprobar tu plan.'),
  back: () => T('Вернуться', 'Go back', 'Volver'),
};

export const MONETIZATION = {
  legacyRecovery: () => T('У группы нет организатора. Освободи поисковый слот и прими роль здесь.',
    'This group has no organizer. Free a search slot and take the role here.',
    'Este grupo no tiene organizador. Libera un espacio de búsqueda y acepta el rol aquí.'),
  recoverGroup: () => T('Стать организатором','Become organizer','Ser organizador'),
  previewInfo: () => T('14 дней Plus начнутся после первой публикации, принятия приглашения или вступления. Карта не нужна; автоматического списания нет.',
    '14 days of Plus begin after your first publication, accepted invitation or admission. No card or automatic charge.',
    'Los 14 días de Plus empiezan con tu primera publicación, invitación aceptada o incorporación. Sin tarjeta ni cobro automático.'),
  previewStarted: () => T('Plus Preview начался', 'Plus Preview has started', 'Plus Preview ha comenzado'),
  freeRules: () => T('Free: один активный собственный поиск и один инициативный личный чат. Ответы, группы, фильтры и договорённости доступны.',
    'Free: one active search of your own and one initiated personal chat. Replies, groups, filters and agreed plans remain available.',
    'Free: una búsqueda propia activa y un chat personal iniciado. Respuestas, grupos, filtros y planes acordados siguen disponibles.'),
  plusRules: () => T('Plus и Preview позволяют вести несколько поисков и личных чатов. Правила безопасности и вместимость групп одинаковы для всех.',
    'Plus and Preview support multiple searches and personal chats. Safety and group capacity are the same for everyone.',
    'Plus y Preview permiten varias búsquedas y chats personales. La seguridad y capacidad de los grupos son iguales para todos.'),
  searchQuota: () => T('У тебя уже есть активный поиск. Его можно приостановить или заменить новым.',
    'You already have an active search. Pause it or replace it with the new one.',
    'Ya tienes una búsqueda activa. Puedes pausarla o reemplazarla por la nueva.'),
  chatQuota: () => T('У тебя уже есть инициативный чат. Заверши его, чтобы начать новый. История и ответы остаются доступны.',
    'You already have an initiated chat. End it to start another. History and replies remain available.',
    'Ya tienes un chat iniciado. Termínalo para iniciar otro. El historial y las respuestas siguen disponibles.'),
  organizerQuota: () => T('Новый организатор уже ведёт поиск. Нужно освободить слот или выбрать другого участника. Роль пока не изменена.',
    'The new organizer already has a search. Free a slot or choose another member. The role has not changed.',
    'El nuevo organizador ya tiene una búsqueda. Libera un espacio o elige a otro participante. El rol no ha cambiado.'),
  freeSlot: () => T('Освободить слот', 'Free a slot', 'Liberar un espacio'),
  chooseOther: () => T('Выбрать другого организатора', 'Choose another organizer', 'Elegir otro organizador'),
  swap: () => T('Заменить текущий поиск', 'Replace current search', 'Reemplazar búsqueda actual'),
  swapConfirm: () => T('Текущий поиск будет приостановлен. Переписки, участники и планы сохранятся.',
    'Your current search will be paused. Chats, members and plans will be preserved.',
    'Tu búsqueda actual se pausará. Los chats, participantes y planes se conservarán.'),
  keep: () => T('Оставить после Plus', 'Keep after Plus', 'Mantener al finalizar Plus'),
  pause: () => T('Приостановить поиск', 'Pause search', 'Pausar búsqueda'),
  searchActive: () => T('Поиск активен', 'Search is active', 'Búsqueda activa'),
  searchPaused: () => T('Поиск приостановлен', 'Search is paused', 'Búsqueda pausada'),
  searchDraft: () => T('Черновик поиска', 'Search draft', 'Borrador de búsqueda'),
  resumeSearch: () => T('Возобновить поиск', 'Resume search', 'Reanudar búsqueda'),
  resume: () => T('Продолжить исходное действие', 'Continue original action', 'Continuar acción original'),
  returnToAction: () => T('Вернуться к исходному действию', 'Return to original action', 'Volver a la acción original'),
  cancelAction: () => T('Отменить действие', 'Cancel action', 'Cancelar acción'),
  continue: () => T('Продолжить', 'Continue', 'Continuar'),
  unknown: () => T('Права сейчас не удалось проверить. Повтори действие.', 'Could not verify access. Retry this action.', 'No se pudo verificar el acceso. Reintenta la acción.'),
};

/** Render server state, never interpret a past Preview expiry as a Free/Plus deadline. */
export function membershipPresentation(data: Membership) {
  const v2 = isMembershipV2(data);
  const expired = data.state === 'expired' || (data.state === 'free' && data.previewStartedAt !== null
    && data.expiresAt !== null && data.expiresAt <= data.serverTime);
  return {
    status: data.state === 'plus' ? PLUS.active() : data.state === 'preview' ? PLUS.preview()
      : expired ? PLUS.expired() : PLUS.free(),
    notice: v2 ? (data.state === 'free' && data.previewEligible && data.previewStartedAt === null
      ? MONETIZATION.previewInfo() : null) : PLUS.stageNote(),
    timing: data.expiresAt === null ? null : data.state === 'preview' ? PLUS.until(expiresLabel(data.expiresAt))
      : expired ? PLUS.endedOn(expiresLabel(data.expiresAt)) : null,
    plusTiming: v2 && data.plusExpiresAt ? PLUS.plusUntil(expiresLabel(data.plusExpiresAt)) : null,
    sources: v2 ? (data.entitlementSources || []).map(s => s.source === 'manual' ? PLUS.manualSource()
      : s.source === 'preview' ? PLUS.previewSource() : PLUS.paidSource()) : [],
  };
}

export function searchStateLabel(state: MembershipV2['searches'][number]['state']) {
  return state === 'active' ? MONETIZATION.searchActive()
    : state === 'paused' ? MONETIZATION.searchPaused() : MONETIZATION.searchDraft();
}

/** An unseen grant may already have expired while the app was closed. */
export function previewNoticePresentation(data: MembershipV2) {
  if (!data.previewNotice || data.previewStartedAt === null) return null;
  const view = membershipPresentation(data);
  return {
    title: data.state === 'preview' ? MONETIZATION.previewStarted() : view.status,
    message: [view.timing, PLUS.preserved()].filter(Boolean).join('\n\n'),
  };
}
