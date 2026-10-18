/**
 * Лента переписки — одна на личный чат и на комнату группы.
 *
 * Их было две, и разметка совпадала почти дословно. Мешало не оформление, а ДАННЫЕ: сервер зовёт
 * автора `from` в паре и `frm` в комнате, системную строку в паре узнают по полю `sys`, а в
 * комнате — по пустому автору. Из-за двух этих различий всё, что делалось для переписки —
 * серии, состояние отправки, реакции, цитата, свайп-ответ, — в комнате отсутствовало.
 *
 * Теперь форма приводится на входе (`roomMsg` в src/groups.ts), а показывает обе одна лента.
 * Что остаётся за экраном — только то, чем чаты действительно отличаются:
 *
 *   `showAuthor`  — имя над чужим пузырём. В комнате больше двух человек, и без подписи реплики
 *                   сливаются в один голос; в паре имя избыточно, собеседник и так один.
 *   `peerRead`    — момент, когда вторая сторона открывала переписку. Есть только у пары: в
 *                   комнате «прочитано» значило бы «все прочитали», а этого сервер не считает.
 *   `sysText`     — как превратить системную строку в текст. В паре это код события, в комнате
 *                   английская фраза от сервера.
 *
 * Всё остальное — общее, и переставать быть общим не должно: разъехавшиеся ленты мы уже видели.
 */
import React from 'react';
import { Image, Pressable, StyleSheet, Text, View, Linking } from 'react-native';
import { CHAT, Msg, msgTime, msgDayLabel, sameSeries, linkParts, klealText } from '../chat';
import { isMe, mediaUrl } from '../api';
import { VoiceBubble } from '../voice';
import { VideoBubble } from '../videonote';
import { SwipeToReply } from './SwipeToReply';
import { GlassSurface } from './LiquidGlass';
import { BubbleIn, EventIn } from './ChatMotion';
import { IconBan, IconCalendar, IconCalendarCheck, IconClock, IconPerson, IconPin } from './icons';
import { color, font, radius as rad, space } from '../theme';

/** Кнопка под событием: подпись, что делать и насколько она главная. */
export type SysAct = { key: string; label: string; onPress: () => void; soft?: boolean };

/** Кто стоит за репликой: цвет имени и лицо. Решает экран — только он знает состав. */
export type Author = { color?: string; photo?: string };

/**
 * Имена, которые в системной строке выделяются начертанием 500 (борд GR.18: «Jane joined the
 * group», «You created BBQ by the beach meetup»): участник — своим цветом автора, «ты» — серым.
 */
export type SysName = { name: string; color: string };


