/**
 * Кандидаты и приглашение — кадры O.12 (список), O.13 (полная карточка), O.14 (окно «Invite …?»).
 *
 * UX-каркас: копия и разбор данных здесь, вид в app/results.tsx и app/candidate.tsx.
 *
 * Честность против кадра. На борде у карточки есть занятие («Language teacher · native Spanish»)
 * и город («London») — в данных кандидата НЕТ ни занятия, ни города: ранжирование отдаёт интересы,
 * языки не всегда, расстояние в км и причины совпадения. Показывается то, что есть: вместо занятия
 * — вайб или первый интерес, вместо города — километры. Выдумывать профессию человеку нельзя —
 * это карточка живого человека, а не макет.
 */
import { T } from './i18n';

export const CANDS = {
  bestBadge: () => T('Лучший мэтч', 'Best match'),
  matchBadge: () => T('Мэтч', 'Match'),
  summaryLabel: () => T('Сводка Kleal:', 'Kleal summary:'),
  invite: () => T('Пригласить', 'Invite'),
  invited: () => T('Приглашение отправлено', 'Invite sent'),
  inviteFailed: () => T('Не отправилось. Попробуй ещё раз.', 'It didn’t send. Try again.'),

  /** Приписка приватности с кадра O.13, дословно. */
  privacyNote: () =>
    T(
      'Твой профиль видят только люди, которых предложил твой агент. Ты этим управляешь.',
      'Only people your agent recommended can see your profile. You’re in control.'
    ),

  /** Окно O.14. Текст с кадра; по-английски нейтральное they вместо she — имя бывает любым. */
  sheetTitle: (name: string) => T(`Пригласить ${name}?`, `Invite ${name}?`),
  sheetBody: (name: string) =>
    T(
      `${name} увидит твой интент и твой профиль. Если согласится — откроется чат; на бесплатном тарифе это единственный чат для этого интента.`,
      'They see your intent and your profile. If they join, a chat opens — on the free plan that is the one chat you get for this intent.'
    ),
  send: () => T('Отправить приглашение', 'Send the invite'),
  notYet: () => T('Пока нет', 'Not yet'),
};

/** Поля карточки, которые реально приходят из /api/agent/match. Всё остальное — не наше. */
export type Cand = {
  name?: string;
  age?: number;
  km?: number | null;
  photo?: string;
  vibe?: string;
  verified?: boolean;
  band?: string;
  band_ru?: string;
  band_en?: string;
  note?: string;
  why?: string;
  interests?: string[];
  reasons?: string[];
  reasons_ru?: string[];
  reasons_en?: string[];
  readiness_ru?: string;
  readiness_en?: string;
  profile_view?: any;
};

/** Подзаголовок карточки: вайб, а без него — первые интересы. Занятия в данных нет (см. шапку). */
export function candSubtitle(c: Cand, ru: boolean): string {
  const vibe = String(c.vibe || '').trim();
  if (vibe) return vibe;
  const ints = (c.interests || []).slice(0, 2).map(String);
  if (ints.length) return ints.map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join(' · ');
  return String((ru ? c.band_ru : c.band_en) || '');
}

/** Строка с меткой места: километры, когда они посчитаны. Города у кандидата нет. */
export function candWhere(c: Cand): string {
  return typeof c.km === 'number' && isFinite(c.km) ? `${c.km} km` : '';
}

/** «Сводка Kleal» на карточке — причины совпадения словами. Их пишет ранжирование, не мы. */
export function candSummary(c: Cand, ru: boolean): string {
  const reasons = (ru ? c.reasons_ru : c.reasons_en) || c.reasons || [];
  const bits = reasons.filter(Boolean).map(String);
  if (bits.length) {
    const line = bits.join(', ');
    return line.charAt(0).toUpperCase() + line.slice(1) + '.';
  }
  return String(c.why || c.note || '');
}
