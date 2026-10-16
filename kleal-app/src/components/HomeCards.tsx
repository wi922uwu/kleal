/**
 * Карточки колоды на главной — «Home Card» с кадра «GR.01 · Home · Kleal prompt» (Figma, секция
 * «Test 260930»).
 *
 * ОДНО СЛОЖЕНИЕ НА ЧЕТЫРЕХ ЖИТЕЛЕЙ КОЛОДЫ: ближайшая встреча, приглашение один на один, групповое
 * приглашение и пустая карточка. Смысл у них разный, а вид один — слева лицо, справа название с
 * бейджем и строка меты, под ними кнопка на всю ширину. И рост один, 126 у всех: колода при
 * листании не меняет высоту, и строка ввода под ней стоит на месте. Так уже прыгало, пока встреча
 * была на шестьдесят пунктов ниже приглашения.
 *
 * Геометрия с борда (Home Card · plan, 350×126), не на глаз:
 *   поля 12; строка 50, под ней через 12 кнопка 40;
 *   строка: лицо 48, через 12 колонка текста — строка названия 24 и мета 22 через 4;
 *   название Geist 600 15/24 с разрядкой −0,15; бейдж 24 в высоту, поля 12, подпись Geist 500 11/16;
 *   мета — кусочки «значок 16 фирменным + 4 + подпись Geist 400 13/22» через 8, в одну строку;
 *   углы: сверху 20, снизу 32 — нижний концентричен кнопке: поле 12 плюс её радиус 20.
 *
 * Данные и переходы те же, что были у карточек в app/home.tsx: встреча открывает /plan, приглашение
 * — /invite, групповое — /ginvite с id и gid, пустая заводит затею в /create.
 */
import React from 'react';
import { Image, Pressable, StyleProp, StyleSheet, Text, View, ViewStyle } from 'react-native';
import Animated from 'react-native-reanimated';
import { useRouter } from 'expo-router';
import { GlassSurface, LIQUID, usePress } from './LiquidGlass';
import { GlassPill } from './Glass';
import { IconClock, IconGlobe, IconGroups, IconImagePlaceholder, IconPin } from './icons';
import { mediaUrl } from '../api';
import { HOME, HomeInvite, splitWhen } from '../home';
import { useLang, dateLocale, use12h } from '../i18n';
import { hTap } from '../haptics';
import { color, font } from '../theme';

/** Рост карточки — один на все четыре вида. Колода (CardStack) держит под ним свои края. */
export const HOME_CARD_H = 126;
const R_TOP = 20;
const R_BOTTOM = 32;
/** Бейдж «сегодня» и «мэтч» — зелёные с кадра (GR.01, «Signal Status Badge»); подпись — successText. */
const BADGE_GREEN = '#CCF1B6';

// ===== дата встречи

/** Сколько календарных дней от сегодня: 0 — сегодня, 1 — завтра. По полуночам, а не по 24 часам. */
function daysAhead(d: Date): number {
  const n = new Date();
  const a = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const b = new Date(n.getFullYear(), n.getMonth(), n.getDate()).getTime();
  // Округление, а не деление нацело: в сутках перевода часов 23 или 25 часов.
  return Math.round((a - b) / 86400000);
}

const cap = (x: string) => (x ? x[0].toUpperCase() + x.slice(1) : x);
/** Точка сокращения («окт.», «vie.») в бейдже лишняя: он и так короткий по определению. */
const bare = (x: string) => x.replace(/\.$/, '').trim();

/**
 * «Fri 3 Oct» / «Пт 3 окт» / «Vie 3 oct» — СОБРАНО ПО ЧАСТЯМ. Целиком локаль ставит свои запятые и
 * порядок («Fri, Oct 3» у en-US), а бейдж на кадре одного вида на всех языках.
 */
function shortDate(d: Date, loc: string): string {
  const wd = bare(d.toLocaleDateString(loc, { weekday: 'short' }));
  const mon = bare(d.toLocaleDateString(loc, { month: 'short' }));
  return cap(`${wd} ${d.getDate()} ${mon}`);
}

/** Слово дня: сегодня, завтра, дальше — день недели. Число уже стоит в бейдже, у часов оно лишнее. */
function dayWord(d: Date, loc: string): string {
  const k = daysAhead(d);
  if (k === 0) return HOME.today();
  if (k === 1) return HOME.tomorrow();
  return cap(bare(d.toLocaleDateString(loc, { weekday: 'short' })));
}