export function MessageFeed({
  msgs, me, ru, sysText, sysAction, showAuthor = false, peerRead, authorOf, sysNames,
  onReply, onReact, onPick, onRetry,
}: {
  msgs: Msg[];
  me: string;
  ru: boolean;
  sysText: (m: Msg) => string;
  /**
   * Что можно СДЕЛАТЬ прямо из события — кнопкой под строкой.
   *
   * Решает вызывающий, а не сервер: только у экрана есть живое состояние плана, и только он
   * знает, устарело ли событие. Строка «план предложен» живёт в ленте вечно, а подтверждать его
   * можно ровно пока он не подтверждён, не отменён и не перенесён ещё раз.
   */
  sysAction?: (m: Msg) => SysAct[] | null;
  showAuthor?: boolean;
  peerRead?: number;
  /** Цвет и лицо автора над чужой серией (комната группы). Без него — имя цветом по хешу. */
  authorOf?: (m: Msg) => Author | null;
  /** Имена для выделения в системных строках. */
  sysNames?: SysName[];
  onReply: (m: Msg) => void;
  onReact: (m: Msg, emoji: string) => void;
  onPick: (m: Msg) => void;
  onRetry: (m: Msg) => void;
}) {
  const norm = (v: unknown) => String(v || '').trim().toLowerCase();
  const mineName = norm(me);

  /**
   * Что реально попадёт на экран. Считается ЗАРАНЕЕ, потому что от соседей зависят и разделитель
   * дня, и серия — а системная строка с незнакомым кодом не рисуется вовсе. Раньше соседа брали
   * из полного списка: скрытая строка оставалась «предыдущей», и «Сегодня» исчезало вместе с ней.
   */
  const shown = msgs.filter((m) => !m.sys || !!sysText(m));
  /*
    НОВОЕ — ТО, ЧТО ПРИШЛО ИЛИ УШЛО ПРИ ОТКРЫТОМ ЭКРАНЕ (см. ChatMotion): время реплики не раньше
    открытия ленты. История, открытая с экраном, стоит на месте. Секунда запаса — на часы сервера.
  */
  const openedAt = React.useRef(Date.now() / 1000 - 1).current;
  const isFresh = (m: Msg) => (m.t || 0) >= openedAt;

  return (
    <>
      {shown.map((m, i) => {
        // Своя ли реплика — по `from_id`; по подписи только у строки без id (своя, ещё не
        // отправленная, или старый ответ). По подписи переписка двух тёзок была вся «моя».
        const mine = isMe(m.from, (m as any).from_id, me);
        const prev = shown[i - 1];
        const next = shown[i + 1];
        const newDay = !!m.t && (!prev
          || new Date((prev.t || 0) * 1000).toDateString() !== new Date(m.t * 1000).toDateString());

        /* События — не реплика: они не чьи-то слова, а факт, случившийся со встречей или с
           составом. Поэтому строкой по центру, без пузыря, автора и галочек. */
        if (m.sys) {
          const acts = sysAction ? sysAction(m) : null;
          return (
            <React.Fragment key={m.id || m.cid || i}>
              {newDay ? <Text style={s.day}>{msgDayLabel(m.t!, ru)}</Text> : null}
              {/* События ПЛАНА — карточкой (см. planEventLook): серой строкой 11 их не замечали. */}
              {planEventLook(m) ? (
                <EventIn fresh={isFresh(m)}>
                  <PlanEvent look={planEventLook(m)!} text={sysSpans(sysText(m), sysNames)} at={m.t ? msgTime(m.t, ru) : ''} />
                </EventIn>
              ) : (
              /* Строка события по борду (GR.18): имена начертанием 500, остальное — 400, дальше
                  часики 10 и время. Одной строкой по центру, переносится целиком. */
              <View style={s.sysRow}>
                <Text style={s.sys}>{sysSpans(sysText(m), sysNames)}</Text>
                {m.t ? (
                  <View style={s.sysTime}>
                    <IconClock size={10} c={SYS_INK} />
                    <Text style={s.sys}>{msgTime(m.t, ru)}</Text>
                  </View>
                ) : null}
              </View>
              )}
              {acts && acts.length ? (
                <View style={s.sysActs}>
                  {acts.map((a) => (
                    <Pressable
                      key={a.key}
                      accessibilityRole="button"
                      accessibilityLabel={a.label}
                      style={[s.sysBtn, a.soft && s.sysBtnSoft]}
                      onPress={a.onPress}
                      hitSlop={6}
                    >
                      <Text style={[s.sysBtnText, a.soft && s.sysBtnTextSoft]}>{a.label}</Text>
                    </Pressable>
                  ))}
                </View>
              ) : null}
            </React.Fragment>
          );
        }

        /* MSG.09 / MSG.14b: удалённая или скрытая реплика — не пузырь, а строка по центру, как
           событие: «You deleted a message», «Pau’s message is hidden». */
        if (m.deleted || m.hidden) {
          const who = String(m.from || '');
          return (
            <React.Fragment key={m.id || m.cid || i}>
              {newDay ? <Text style={s.day}>{msgDayLabel(m.t!, ru)}</Text> : null}
              <View style={s.sysRow}>
                <Text style={s.sys}>{sysSpans(m.hidden ? CHAT.hiddenFrom(who) : CHAT.deletedBy(who, mine),
                  [...(sysNames || []), ...(who && !mine ? [{ name: who, color: authorOf?.(m)?.color || authorColor(who) }] : [])])}</Text>
                {m.t ? (
                  <View style={s.sysTime}>
                    <IconClock size={10} c={SYS_INK} />
                    <Text style={s.sys}>{msgTime(m.t, ru)}</Text>
                  </View>
                ) : null}
              </View>
            </React.Fragment>
          );
        }

        const tail = !sameSeries(m, next);
        const head = !sameSeries(prev, m);
        const failed = m.state === 'failed';
        const read = peerRead !== undefined && peerRead >= (m.t || 0);

        return (
          // Ключ — сначала `cid`: он один у показанной сразу реплики и у серверной. По `id` реплика
          // меняла ключ в момент, когда сервер её принял, перемонтировалась и взлетала второй раз.
          <React.Fragment key={m.cid || m.id || i}>
            {newDay ? <Text style={s.day}>{msgDayLabel(m.t!, ru)}</Text> : null}
            <SwipeToReply enabled={!!m.id && !m.deleted} onReply={() => onReply(m)}>
              <BubbleIn mine={mine} fresh={isFresh(m)} style={{ alignItems: mine ? 'flex-end' : 'flex-start', marginTop: head ? 8 : 2 }}>
                {/* Имя автора — только у чужих и только в начале серии: повторять его над каждой
                    репликой одного человека значит кричать его четыре раза подряд. */}
                {showAuthor && !mine && head ? (
                  /* Автор серии — лицо 32 и имя его цветом (борд GR.21: «Chat Message → author»).
                     Лицо нужно, чтобы в группе реплику узнавали раньше, чем прочтут имя. */
                  <View style={s.authorRow}>
                    {authorOf ? (
                      <View style={s.authorAv}>
                        <IconPerson size={16} />
                        {authorOf(m)?.photo ? (
                          <Image source={{ uri: mediaUrl(String(authorOf(m)?.photo)) }}
                                 style={[s.authorAv, StyleSheet.absoluteFill]} />
                        ) : null}
                      </View>
                    ) : null}
                    <Text style={[s.author, { color: authorOf?.(m)?.color || authorColor(String(m.from || '')) }]}
                          numberOfLines={1}>{m.from}</Text>
                  </View>
                ) : null}
                {/* Ответ модерации. Подписан прямо над репликой, потому что иначе это просто
                    сообщение от кого-то по имени Kleal — а человек должен видеть, что ему
                    ответил продукт, а не собеседник. Старый клиент лишнего поля не знает и
                    покажет обычную реплику: хуже не станет. */}
                {(m as any).admin && !mine && head ? (
                  <Text style={s.official}>{CHAT.fromKleal()}</Text>
                ) : null}

                {m.video && !m.deleted ? (
                  /* Кружок — не пузырь: у него нет ни фона, ни хвостика, он сам себе форма. */
                  <VideoBubble video={m.video} />
                ) : m.voice ? (
                  <VoiceBubble voice={m.voice} mine={mine} />
                ) : (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={failed ? CHAT.retry() : m.text}
                    onPress={failed ? () => onRetry(m) : undefined}
                    onLongPress={m.deleted || !m.id ? undefined : () => onPick(m)}
                    delayLongPress={350}
                    style={[s.bubBox, mine ? s.bubMe : s.bubThem]}
                  >
                    {/*
                      ПУЗЫРЬ — ЖИДКОЕ СТЕКЛО (борд «GR · Offline — new layout», GR.18): свой —
                      коралловое, чужой — светлое, скругление 20 и хвостик 4 у последнего в серии.
                      Стекло само по себе не ловит касаний, долгое нажатие и ссылки внутри текста
                      продолжают работать через Pressable и Text.
                    */}
                    <GlassSurface
                      tone={mine ? 'brand' : 'light'}
                      radius={20}
                      style={[s.bub, mine ? (tail ? s.bubMeTail : s.bubMeMid) : (tail ? s.bubThemTail : s.bubThemMid),
                              (m as any).admin && !mine && s.bubOfficial]}
                    >
                    {/* Цитата внутри пузыря, а не рядом: ответ и то, на что отвечают, — одно целое. */}
                    {m.rt ? (
                      <View style={[s.quote, mine && s.quoteMine]}>
                        <Text style={[s.quoteWho, mine && { color: color.onPrimary }]} numberOfLines={1}>
                          {m.rt.from}
                        </Text>
                        <Text style={[s.quoteText, mine && { color: color.onPrimary }]} numberOfLines={2}>
                          {m.rt.text || CHAT.deleted()}
                        </Text>
                      </View>
                    ) : null}
                    <Text style={[s.bubText, mine && { color: color.onPrimary }, m.deleted && s.bubGone, failed && s.bubFailed]}>
                      {m.deleted ? CHAT.deleted() : linkParts(String((m as any).admin && klealText(m as any) || m.text || '')).map((part, k) => (
                        part.href ? (
                          /* Адрес показан ровно так, как его прислали: подменять его красивой
                             подписью нельзя — по нему и решают, идти ли. */
                          <Text
                            key={k}
                            style={[s.link, mine && s.linkMine]}
                            onPress={() => Linking.openURL(part.href!).catch(() => {})}
                          >
                            {part.text}
                          </Text>
                        ) : <Text key={k}>{part.text}</Text>
                      ))}
                    </Text>
                    </GlassSurface>
                  </Pressable>
                )}

                {/* Реакции под пузырём: нажатие по своей снимает её, по чужой — присоединяет. */}
                {m.r && Object.keys(m.r).length ? (
                  <View style={[s.reactions, { alignSelf: mine ? 'flex-end' : 'flex-start' }]}>
                    {Object.entries(m.r).map(([e, who]) => (
                      <Pressable
                        key={e}
                        accessibilityRole="button"
                        accessibilityLabel={`${e} ${who.length}`}
                        onPress={() => onReact(m, e)}
                        style={[s.reaction, who.includes(mineName) && s.reactionMine]}
                      >
                        <Text style={s.reactionText}>{e}{who.length > 1 ? ` ${who.length}` : ''}</Text>
                      </Pressable>
                    ))}
                  </View>
                ) : null}

                {tail ? (
                  <Text style={s.time}>
                    {msgTime(m.t, ru)}
                    {/* Своё сообщение говорит о себе честно: часики — ушло не всё, восклицание —
                        не ушло вовсе и можно нажать, галочка — сервер принял, две — прочитано. */}
                    {mine ? (
                      m.state === 'sending' ? <Text style={s.tick}>  ⋯</Text>
                      : failed ? <Text style={s.tickFail}>  ! {CHAT.retry()}</Text>
                      : peerRead === undefined ? null
                      : <Text style={read ? s.tickRead : s.tick}>{read ? '  ✓✓' : '  ✓'}</Text>
                    ) : null}
                  </Text>
                ) : null}
              </BubbleIn>
            </SwipeToReply>
          </React.Fragment>
        );
      })}
    </>
  );
}

