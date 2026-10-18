/**
 * Главный экран — кадр «GR.01 · Home · Kleal prompt» (Figma, секция «Test 260930»).
 *
 * Сверху вниз, как на кадре: приветствие по имени и колокольчик; карусель стеклянных карточек с
 * предметом-занятием («Set Fire to the Night» и зеркальный шар); колода — ближайшая встреча и
 * приглашения; строка «What do you feel like doing?»; нижняя панель.
 *
 * Данные — с сервера, придуманных карточек нет:
 *  — ближайшая встреча — /api/agent/mplans;
 *  — адресованные человеку 1:1 и групповые приглашения — /api/agent/home-invites.
 * Когда сервер ничего не вернул, в колоде лежит пустая карточка, а не заглушка, похожая на данные.
 *
 * ЧЕГО НА ЭКРАНЕ БОЛЬШЕ НЕТ, И ПОЧЕМУ.
 *  • Ленты «групп, к которым можно присоединиться». Кадр её не рисует, а чужие затеи рядом теперь
 *    показывают карта и «Онлайн» — вторая витрина того же на главной спорила бы с ними.
 *  • Кнопки «Открыть историю разговоров» под строкой ввода. На кадре её нет; вход в историю переехал
 *    в шапку разговора с Kleal (app/buddy.tsx), где эти разговоры и живут, — экран не осиротел.
 *  • Пятен подложки, перетекавших вместе с колесом. (С 17.10 фон снова идёт за каруселью, но иначе —
 *    светом карточки под шёлковой фактурой, см. MoodBackdrop.) Тогда фон был фотографией с кадра, и цветные
 *    пятна поверх неё мутили бы её, а не оживляли.
 */