/** Бейдж: «Today», «Tomorrow» или короткая дата. */
function dayBadge(d: Date, loc: string): string {
  const k = daysAhead(d);
  if (k === 0) return HOME.today();
  if (k === 1) return HOME.tomorrow();
  return shortDate(d, loc);
}

/**
 * Часы. Двенадцатичасовые — только у английского (use12h), и там без ведущего нуля: «8:30 PM», а
 * не «08:30 PM». В двадцатичетырёхчасовых ноль нужен — «09:00», как на кадре «20:30».
 */
function clock(d: Date, ru: boolean): string {
  const h12 = use12h(ru);
  return d.toLocaleTimeString(dateLocale(ru), { hour: h12 ? 'numeric' : '2-digit', minute: '2-digit', hour12: h12 });
}

// ===== части карточки

const initial = (name?: string) => (Array.from(String(name || '').trim())[0] || '?').toUpperCase();

/**
 * Лицо. Буква лежит ПОД фотографией, а не вместо неё: пока файл читается из кэша (а при смене
 * карточки в колоде это кадр-два), на месте лица стоит буква, а не пустой серый круг. Не загрузилось
 * вовсе — буква и остаётся.
 */
function Face({ photo, name, size = 48, ring, style }: {
  photo?: string; name?: string; size?: number; ring?: boolean; style?: StyleProp<ViewStyle>;
}) {
  const url = String(photo || '').trim();
  const inner = ring ? size - 4 : size;
  return (
    <View style={[s.face, { width: size, height: size, borderRadius: size / 2 }, ring && s.ring, style]}>
      <Text style={[s.faceInit, size < 40 && s.faceInitSm]}>{initial(name)}</Text>
      {url ? (
        <Image source={{ uri: mediaUrl(url) }} style={[StyleSheet.absoluteFill, { borderRadius: inner / 2 }]} />
      ) : null}
    </View>
  );
}

/** Бейдж в строке названия. `quiet` — серый: встреча ещё не подтверждена. */
function Badge({ label, quiet }: { label: string; quiet?: boolean }) {
  return (
    <View style={[s.badge, quiet && s.badgeQuiet]}>
      <Text style={[s.badgeText, quiet && s.badgeQuietText]} numberOfLines={1}>{label}</Text>
    </View>
  );
}

/**
 * Кусочек меты: значок и подпись. `shrink` — этот кусочек уступает место, когда строка не влезает:
 * длинное место встречи обрезается многоточием, а время рядом остаётся целым.
 */
function Chunk({ icon, text, shrink, quiet }: { icon?: React.ReactNode; text: string; shrink?: boolean; quiet?: boolean }) {
  return (
    <View style={[s.chunk, shrink && s.chunkShrink]}>
      {icon}
      <Text style={[s.metaText, quiet && s.metaQuiet]} numberOfLines={1}>{text}</Text>
    </View>
  );
}

const metaIcon = (Icon: typeof IconClock) => <Icon size={16} c={color.primary} />;

/**
 * Тело «Home Card». Все четыре карточки собраны из него, поэтому и рост, и поля, и кнопка у них
 * общие по построению, а не по договорённости.
 *
 * СТЕКЛО — ОТДЕЛЬНЫЙ СЛОЙ ПОД СОДЕРЖИМЫМ, И ФОРМУ ЕМУ ДАЁТ ОНО САМО, А НЕ ОБРЕЗКА. Углы у карточки
 * разные (20 и 32), а `overflow: hidden` при разных радиусах RN на iOS делает маской — CAShapeLayer
 * на слое вида. Системное стекло под маскированным предком не рисуется вовсе, ровно как под
 * непрозрачностью меньше 1. Поэтому у жидкого стекла обрезки нет: радиусы по углам expo-glass-effect
 * сам передаёт в `cornerConfiguration` UIGlassEffect. Запасной путь (размытие и плёнка) обрезается
 * видом, как и раньше.
 *
 * СВЕЧЕНИЕ КНОПКИ НЕ ОБРЕЗАЕТСЯ. Карточка сначала обрезала себя прямоугольником, чтобы розовое
 * свечение (8 вниз, размытие 20) не ложилось на края колоды. Но прямоугольник шире скруглённых
 * нижних углов: свечение заполняло углы, и под карточкой проступала розовая подложка с КВАДРАТНЫМИ
 * углами (снимок симулятора 30.09). На кадре свечение и правда выходит на края колоды — так и
 * оставлено.
 */