/**
 * Цвет имени автора. Постоянный для человека: считается от имени, а не от порядка в ленте —
 * иначе Jane была бы фиолетовой вчера и оранжевой сегодня.
 */
const AUTHOR_COLORS = ['#5F31DB', '#E0671B', '#0F7340', '#1F58BE', '#C2185B', '#8A5A00'];

/** Серый системных строк — muted-foreground палитры борда. */
const SYS_INK = '#5A616E';

/**
 * Разложить строку события на куски: имена из `names` — начертанием 500 (участник своим цветом,
 * «ты» — серым), остальное — обычным. Ищется целое слово, самое длинное имя первым: иначе «Jan»
 * съело бы начало «Jane».
 */
/**
 * СОБЫТИЯ ПЛАНА — КАРТОЧКОЙ, А НЕ СЕРОЙ СТРОКОЙ.
 *
 * «Ты предложил(а) встречу», «План подтверждён», «Ты назвал(а) место» шли той же строкой 11 серым,
 * что и «You joined»: тестировщики 17.10.2026 — «в чате ПЛОХО видно оповещения, что что-то
 * создалось или изменилось». А это главные события переписки: после них меняется встреча.
 * Поэтому у них — светлая карточка по центру, значок в круге и текст 13 тёмным; подтверждение —
 * зелёным, отмена и молчание — серым. Мелкие события (вошёл, вышел из комнаты) остаются строкой.
 */
