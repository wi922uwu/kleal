import { T, dateLocale } from './i18n';

export type Product = { id: 'plus_monthly' | 'plus_annual'; period: 'month' | 'year'; referencePriceCents: number; currency: string };
export type Membership = {
  ok: true; state: 'free' | 'preview' | 'expired'; plan: 'free' | 'plus'; source: 'preview' | 'none';
  serverTime: number; previewStartedAt: number | null; expiresAt: number | null;
  canStartPreview: boolean; previewEnabled: boolean; previewDays: number;
  purchaseAvailable: false; restoreAvailable: false; enforcementEnabled: false; phase: 'foundation'; products: Product[];
};

/** In phase 1 a malformed/future response must never look like a successful payment. */
export function isMembership(value: unknown): value is Membership {
  const v = value as Membership | null;
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
  stage: () => T('Тестовый этап · без списаний', 'Test phase · no charges', 'Fase de prueba · sin cargos'),
  stageNote: () => T('Сейчас проверяем тарифный flow. Preview меняет тестовый статус аккаунта; новые лимиты и платные инструменты ещё не включены.',
    'We are testing the membership flow. Preview changes your test membership status; new limits and paid tools are not enabled yet.',
    'Estamos probando el flujo de planes. Preview cambia el estado de prueba; los nuevos límites y herramientas de pago aún no están habilitados.'),
  free: () => T('Сейчас Free', 'Currently Free', 'Actualmente Free'),
  preview: () => T('Plus Preview активен', 'Plus Preview is active', 'Plus Preview está activo'),
  expired: () => T('Preview завершён · Free', 'Preview ended · Free', 'Preview finalizado · Free'),
  until: (date: string) => T(`До ${date}`, `Until ${date}`, `Hasta el ${date}`),
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
  error: () => T('Не удалось проверить тариф. Повтори запрос — повторного списания не будет.', 'Could not check your plan. Retry safely; you will not be charged.', 'No se pudo comprobar tu plan. Puedes reintentar sin cargos.'),
  login: () => T('Войди в аккаунт, чтобы проверить тариф.', 'Sign in to check your plan.', 'Inicia sesión para comprobar tu plan.'),
  back: () => T('Вернуться', 'Go back', 'Volver'),
};