function HomeCard({ avatar, title, badge, meta, action, onPress, onAction }: {
  avatar: React.ReactNode;
  title: string;
  badge?: React.ReactNode;
  meta: React.ReactNode;
  /** Подпись кнопки. */
  action: string;
  /** Нажатие по карточке целиком. Нет — карточка не нажимается, работает только кнопка. */
  onPress?: () => void;
  /** Нажатие по кнопке, если оно не то же самое, что по карточке. */
  onAction?: () => void;
}) {
  const p = usePress(0.98);
  const body = (
    <>
      <GlassSurface tone="light" radius={R_TOP} pointerEvents="none" style={[StyleSheet.absoluteFill, s.glass]} />
      <View style={s.row}>
        {avatar}
        <View style={s.text}>
          <View style={s.titleRow}>
            <Text style={s.title} numberOfLines={1}>{title}</Text>
            {badge}
          </View>
          <View style={s.meta}>{meta}</View>
        </View>
      </View>
      {/*
        Кнопка нажимается сама по себе — со своей пружиной и откликом фирменной кнопки (GlassPill
        сам даёт hCommit). Отдельного отклика тут не нужно: он был бы вторым на одно касание.
      */}
      <GlassPill tone="brand" small label={action} onPress={onAction || onPress} style={s.btn} />
    </>
  );
  if (!onPress) return <View style={s.card}>{body}</View>;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      onPressIn={p.onPressIn}
      onPressOut={p.onPressOut}
      // Карточка целиком — это переход, а не главное действие: отклик лёгкий (см. src/haptics.ts).
      onPress={() => { hTap(); onPress(); }}
    >
      {/* Отклик на палец — масштабом: прозрачность погасила бы стекло карточки и кнопки. */}
      <Animated.View style={[s.card, p.style]}>{body}</Animated.View>
    </Pressable>
  );
}

// ===== четыре карточки

/**
 * Ближайшая встреча. На кадре: «Language meetup» · бейдж «Today» · [глобус] «Online» · [часы]
 * «Today 20:30» · «Go to plan».
 *
 * ЛИЦО — ВТОРОГО УЧАСТНИКА, а не плитка с датой: дата теперь в бейдже и у часов, дважды её на одной
 * карточке не показываем. Кто второй, говорит `participants[].is_me` с сервера; нет списка — прежнее
 * сравнение хоста и гостя с собственным именем.
 *
 * СОСТОЯНИЕ — ЦВЕТОМ БЕЙДЖА. Слово в бейдже теперь день встречи, а подтверждена ли она, говорит
 * зелёный (как на кадре); ещё ждёт ответа — тот же бейдж серым.
 */
export function PlanCard({ plan, me }: { plan: any; me: string }) {
  const router = useRouter();
  const ru = useLang() === 'ru';
  const loc = dateLocale(ru);
  const at = Number(plan?.starts_at || 0);
  const d = at ? new Date(at * 1000) : null;
  const open = () => router.navigate({ pathname: '/plan', params: { id: String(plan?.id || '') } });

  // С кем: второй в паре. Имена сравниваются без регистра — так их хранит матчинг.
  const rows: any[] = Array.isArray(plan?.participants) ? plan.participants : [];
  const other = rows.find((x) => x && !x.is_me);
  const norm = (x: any) => String(x || '').trim().toLowerCase();
  const name = String(other?.name || (norm(plan?.host) === norm(me) ? plan?.guest : plan?.host) || '').trim();

  const confirmed = plan?.state === 'confirmed';
  const online = plan?.mode === 'online';
  const place = online ? HOME.online() : String(plan?.venue || plan?.district || '').trim();
  const when = d ? `${dayWord(d, loc)} ${clock(d, ru)}` : String(plan?.when || '').trim() || HOME.flexible();

  return (
    <HomeCard
      onPress={open}
      avatar={<Face photo={other?.photo} name={name} />}
      title={String(plan?.title || '').trim() || HOME.next()}
      badge={
        d ? <Badge label={dayBadge(d, loc)} quiet={!confirmed} />
        // Без отметки времени дня не назвать — бейдж говорит хотя бы состояние.
        : <Badge label={confirmed ? HOME.planConfirmed() : HOME.planPending()} quiet={!confirmed} />
      }
      meta={
        <>
          {/* Место встречи вживую не указано — кусочка нет вовсе, а не «место не указано». */}
          {place ? <Chunk icon={metaIcon(online ? IconGlobe : IconPin)} text={place} shrink /> : null}
          <Chunk icon={metaIcon(IconClock)} text={when} />
        </>
      }
      action={HOME.goToPlan()}
    />
  );
}