type PlanLook = { tone: 'brand' | 'ok' | 'off'; icon: 'cal' | 'check' | 'pin' | 'off' };
const PLAN_OK = new Set(['plan_confirmed', 'plan_fixed', 'plan_change_ok']);
const PLAN_OFF = new Set(['plan_cancelled', 'plan_expired', 'plan_left', 'plan_change_no', 'plan_change_expired',
  'plan_cant_make_it', 'plan_ask_declined', 'plan_change_pulled', 'plan_ask_pulled']);
function planEventLook(m: Msg): PlanLook | null {
  const code = String((m.sys as any)?.code || '');
  if (!(code.startsWith('plan_') || code === 'intent_new') || code === 'plan_status' || code === 'plan_side') return null;
  if (PLAN_OK.has(code)) return { tone: 'ok', icon: 'check' };
  if (PLAN_OFF.has(code)) return { tone: 'off', icon: 'off' };
  if (code === 'plan_place') return { tone: 'brand', icon: 'pin' };
  return { tone: 'brand', icon: 'cal' };
}

function PlanEvent({ look, text, at }: { look: PlanLook; text: React.ReactNode; at: string }) {
  const ink = look.tone === 'ok' ? color.successText : look.tone === 'off' ? SYS_INK : color.primary;
  const Icon = look.icon === 'check' ? IconCalendarCheck : look.icon === 'pin' ? IconPin : look.icon === 'off' ? IconBan : IconCalendar;
  return (
    <View style={s.evWrap}>
      <GlassSurface tone="light" radius={16} style={s.ev}>
        <View style={[s.evIcon, look.tone === 'ok' ? s.evIconOk : look.tone === 'off' ? s.evIconOff : s.evIconBrand]}>
          <Icon size={16} c={ink} />
        </View>
        <View style={{ flexShrink: 1, gap: 2 }}>
          <Text style={s.evText}>{text}</Text>
          {at ? <Text style={s.evTime}>{at}</Text> : null}
        </View>
      </GlassSurface>
    </View>
  );
}