import { useCallback, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl, useWindowDimensions, Animated as RNAnimated } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { BottomNav } from '../src/components/BottomNav';
import { CardStack } from '../src/components/CardStack';
import { MoodCarousel, moodGeometry } from '../src/components/MoodCarousel';
import { PlanCard, EmptyInviteCard, DirectInviteCard, GroupInviteCard } from '../src/components/HomeCards';
import { NotifyBubble } from '../src/components/NotifyBubble';
import { GlassSurface } from '../src/components/LiquidGlass';
import { MoodBackdrop } from '../src/components/MoodBackdrop';
import { shuffledWheelKeys, wheelInOrder } from '../src/wheel';
import { IconMic } from '../src/components/icons';
import { useLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { warmPhotos, agent } from '../src/api';
import { HOME, homeInvites, HomeInvite } from '../src/home';
import { color, displayFamily, font } from '../src/theme';
import { useNavCollapse } from '../src/navScroll';

/**
 * ВЕРТИКАЛЬ КАДРА — ЧИСЛАМИ С БОРДА (390×844): шапка 56; карточка карусели на 40 ниже шапки; от
 * карусели до колоды 56; колода 126 + три края по 3; от колоды до строки 39; строка 48; от строки
 * до панели 49. Экран выше кадра — лишнее уходит в промежуток между каруселью и колодой, ниже —
 * карусель сжимается (см. `moodScale`), а не выталкивает строку за панель.
 */
const HEAD_H = 56;
const CARD_GAP = 40;
const STACK_H = 126 + 9;
const STACK_TO_ASK = 39;
const ASK_H = 48;
const ASK_TO_NAV = 49;
const MIN_MID = 24;

export default function Home() {
  /** Navigation V2: панель сворачивается при прокрутке вниз (NAV.S2). */
  const navCollapse = useNavCollapse();
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const me = st.profile.name || '';
  /** Ход карусели — по нему фон перетекает за пальцем (MoodBackdrop). Отдаёт сама карусель. */
  const [track, setTrack] = useState<{ x: RNAnimated.Value; pitch: number } | null>(null);
  const onTrack = useCallback((x: RNAnimated.Value, pitch: number) => setTrack({ x, pitch }), []);

  const [invites, setInvites] = useState<HomeInvite[]>([]);
  const [nextPlan, setNextPlan] = useState<any>(null);
  const [inviteError, setInviteError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  /**
   * Высота нижней панели. Меряется, а не задаётся числом: она складывается из своей полосы и
   * безопасной зоны, которая на разных телефонах разная.
   */
  const [navH, setNavH] = useState(96);
  /** Видимая высота ленты — от неё считается, помещается ли карусель в полный рост. */
  const [viewH, setViewH] = useState(0);
  /** Какая карточка колоды сверху. Живёт в экране: он знает, какие приглашения уже разобрали. */
  const [invIdx, setInvIdx] = useState(0);
  /** Сколько раз заходили на главную: карусель по этому числу коротко качается — «меня можно листать». */
  const [hint, setHint] = useState(0);

  /** Встреча и приглашения грузятся независимо: сбой одного не прячет другое. */
  const load = useCallback(async () => {
    if (!me) { setLoading(false); return; }
    const [i, pl] = await Promise.all([
      agent.homeInvites(me, true).catch(() => null),
      agent.plans(me).catch(() => null),
    ]);
    // Ближайшая ЖИВАЯ встреча: назначенная и ещё не прошедшая, самая ранняя из них. Отменённые и
    // прошедшие сюда не попадают — главная показывает то, к чему человек собирается, а не архив.
    const live = ((pl as any)?.plans || [])
      .filter((p: any) => (p.state === 'confirmed' || p.state === 'proposed') && p.starts_at)
      .sort((a: any, b: any) => (a.starts_at || 0) - (b.starts_at || 0));
    setNextPlan(live[0] || null);
    if (i) {
      const next = homeInvites((i as any)?.invites || []);
      /*
        Лица греем СРАЗУ, как только пришёл список, — до того, как колоду нарисуют: иначе карточка
        появлялась пустой и лицо проявлялось через паузу. Греем всю колоду: её листают подряд.
      */
      warmPhotos(next.map((x: any) => x?.from?.photo));
      setInvites((prev) => {
        // Индекс сбрасывается, только когда СОСТАВ изменился: после ответа на приглашение список
        // приходит короче, и прежний индекс показал бы пустое место. При том же составе позиция
        // сохраняется — иначе возврат с экрана приглашения отбрасывал бы колоду в начало.
        const same = prev.length === next.length
          && prev.every((p, k) => String(p.id) === String(next[k]?.id));
        if (!same) setInvIdx(0);
        return next;
      });
      setInviteError(false);
    } else {
      setInviteError(true);
    }
    setLoading(false);
  }, [me]);

  /*
    КОЛЕСО ПЕРЕМЕШИВАЕТСЯ ПРИ КАЖДОМ ЗАХОДЕ НА ГЛАВНУЮ (владелец 17.10.2026). Порядок — состояние
    экрана: пока человек здесь, карточки не прыгают; ушёл и вернулся — новая раскладка.
  */
  const [wheelOrder, setWheelOrder] = useState<string[]>(shuffledWheelKeys);
  useFocusEffect(useCallback(() => { load(); setHint((n) => n + 1); setWheelOrder(shuffledWheelKeys()); }, [load]));
  const wheel = wheelInOrder(wheelOrder);

  const refresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  /**
   * Строка на главной — не поле, а кнопка. Печатать тут негде: разговор идёт в чате с Kleal, и
   * набирать первую фразу на одном экране, чтобы дочитать ответ на другом, незачем. Нажатие сразу
   * открывает чат, клавиатура поднимается уже там.
   */
  const toBuddy = () => router.navigate('/buddy');

  /*
    КАРУСЕЛЬ СЖИМАЕТСЯ, КОГДА ЭКРАН НИЖЕ КАДРА — и только тогда. Всё остальное на главной одного
    роста на любом телефоне (шапка, колода, строка), поэтому уступать может только она. Выше кадра
    карусель остаётся 1:1, а лишнее уходит в промежуток над колодой.
  */
  const fixed = insets.top + HEAD_H + CARD_GAP + MIN_MID + STACK_H + STACK_TO_ASK + ASK_H + ASK_TO_NAV + navH;
  const full = moodGeometry(width, 1);
  const moodScale = viewH ? Math.max(0.62, Math.min(1, (viewH - fixed) / (full.height - full.cardTop))) : 1;
  // Геометрию считает сама карусель: на узком экране карточка уже 299, и отступы сжимаются с ней.
  const mood = moodGeometry(width, moodScale);
  const first = me.trim().split(/\s+/)[0] || '';

  const deck: any[] = [
    // Встреча — такой же житель колоды, как приглашение: `kind` отличает её при отрисовке.
    ...(nextPlan ? [{ key: 'plan', kind: 'plan', plan: nextPlan }] : []),
    ...(invites.length
      ? invites.map((inv) => ({ ...inv, kind: 'invite', key: String(inv.id) }))
      // Пустая карточка приглашений — тоже житель: без неё колода из одной встречи не сказала бы,
      // что приглашений просто нет.
      : [{ key: 'empty', kind: 'empty' }]),
  ];

  return (
    <View style={s.wrap}>
      {/*
        ФОН ИДЁТ ЗА КАРУСЕЛЬЮ (решение владельца 17.10.2026). Раньше здесь лежала фотография цветка
        с кадра (assets/art/home/bg.jpg) — «не наш стиль». Теперь у каждой карточки свой свет под
        общей шёлковой фактурой, и он перетекает вслед за пальцем: см. src/components/MoodBackdrop.tsx.
      */}
      <MoodBackdrop keys={wheel.map((it) => it.key)} x={track?.x || null} pitch={track?.pitch || 0} />

      <ScrollView onScroll={navCollapse} scrollEventThrottle={16}
        onLayout={(e) => setViewH(e.nativeEvent.layout.height)}
        contentContainerStyle={[s.scroll, { paddingTop: insets.top }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={color.primary} />}
      >
        {/*
          Карусель стоит ПОД шапкой в порядке отрисовки: её предметы выходят вверх за карточку
          (мартини — на 65 пунктов), и полоса карусели начинается выше, чем кончается шапка. Шапка
          рисуется поверх и пропускает касания мимо своих кнопок (`box-none`), так что колокольчик
          нажимается, а жест по свободному месту шапки листает карусель.
        */}
        <View style={{ height: HEAD_H + CARD_GAP + mood.height - mood.cardTop }}>
          <View style={[s.mood, { top: HEAD_H + CARD_GAP - mood.cardTop }]}>
            <MoodCarousel
              items={wheel}
              hint={hint}
              scale={moodScale}
              // Нажатие по центральной карточке открывает создание интента с уже сказанной фразой.
              onPick={(it) => router.navigate({ pathname: '/create', params: { seed: it.query } })}
              onTrack={onTrack}
            />
          </View>
          <View style={s.head} pointerEvents="box-none">
            {/* Гарнитура по языку — в шрифте борда нет кириллицы (см. displayFamily). */}
            <Text
              style={[s.hello, { fontFamily: displayFamily(lang) }, lang === 'ru' && s.helloRu]}
              numberOfLines={1}
              adjustsFontSizeToFit
              minimumFontScale={0.7}
            >
              {first ? HOME.hey(first) : HOME.hello()}
            </Text>
            {/* Колокольчик — только про новое: на что ответили и что закрылось, уже не новость. */}
            <NotifyBubble
              invites={invites.filter((x) => x.type !== 'one_to_one' || !x.status || x.status === 'pending')}
              onPick={(inv) => router.navigate({ pathname: '/invite', params: { id: inv.id } })}
            />
          </View>
        </View>

        <View style={s.mid} />

        {loading ? (
          <ActivityIndicator style={s.loading} color={color.primary} />
        ) : inviteError && !nextPlan ? (
          <View style={s.inviteError}>
            <Text style={s.errText}>{HOME.inviteLoadFailed()}</Text>
            <Pressable accessibilityRole="button" onPress={load} style={s.retryBtn}>
              <Text style={s.retryText}>{HOME.retry()}</Text>
            </Pressable>
          </View>
        ) : (
          /*
            Колода — компонент «Home Card» с тремя краями под ней (GR.01): сверху одна карточка, за ней
            видно, что есть ещё. Встреча идёт первой: она про назначенное время, и её нельзя задвинуть
            за приглашение, которого может и не быть.
          */
          <CardStack
            items={deck}
            index={invIdx}
            onIndex={setInvIdx}
            emptyHint={invites.length ? HOME.invitesAllSeen() : ''}
            render={(it: any) => (
              it.kind === 'plan' ? <PlanCard plan={it.plan} me={me} />
              : it.kind === 'empty' ? <EmptyInviteCard />
              : it.type === 'group' ? <GroupInviteCard inv={it} />
              : <DirectInviteCard inv={it} />
            )}
          />
        )}
        <View style={{ height: STACK_TO_ASK + ASK_H + ASK_TO_NAV + navH }} />
      </ScrollView>

      {/*
        «KLEAL PROMPT» (GR.01): стеклянная строка 48 на всю ширину без полей 20, подсказка Geist 15/20
        серым, справа микрофон 24 тем же серым. Без значка чата слева и без красного круга под
        микрофоном — на кадре строка тихая, акцент экрана — карусель. Поле по виду, кнопка по
        действию (см. toBuddy).
      */}
      <View style={[s.dock, { bottom: navH + ASK_TO_NAV }]} pointerEvents="box-none">
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={HOME.ask()}
          style={({ pressed }) => [s.ask, pressed && { transform: [{ scale: 0.985 }] }]}
          onPress={toBuddy}
        >
          <GlassSurface tone="light" radius={999} pointerEvents="none" style={[StyleSheet.absoluteFill, s.askGlass]} />
          <Text style={s.askText} numberOfLines={1}>{HOME.ask()}</Text>
          <IconMic size={24} c={color.muted} />
        </Pressable>
      </View>

      {/*
        Панель прибита к низу экрана и лежит поверх ленты; её высота меряется — от неё отступает
        строка ввода и хвост ленты.
      */}
      <View style={s.navFloat} onLayout={(e) => setNavH(e.nativeEvent.layout.height)} pointerEvents="box-none">
        <BottomNav />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: '#F5F1EC' },
  scroll: { flexGrow: 1 },
  /** Полоса карусели лежит под шапкой и выходит за неё вверх — см. разметку. */
  mood: { position: 'absolute', left: 0, right: 0 },
  /*
    «Greeting Header» 390×56, поля 8/20: «Hey Mateo 👋» — TASA Orbiter 700 28 с разрядкой −0,28, и
    стеклянный колокольчик 40 справа. Высота строки 34, а не 24 с кадра: у Figma там текст выше своей
    рамки, а в RN рамка обрезала бы и хвосты, и эмодзи.
  */
  head: {
    height: HEAD_H, flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: 20, paddingVertical: 8,
  },
  hello: { flex: 1, fontSize: 28, lineHeight: 34, letterSpacing: -0.28, color: color.fg },
  /** Unbounded шире TASA примерно на четверть — русское приветствие мельче, иначе имя обрезается. */
  helloRu: { fontSize: 22, lineHeight: 30, letterSpacing: 0 },
  /** Промежуток над колодой — всё, что экран даёт сверх кадра, уходит сюда. */
  mid: { flexGrow: 1, minHeight: MIN_MID },
  loading: { marginVertical: 48 },
  inviteError: { gap: 8, alignItems: 'flex-start', paddingHorizontal: 20, minHeight: STACK_H },
  errText: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.fg, opacity: 0.7 } as any,
  retryBtn: { paddingVertical: 8, paddingHorizontal: 14, borderRadius: 999, backgroundColor: color.card },
  retryText: { fontFamily: font.textSemibold, fontSize: 11, lineHeight: 16, color: color.primary } as any,

  dock: { position: 'absolute', left: 20, right: 20 },
  /** Строка 350×48: поля 16 слева и 12 справа, как «field» на кадре. */
  ask: {
    height: ASK_H, borderRadius: 999, flexDirection: 'row', alignItems: 'center',
    paddingLeft: 16, paddingRight: 12, gap: 8,
  },
  /** Стекло строки — белое 56% на кадре; светлый тон стекла даёт 46% и собственный материал сверху. */
  askGlass: { borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(255,255,255,0.7)' },
  askText: { flex: 1, fontFamily: font.text, fontSize: 15, lineHeight: 20, color: color.muted } as any,
  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },
});