/**
 * «Home Card · Empty»: то же тело, но вместо человека — заглушка картинки. Строка под названием —
 * не время и не место, а «они появятся здесь», поэтому без значка и серым.
 *
 * КНОПКА ЗАВОДИТ ЗАТЕЮ, А НЕ ОТКРЫВАЕТ СПИСОК. Приглашений нет ровно потому, что человеку пока не с
 * чем к кому-то прийти, — показать ему пустой список значило бы ответить «смотри, тут тоже ничего».
 * Без `seed`: что именно человек хочет, он ещё не сказал. Средний отклик (hCommit), как и раньше,
 * даёт сама фирменная кнопка.
 */
export function EmptyInviteCard() {
  const router = useRouter();
  return (
    <HomeCard
      avatar={<View style={s.face}><IconImagePlaceholder size={24} /></View>}
      title={HOME.noInvites()}
      meta={<Chunk text={HOME.noInvitesNote()} shrink quiet />}
      action={HOME.discover()}
      onAction={() => router.navigate('/create')}
    />
  );
}

/**
 * Приглашение один на один: лицо, «Имя, возраст», бейдж «Match» и одна строка «затея · когда».
 * Ни затеи, ни времени — строкой идёт записка человека или «хочет встретиться», и тогда без часов:
 * значок времени у фразы без времени врал бы.
 */
export function DirectInviteCard({ inv }: { inv: HomeInvite }) {
  const router = useRouter();
  const w = splitWhen(inv.intent.when || '');
  // splitWhen на пустом «когда» отвечает «Гибко» — здесь это не время, а его отсутствие.
  const date = inv.intent.when ? [w.date, w.time].filter(Boolean).join(' ') : '';
  const line = [String(inv.intent.title || '').trim(), date].filter(Boolean).join(' · ');
  const open = () => router.navigate({ pathname: '/invite', params: { id: inv.id } });
  return (
    <HomeCard
      onPress={open}
      avatar={<Face photo={inv.from.photo} name={inv.from.name} />}
      title={`${inv.from.name}${inv.from.age ? `, ${inv.from.age}` : ''}`}
      /* Ответившее и закрытое приглашение — та же карточка, но тихая: решать в ней уже нечего. */
      badge={inv.status === 'answered' ? <Badge label={HOME.saidYes()} quiet />
        : inv.status === 'not_picked' ? <Badge label={HOME.inviteClosed()} quiet />
        : <Badge label={HOME.match()} />}
      meta={
        line ? <Chunk icon={metaIcon(IconClock)} text={line} shrink />
        : <Chunk text={inv.note || HOME.wantsToMeet()} shrink />
      }
      action={inv.status === 'answered' ? HOME.waitingPick(inv.from.name)
        : inv.status === 'not_picked' ? HOME.seeWhy() : HOME.review()}
    />
  );
}

/**
 * Групповое приглашение — та же карточка; отличие только слева: не одно лицо, а два внахлёст (кто
 * уже внутри), и в мете вместо места — сколько людей. Кто зовёт, отдельной строкой больше не пишем:
 * в карточке 126 для неё нет места, а имя видно на экране приглашения.
 */