function sysSpans(text: string, names?: SysName[]): React.ReactNode {
  const list = (names || []).filter((n) => n.name.trim()).sort((a, b) => b.name.length - a.name.length);
  if (!list.length || !text) return text;
  const esc = (v: string) => v.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  // Граница слова — явным классом букв, а не \\p{L}: свойства Юникода в регулярках Hermes знает не везде.
  const L = 'A-Za-zÀ-ÿĀ-žА-Яа-яЁё';
  const re = new RegExp('(^|[^' + L + '])(' + list.map((n) => esc(n.name)).join('|') + ')(?=$|[^' + L + '])', 'g');
  const out: React.ReactNode[] = [];
  let last = 0;
  let k = 0;
  for (const mm of text.matchAll(re)) {
    const at = (mm.index || 0) + mm[1].length;
    if (at > last) out.push(text.slice(last, at));
    const hit = list.find((n) => n.name === mm[2]);
    out.push(<Text key={k++} style={[s.sysName, { color: hit?.color || SYS_INK }]}>{mm[2]}</Text>);
    last = at + mm[2].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function authorColor(name: string): string {
  let h = 0;
  for (const ch of name.trim().toLowerCase()) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AUTHOR_COLORS[h % AUTHOR_COLORS.length];
}

// ===== вид

const s = StyleSheet.create({
  day: { alignSelf: 'center', fontSize: 12, color: color.neutral400, marginVertical: space.sm },
  /** Событие — Geist 11 серым по центру, как строки «joined the group» на GR.18. */
  sys: { textAlign: 'center', fontFamily: font.text, fontSize: 11, lineHeight: 16, color: SYS_INK },
  /** Строка события: имя, текст, часики и время в один ряд, поля 3/11 как у «Frame 545» борда. */
  sysRow: { alignSelf: 'center', flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center',
            columnGap: 3, paddingVertical: 3, paddingHorizontal: 11, marginVertical: 2, maxWidth: '100%' },
  sysTime: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  /** Карточка события плана: по центру, ровно 88% ленты — подряд идущие события стоят одной
      колонкой (по ширине текста они плясали: короткое «назвал место» уже длинного «предложил»). */
  evWrap: { alignSelf: 'center', width: '88%', marginVertical: 6 },
  ev: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, paddingLeft: 10, paddingRight: 14 },
  evIcon: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  evIconBrand: { backgroundColor: 'rgba(255,56,92,0.12)' },
  evIconOk: { backgroundColor: color.successBg },
  evIconOff: { backgroundColor: 'rgba(24,27,34,0.06)' },
  evText: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.fg } as any,
  evTime: { fontFamily: font.text, fontSize: 11, lineHeight: 14, color: SYS_INK } as any,
  sysName: { fontFamily: font.textMedium },
  /* Кнопка события. Главная — фирменным цветом: человек должен видеть, что от него ждут ответа,
     не вчитываясь в серую строку над ней. Второстепенная — обведённая, чтобы «оставить как было»
     не спорило глазом с «подтвердить». */
  sysActs: { flexDirection: 'row', flexWrap: 'wrap', alignSelf: 'center', justifyContent: 'center',
             gap: space.xs, marginTop: -2, marginBottom: 10 },
  sysBtn: { height: 36, paddingHorizontal: 16, borderRadius: rad.full, backgroundColor: color.primary,
            alignItems: 'center', justifyContent: 'center' },
  sysBtnSoft: { backgroundColor: color.card, borderWidth: 1, borderColor: color.border },
  sysBtnText: { fontSize: 13, fontWeight: '700', color: color.onPrimary } as any,
  sysBtnTextSoft: { color: color.fg } as any,
  /** Имя автора цветом человека (GR.18: Jane — фиолетовым, Marc — оранжевым). */
  author: { fontFamily: font.textSemibold, fontSize: 15, lineHeight: 20, flexShrink: 1 } as any,
  /** Лицо 32 и имя через 8 — «author» борда; до пузыря 4. */
  authorRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4, maxWidth: '80%' },
  authorAv: {
    width: 32, height: 32, borderRadius: 16, overflow: 'hidden', backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },

  /*
    ПО ЧИСЛАМ БОРДА (OF.C2, node 3642-221266). Отличий было четыре, и вместе они и делали ленту
    сырой:
      • чужой пузырь стоял СЕРЫМ (#EEF0F4) — на борде он белый. На светло-сером фоне страницы
        серое на сером сливалось в кашу, белое отделяется;
      • радиус 18 против 22 — пузыри выглядели угловатее макета;
      • свой пузырь был плоской заливкой без тени, а на борде под ним лежит мягкое розовое
        свечение, которое и приподнимает его над лентой;
      • у белого пузыря на борде есть своя тень — без неё он растворяется в фоне.
    Настоящего градиента у своего пузыря пока нет: expo-linear-gradient в зависимостях
    отсутствует, а тащить его ради одного пузыря — отдельное решение. Свечение даёт бо́льшую часть
    эффекта; если понадобится градиент, это отдельная правка.
  */
  /** Обёртка держит ширину и тень; сам пузырь — стекло внутри неё. */
  /** 260 из 350 на борде (Chat/Message) — 74% ширины ленты. */
  bubBox: { maxWidth: '74%' },
  bub: { paddingVertical: 12, paddingHorizontal: 16 },
  /**
   * Тени из борда: под своим — коралловое свечение (#FF385C · 30%, 16, y 6), под чужим — мягкая
   * тёмная (#0A0A14 · 12%). Лежат на обёртке без заливки: iOS строит тень по форме стекла.
   */
  bubMe: {
    alignSelf: 'flex-end',
    shadowColor: color.primary, shadowOpacity: 0.3, shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 }, elevation: 4,
  },
  bubThem: {
    alignSelf: 'flex-start',
    // Только контактная тень 0/1 · 2, #0A0A14 · 6% — «Glass/Bubble» борда. Прежняя 16/6 · 12%
    // поднимала чужой пузырь выше своего, а на борде он лежит почти на подложке.
    shadowColor: '#0A0A14', shadowOpacity: 0.06, shadowRadius: 2,
    // Без elevation: на Android тень просвечивает сквозь светлое стекло и красит пузырь в серый.
    shadowOffset: { width: 0, height: 1 },
  },
  official: { fontSize: 11, fontWeight: '700', color: color.primary, marginBottom: 3, letterSpacing: 0.3 },
  bubOfficial: { borderWidth: 1, borderColor: color.primary },
  /** Хвостик — у ПОСЛЕДНЕГО пузыря серии: он и показывает, где реплики одного человека кончились. */
  bubMeTail: { borderBottomRightRadius: 4 },
  bubThemTail: { borderBottomLeftRadius: 4 },
  bubMeMid: { borderBottomRightRadius: 20 },
  bubThemMid: { borderBottomLeftRadius: 20 },
  /** Семейство явно: без него реплики рисовались системным шрифтом, а не Geist. */
  bubText: { fontFamily: font.text, fontSize: 15, lineHeight: 22, color: color.fg },
  /**
   * Не ушло — бледнее ТЕКСТ, а не пузырь: полупрозрачный предок гасит системное стекло целиком,
   * и вместо бледного пузыря осталась бы одна строка. Цвет не меняем: это по-прежнему твои слова.
   */
  bubFailed: { opacity: 0.6 },
  /** Удалённое остаётся строкой: пропасть бесследно оно не может — второй его уже видел. */
  bubGone: { fontStyle: 'italic', opacity: 0.7 },

  quote: { borderLeftWidth: 2, borderLeftColor: color.primary, paddingLeft: space.sm, marginBottom: 6, gap: 1 },
  quoteMine: { borderLeftColor: color.onPrimary },
  quoteWho: { fontSize: 12, fontWeight: '700', color: color.primary } as any,
  quoteText: { fontSize: 12, color: color.muted } as any,

  link: { color: color.primary, textDecorationLine: 'underline' } as any,
  linkMine: { color: color.onPrimary } as any,

  reactions: { flexDirection: 'row', gap: 4, marginTop: 3 },
  reaction: {
    flexDirection: 'row', paddingHorizontal: 7, paddingVertical: 3,
    borderRadius: rad.full, backgroundColor: color.neutral100,
    borderWidth: 1, borderColor: 'transparent',
  },
  /** Своя реакция обведена: без этого нельзя понять, поставил ты её или просто видишь. */
  reactionMine: { borderColor: color.primary, backgroundColor: color.card },
  reactionText: { fontSize: 13, color: color.fg } as any,

  /** Время: 11 средним начертанием цветом #5A616E — так на борде. */
  time: { fontFamily: font.text, fontSize: 11, lineHeight: 22, color: '#8A8E96', marginHorizontal: 4 },
  tick: { fontSize: 11, color: color.neutral400 } as any,
  tickRead: { fontSize: 11, color: color.primary, fontWeight: '700' } as any,
  tickFail: { fontSize: 11, color: color.primary, fontWeight: '600' } as any,
});