export function GroupInviteCard({ inv }: { inv: HomeInvite }) {
  const router = useRouter();
  const group = inv.group;
  const w = splitWhen(inv.intent.when || '');
  // Маршрут называется /ginvite — файл app/ginvite.tsx. Стояло `/group-invite`, которого нет:
  // expo-router на несуществующий путь молча ничего не делает, и карточка не открывалась вовсе.
  // gid рядом с id — экран приглашения без него не находит группу.
  const open = () => router.navigate({
    pathname: '/ginvite',
    params: { id: inv.id, gid: String(group?.gid || inv.intent.id || '') },
  });
  const line = [
    [w.date, w.time].filter(Boolean).join(' '),
    HOME.peopleCount(group?.participant_count || 0, group?.max_size),
  ].filter(Boolean).join(' · ');
  return (
    <HomeCard
      onPress={open}
      avatar={<GroupFaces people={(group?.participants || []).slice(0, 2)} />}
      title={inv.intent.title || inv.from.name}
      badge={<Badge label={HOME.inviteKindGroup()} />}
      meta={<Chunk icon={metaIcon(IconClock)} text={line} shrink />}
      action={HOME.review()}
    />
  );
}

/**
 * Два лица 32 внахлёст на 16 — ровно в квадрат 48, на место одного лица: колонка текста у групповой
 * карточки начинается там же, где у одиночной. Белое кольцо 2 разделяет лица. Одно лицо — рядом
 * знак группы, чтобы карточка не выглядела приглашением один на один; ни одного — знак группы
 * во весь круг.
 */
function GroupFaces({ people }: { people: { name: string; photo?: string }[] }) {
  if (!people.length) {
    return <View style={s.face}><IconGroups size={24} c={color.muted} /></View>;
  }
  return (
    <View style={s.faces}>
      <Face photo={people[0].photo} name={people[0].name} size={32} ring style={s.faceFront} />
      {people[1] ? (
        <Face photo={people[1].photo} name={people[1].name} size={32} ring style={s.faceBack} />
      ) : (
        <View style={[s.face, s.mini, s.ring, s.faceBack]}><IconGroups size={16} c={color.muted} /></View>
      )}
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  card: { height: HOME_CARD_H, padding: 12, gap: 12 },
  /** Углы по кадру; обрезка — только у запасного пути (см. HomeCard). */
  glass: {
    borderTopLeftRadius: R_TOP,
    borderTopRightRadius: R_TOP,
    borderBottomLeftRadius: R_BOTTOM,
    borderBottomRightRadius: R_BOTTOM,
    overflow: LIQUID ? 'visible' : 'hidden',
  },
  row: { height: 50, flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  text: { flex: 1, gap: 4 },
  titleRow: { height: 24, flexDirection: 'row', alignItems: 'center', gap: 8 },
  /* Насыщенность — семейством, а не `fontWeight`: на подключённых файлах вес не работает. */
  title: {
    flex: 1, fontFamily: font.textSemibold, fontSize: 15, lineHeight: 24, letterSpacing: -0.15, color: color.fg,
  },
  badge: {
    height: 24, borderRadius: 999, paddingHorizontal: 12, justifyContent: 'center', backgroundColor: BADGE_GREEN,
  },
  badgeQuiet: { backgroundColor: color.neutral100 },
  badgeText: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 16, color: color.successText },
  badgeQuietText: { color: color.muted },
  meta: { height: 22, flexDirection: 'row', alignItems: 'center', gap: 8 },
  chunk: { flexDirection: 'row', alignItems: 'center', gap: 4, flexShrink: 0 },
  chunkShrink: { flexShrink: 1, minWidth: 0 },
  metaText: { flexShrink: 1, fontFamily: font.text, fontSize: 13, lineHeight: 22, color: color.fg },
  metaQuiet: { color: color.muted },
  /** «Button» 326×40: GlassPill small даёт подпись 14/20 и поля 16, высоту задаём здесь. */
  btn: { height: 40 },

  face: {
    width: 48, height: 48, borderRadius: 24, overflow: 'hidden',
    backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center',
  },
  faceInit: { fontFamily: font.textSemibold, fontSize: 18, lineHeight: 24, color: color.muted },
  faceInitSm: { fontSize: 13, lineHeight: 18 },
  ring: { borderWidth: 2, borderColor: color.card },
  faces: { width: 48, height: 48, flexDirection: 'row', alignItems: 'center' },
  /** Первое лицо сверху: читается «вот кто зовёт, за ним остальные». */
  faceFront: { zIndex: 2 },
  faceBack: { marginLeft: -16 },
  mini: { width: 32, height: 32, borderRadius: 16 },
});
