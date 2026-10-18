/**
 * Поиск на карте — кадры «Search · Map» (1688-27392) и «Search Map · Pin selected» (1834-52500).
 *
 * ЧТО ЗДЕСЬ ПОКАЗАНО. Пин — не человек, а его ОТКРЫТЫЙ ИНТЕНТ: встреча, место которой он назвал
 * сам. Это единственная причина, по которой карта людей вообще допустима: домашняя точка человека
 * клиенту не отдаётся никогда (Вердикт#22, `matching_core/contracts/geo_privacy.py`), а место
 * встречи публикуется осознанно — иначе на неё нельзя прийти. Если сюда когда-нибудь приедет
 * координата человека, а не встречи, — это не новая возможность, а утечка.
 *
 * ПОЧЕМУ ЭКРАН ЗАБИРАЕТ ВКЛАДКУ «ПОИСК». В нижней панели она была приглушена и никуда не вела.
 * Данные для неё лежали готовые: `/api/agent/explore` отдаёт открытые интенты с координатами, и до
 * сих пор её не звал ни один экран.
 *
 * СЕГМЕНТЫ «КАРТА / ОНЛАЙН». Карта показывает Offline/Hybrid по адресу встречи, а мировой
 * обзор — Online/Hybrid только на уровне подтверждённой страны.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Animated, Easing } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Stack, useRouter } from 'expo-router';
import * as Location from 'expo-location';
import { agent, getSession, mediaUrl } from '../src/api';
import { useOnb } from '../src/state';
import { MAP, MORPH, ExplorePin, stackedAt, centerOf, intentReplyError } from '../src/explore';
import { buildOfflineIntentMapModel } from '../src/offline-map-feed';
import {
  buildOnlineIntentGlobeModel, onlineIntentGlobeCopy, type OnlineIntentGlobeStatus, type OnlineIntentItem,
} from '../src/online-intent-globe';
import { confirmedOnlineCountryRows } from '../src/online-map-feed';
import { useLang } from '../src/i18n';
import { sendIntentReply } from '../src/invites';
import { ExploreMap } from '../src/components/ExploreMap';
import { OnlineIntentGlobe } from '../src/components/OnlineIntentGlobe';
import { GlobeAsk } from '../src/components/GlobeAsk';
import { NearbyIntentSheet } from '../src/components/NearbyIntentSheet';
import { BottomNav } from '../src/components/BottomNav';
import { IconSearch, IconLocate, IconMap, IconGlobe, IconClock } from '../src/components/icons';
import { CategoryGlyph, iconNameFor } from '../src/components/category-icons';
import { color, radius, shadow, space, type } from '../src/theme';
import RAnimated from 'react-native-reanimated';
import { HomeCard, Face, Chunk, metaIcon } from '../src/components/HomeCards';
import { GlassToast } from '../src/components/Glass';
import { riseIn } from '../src/components/LiquidGlass';
import { IconPin as IconPinMeta, IconPerson } from '../src/components/icons';

/** Доля перехода, к которой плашки карты растаяли (туда) и с которой проступают (обратно). */
const CHROME_AT = 0.22;
/** Сколько занимает нижняя навигация над безопасным отступом: панель карты и лист считают от неё. */
const NAV_CLEAR = 84;

export default function MapScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const st = useOnb();
  const lang = useLang();
  const me = String(st.profile?.name || '').trim();

  const [pins, setPins] = useState<ExplorePin[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [view, setView] = useState<'map' | 'online'>('map');
  const [geoDenied, setGeoDenied] = useState(false);
  const [onlineRows, setOnlineRows] = useState<any[]>([]);
  const [onlineStatus, setOnlineStatus] = useState<'idle' | OnlineIntentGlobeStatus>('idle');
  const [picked, updatePicked] = useState<ExplorePin | null>(null);
  const [sending, setSending] = useState(false);
  const [replyError, setReplyError] = useState('');
  const replyGeneration = useRef(0);
  const setPicked = useCallback((pin: ExplorePin | null) => {
    replyGeneration.current += 1;
    updatePicked(pin); setSending(false); setReplyError('');
  }, []);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { setPicked(null); }, [st.session, setPicked]);
  /** Итог отклика с карты — короткий тост над панелью: «отправлено» или почему нет. */
  const [toast, setToast] = useState<{ title: string; note?: string } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const say = useCallback((t: { title: string; note?: string }) => {
    setToast(t);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2600);
  }, []);
  useEffect(() => () => { if (toastTimer.current) clearTimeout(toastTimer.current); }, []);
  /** Скрытые «не сейчас» — только на время сеанса: это не отказ, а «убери с глаз». */
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [showMe, setShowMe] = useState(false);
  const [recenter, setRecenter] = useState(0);
  const home = useRef<{ lat: number; lon: number } | null>(null);

  /*
   * ПЕРЕХОД «КАРТА → ОНЛАЙН» — ОДНА КАРТА, КОТОРАЯ СВОРАЧИВАЕТСЯ В ПЛАНЕТУ.
   * Второго шара больше нет: карта интентов живёт в глобус-проекции, и отъезд её камеры к
   * нулевому масштабу и есть превращение плоскости в планету (ночную — схема перекрашивается
   * по дороге). Раньше здесь лежали два слоя — карта и отдельный шар на three.js, — которые
   * приходилось подгонять друг под друга по размеру и повороту и сводить перекрёстным
   * затуханием; теперь подгонять нечего.
   * `trans` (0 — карта, 1 — планета) двигает только НАДПИСИ поверх карты: плашки «сколько
   * рядом» и карточку пина туда, кнопку со списком интентов обратно.
   */
  const trans = useRef(new Animated.Value(0)).current;
  const [mapMode, setMapMode] = useState<'city' | 'planet'>('city');
  /** Выбранная страна на планете — общая для плашек и списка. */
  const [country, setCountry] = useState<string | null>(null);
  /** Счётчик тапов по плашке страны: лист сам открывается и подвозит раздел. */
  const [pickSignal, setPickSignal] = useState(0);
  /** Счётчик нажатий лупы во вкладке «Онлайн»: она и открывает список интентов. */
  const [openSignal, setOpenSignal] = useState(0);
  /** Лупа во вкладке «Карта»: список интентов рядом — тот же лист, только светлый. */
  const [nearbyOpen, setNearbyOpen] = useState(false);
  /*
   * Нажали строку в списке — камера едет к этому пину. Счётчик, а не координата: два нажатия
   * подряд по одной строке должны везти дважды, а объект с теми же числами React считает
   * прежним, и эффект не запускается.
   */
  const [focusPin, setFocusPin] = useState<{ lat: number; lon: number; n: number } | null>(null);
  const focusStep = useRef(0);
  const flyToPin = useCallback((pin: ExplorePin) => {
    focusStep.current += 1;
    setFocusPin({ lat: pin.lat, lon: pin.lon, n: focusStep.current });
  }, []);
  /** Под открытой карточкой карта приглушается: иначе цветная карта спорит с текстом на ней. */
  const dim = useRef(new Animated.Value(0)).current;
  /*
   * ТЁМНЫЙ ИНТЕРФЕЙС НАД ПЛАНЕТОЙ. Навигация, лупа и сегменты темнеют, когда карта на середине
   * перехода становится ночной, и светлеют сразу с началом возврата — вместе с рассветом карты.
   */
  const [dark, setDark] = useState(false);
  useEffect(() => {
    Animated.timing(dim, { toValue: picked ? 1 : 0, duration: 220, easing: Easing.out(Easing.quad), useNativeDriver: true }).start();
  }, [picked, dim]);
  const darkTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (darkTimer.current) clearTimeout(darkTimer.current); }, []);
  /** Сколько пикселей снизу закрыл лист: планета уходит в оставшееся окно. */
  const [sheetBottom, setSheetBottom] = useState(0);
  /** «Спроси шар»: веса стран от Буди, волна ожидания и место под карточками совпадений. */
  const [askW, setAskW] = useState<Record<string, number> | null>(null);
  const [askScan, setAskScan] = useState(false);
  const [askBottom, setAskBottom] = useState(0);
  /*
   * Панель «поиск · Карта/Онлайн · фильтры» уходит, пока открыт лист: она стояла ровно поверх
   * карточек. Нижняя навигация остаётся — под неё лист сам оставляет место.
   */
  const barA = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    Animated.timing(barA, { toValue: sheetBottom > 0 ? 0 : 1, duration: 200, easing: Easing.out(Easing.quad), useNativeDriver: true }).start();
  }, [sheetBottom, barA]);
  const switchTo = useCallback((next: 'map' | 'online') => {
    if (next === view) return;
    setView(next);
    if (darkTimer.current) { clearTimeout(darkTimer.current); darkTimer.current = null; }
    if (next === 'online') {
      setPicked(null);
      setNearbyOpen(false);
      setMapMode('planet');
      darkTimer.current = setTimeout(() => { darkTimer.current = null; setDark(true); }, MORPH.total * 0.5);
    } else {
      setMapMode('city');
      setSheetBottom(0);
      setDark(false);
    }
    // Линейно: кривая движения — у самой камеры карты, а здесь только окна проявления надписей.
    Animated.timing(trans, {
      toValue: next === 'online' ? 1 : 0,
      duration: MORPH.total,
      easing: Easing.linear,
      useNativeDriver: true,
    }).start();
  }, [view, trans]);

  /** Нажали плашку страны на самой планете. */
  const pickCountry = useCallback((code: string) => {
    setCountry(code);
    setPickSignal((n) => n + 1);
  }, []);

  const load = useCallback(async () => {
    if (!me) { setLoading(false); return; }
    setLoading(true);
    try {
      const r: any = await agent.mapFeed(me, 'offline');
      const model = buildOfflineIntentMapModel(r);
      setPins(model.pins);
      setFailed(false);
    } catch {
      setPins([]);
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [me]);

  useEffect(() => { load(); }, [load]);

  const loadOnline = useCallback(async () => {
    if (!me) { setOnlineStatus('ready'); return; }
    setOnlineStatus('loading');
    try {
      const response: any = await agent.mapFeed(me, 'online');
      setOnlineRows(Array.isArray(response?.items) ? response.items : []);
      setOnlineStatus('ready');
    } catch {
      setOnlineRows([]);
      setOnlineStatus('error');
    }
  }, [me]);

  useEffect(() => {
    // Лента планеты грузится заранее, но ПОСЛЕ того, как карта открылась: две загрузки разом
    // на старте экрана — это рывок на первом же касании карты.
    if (onlineStatus !== 'idle') return;
    const timer = setTimeout(loadOnline, 1500);
    return () => clearTimeout(timer);
  }, [loadOnline, onlineStatus]);

  const visible = useMemo(() => pins.filter((p) => !hidden.has(p.id)), [pins, hidden]);
  const stacks = useMemo(() => stackedAt(visible), [visible]);
  const onlineModel = useMemo(
    () => buildOnlineIntentGlobeModel(confirmedOnlineCountryRows(onlineRows), { locale: lang }),
    [lang, onlineRows],
  );
  const onlineCopy = onlineIntentGlobeCopy(onlineModel.locale);
  const onlineItems = useMemo(() => onlineModel.countries.flatMap((c) => c.intents), [onlineModel]);
  const askProfile = useMemo(() => ({
    interests: st.profile?.interests?.explicit || [], city: st.profile?.city, languages: st.profile?.languages,
  }), [st.profile?.interests?.explicit, st.profile?.city, st.profile?.languages]);
  const onlineTotal = onlineModel.stats.total;
  /** Страны для плашек на планете: те же данные, что у списка. */
  const globeCountries = useMemo(
    () => onlineModel.countries.map((c) => ({
      code: c.code, lat: c.latitude, lon: c.longitude, count: c.count,
      ...(askW ? { w: askW[c.code] ?? 0 } : {}),
    })),
    [onlineModel, askW],
  );

  /**
   * «Где я». Разрешение спрашивается ТОЛЬКО по нажатию, а не при открытии экрана: карта полезна и
   * без него, а окно системного запроса на первом же кадре читается как требование.
   */
  const locate = useCallback(async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') { setGeoDenied(true); return; }
      const pos = await Location.getCurrentPositionAsync({});
      home.current = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      setGeoDenied(false);
      setShowMe(true);
      setRecenter((n) => n + 1);
    } catch { setGeoDenied(true); }
  }, []);

  const respond = useCallback(async () => {
    if (!picked || sending) return;
    const session = getSession();
    const generation = replyGeneration.current;
    const current = () => mounted.current && getSession() === session && replyGeneration.current === generation;
    setSending(true);
    setReplyError('');
    try {
      const r = await sendIntentReply(me, { name: picked.who, id: picked.whoId }, picked);
      if (!current()) return;
      if (r.ok) { setPicked(null); say({ title: MAP.sentWaiting() }); }
      else setReplyError(intentReplyError(r));
    } catch (error) {
      if (current()) setReplyError(intentReplyError({}));
    } finally {
      if (current()) setSending(false);
    }
  }, [picked, sending, me, say]);

  const notNow = useCallback(() => {
    if (!picked) return;
    setHidden((s) => new Set(s).add(picked.id));
    setPicked(null);
  }, [picked]);

  /*
   * Откуда смотреть: своя точка (если разрешили), иначе город из анкеты, иначе самая плотная
   * кучка пинов. Среднее по всем пинам сюда не годится: два пина на разных континентах давали
   * центр в пустыне.
   */
  const profilePoint = useMemo(() => {
    const la = Number(st.profile?.geo?.coarseLat);
    const lo = Number(st.profile?.geo?.coarseLon);
    return Number.isFinite(la) && Number.isFinite(lo) && (la !== 0 || lo !== 0) ? { lat: la, lon: lo } : null;
  }, [st.profile?.geo?.coarseLat, st.profile?.geo?.coarseLon]);
  const center = home.current || profilePoint || centerOf(visible);
  const openIntent = useCallback((pin: ExplorePin) => {
    router.navigate({ pathname: '/map-intent', params: { id: pin.id, view: 'offline' } } as any);
  }, [router]);
  const openOnlineIntent = useCallback((item: OnlineIntentItem) => {
    router.navigate({ pathname: '/map-intent', params: { id: item.id, view: 'online' } } as any);
  }, [router]);

  return (
    <View style={s.root}>
      {/*
        ЖЕСТА «НАЗАД» НА ЭТОМ ЭКРАНЕ НЕТ. Здесь любое движение пальца — это движение карты или
        шара, и протяжка от левого края означала не «вернуться», а «повернуть». Стек перехватывал
        её раньше карты, и человек, крутя глобус, случайно смахивал весь экран. Возврат — кнопкой.
      */}
      <Stack.Screen options={{ gestureEnabled: false }} />
      {/* ОДНА КАРТА НА ОБЕ ВКЛАДКИ: в «Онлайне» она сама свёрнута в планету. */}
      <ExploreMap
        pins={visible}
        center={center}
        onPick={setPicked}
        stacks={stacks}
        showMe={showMe}
        recenter={recenter}
        selectedId={picked?.id || null}
        mode={mapMode}
        focusPin={focusPin}
        countries={view === 'online' ? globeCountries : null}
        selectedCountry={country}
        onPickCountry={pickCountry}
        reserveBottom={Math.max(sheetBottom, askBottom)}
        scanning={askScan}
      />

      {/* Надписи карты: тают в начале ухода и проступают в конце возврата, а не исчезают щелчком. */}
      <Animated.View
        pointerEvents={view === 'map' ? 'box-none' : 'none'}
        style={[StyleSheet.absoluteFill, {
          opacity: trans.interpolate({ inputRange: [0, CHROME_AT, 1], outputRange: [1, 0, 0] }),
        }]}
      >
        {/* Сверху карта чистая: сколько интентов рядом, говорит бейдж на лупе, список — за ней. */}
        {loading ? <ActivityIndicator style={[s.spin, { top: insets.top + 24 }]} color={color.primary} /> : null}

        {/* Пусто и сломано — разные состояния: «никого рядом» это не ошибка связи. */}
        {!loading && !visible.length ? (
          <View style={[s.empty, { top: insets.top + 90 }]}>
            <Text style={s.emptyTitle}>{failed ? MAP.failed() : MAP.empty()}</Text>
            <Text style={s.emptyNote}>{failed ? '' : MAP.emptyNote()}</Text>
            {failed ? (
              <Pressable accessibilityRole="button" onPress={load} style={s.retry}>
                <Text style={s.retryText}>{MAP.retry()}</Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}

        {geoDenied ? (
          <View style={[s.notice, { bottom: 220 + insets.bottom }]}>
            <Text style={s.noticeText}>{MAP.noGeo()}</Text>
          </View>
        ) : null}

        {/* «Где я» — над карточкой выбранного, чтобы она её не накрывала. */}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={MAP.locate()}
          onPress={locate}
          style={[s.locate, { bottom: (picked ? 152 + 24 : 0) + 156 + insets.bottom }]}
        >
          <IconLocate size={20} c={color.fg} />
        </Pressable>

        {/*
          Приглушение — ПОД карточкой и НАД картой: карточка остаётся яркой, а цветная карта
          под ней отходит на шаг. Касания сквозь него проходят: это вуаль, а не заслонка.
        */}
        <Animated.View pointerEvents="none" style={[s.scrim, { opacity: dim }]} />

        {toast ? (
          <RAnimated.View entering={riseIn(0, 8)} style={[s.toastWrap, { bottom: NAV_CLEAR + insets.bottom + 72 }]} pointerEvents="none">
            <GlassToast title={toast.title} note={toast.note} />
          </RAnimated.View>
        ) : null}

        {picked ? <PinPreview pin={picked} sending={sending} error={replyError} onRespond={respond} onNotNow={notNow}
                              onOpen={() => openIntent(picked)} bottom={140 + insets.bottom} /> : null}

        <NearbyIntentSheet
          pins={visible}
          open={nearbyOpen}
          onClose={() => setNearbyOpen(false)}
          /*
            Нажатие на строку ведёт НЕ на отдельный экран, а к самому пину: лист уходит, камера
            подъезжает, снизу встаёт та же карточка, что и при нажатии на пин на карте. Так
            список и карта говорят об одном и том же, а открыть затею целиком — следующий шаг
            той же карточкой.
          */
          onOpen={(pin) => { setNearbyOpen(false); setPicked(pin); flyToPin(pin); }}
          navClear={NAV_CLEAR + insets.bottom}
          onSheet={setSheetBottom}
        />
      </Animated.View>

      {/* Надписи «Онлайна»: кнопка со счётчиком и лист со списком — поверх той же планеты. */}
      <Animated.View
        pointerEvents={view === 'online' ? 'box-none' : 'none'}
        style={[StyleSheet.absoluteFill, {
          opacity: trans.interpolate({ inputRange: [0, 1 - CHROME_AT, 1], outputRange: [0, 0, 1] }),
        }]}
      >
        <OnlineIntentGlobe
          model={onlineModel}
          status={onlineStatus === 'idle' ? 'loading' : onlineStatus}
          onRetry={loadOnline}
          onOpenIntent={openOnlineIntent}
          contentInsets={{ top: insets.top + 8, bottom: NAV_CLEAR + insets.bottom }}
          selected={country}
          onSelect={setCountry}
          onSheet={setSheetBottom}
          pickSignal={pickSignal}
          openSignal={openSignal}
          testID="search-online-intent-globe"
        />
        {/* «Спроси шар» — Буди отвечает светом стран и карточками совпадений. */}
        <GlobeAsk
          active={view === 'online' && sheetBottom === 0 && onlineStatus === 'ready' && onlineTotal > 0}
          items={onlineItems}
          profile={askProfile}
          me={me}
          bottom={NAV_CLEAR + insets.bottom + 56}
          topInset={insets.top + 8}
          onLight={setAskW}
          onFocus={setCountry}
          onScan={setAskScan}
          onReserve={(px) => setAskBottom(px ? px + 56 : 0)}
          onOpen={openOnlineIntent}
        />
      </Animated.View>

      {/* Панель поиска и сегменты — низ кадра, над нижней навигацией. */}
      <Animated.View
        pointerEvents={sheetBottom > 0 ? 'none' : 'auto'}
        style={[s.bar, { bottom: NAV_CLEAR + insets.bottom, opacity: barA }]}
      >
        {/* Лупа: открывает список — интентов рядом на карте, по странам на планете — и носит счётчик. */}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={view === 'online' ? onlineCopy.showList : MAP.nearbyList()}
          onPress={() => {
            if (view === 'online') setOpenSignal((n) => n + 1);
            else if (visible.length) setNearbyOpen(true);
          }}
          style={[s.round, dark && s.roundDark]}
        >
          <IconSearch size={20} c={dark ? color.glassLight : color.fg} />
          {(view === 'online' ? onlineTotal : visible.length) > 0 ? (
            <View style={s.roundBadge}>
              <Text style={s.roundBadgeText}>{Math.min(99, view === 'online' ? onlineTotal : visible.length)}{(view === 'online' ? onlineTotal : visible.length) > 99 ? '+' : ''}</Text>
            </View>
          ) : null}
        </Pressable>
        <View style={s.segments}>
          <Pressable onPress={() => switchTo('map')} style={[s.segment, view === 'map' && s.segmentOn]}>
            <IconMap size={18} c={color.onPrimary} />
            <Text style={[s.segmentText, view === 'map' && s.segmentTextOn]}>{MAP.map()}</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={() => switchTo('online')}
            style={[s.segment, view === 'online' && s.segmentOn]}
          >
            <IconGlobe size={18} c={color.onPrimary} />
            <Text style={s.segmentText}>{MAP.online()}</Text>
          </Pressable>
        </View>
      </Animated.View>

      {/* Панель прижата к низу абсолютом — как на главной. Всё остальное на этом экране тоже
          абсолютное (оно лежит поверх карты), и в обычном потоке панель всплывала к верхней
          кромке: кнопки были на месте, но не там, где их ищут. */}
      <View style={s.navFloat} pointerEvents="box-none">
        <BottomNav active="search" dark={dark} />
      </View>
    </View>
  );
}

/**
 * Карточка выбранного пина — та же «Home Card», что на главной (переделано 17.10.2026: «нанести
 * нашу идентику»). Лицо автора с бейджем темы, название затеи, кто и когда — значками фирменного
 * цвета, коралловая кнопка и тихое «Не сейчас» рядом. Появляется подъёмом, как карточки главной.
 * Нажатие по карточке — открыть затею целиком; по кнопке — откликнуться (у группы — открыть).
 */
function PinPreview({
  pin, sending, error, onRespond, onNotNow, onOpen, bottom,
}: {
  pin: ExplorePin;
  sending: boolean;
  error: string;
  onRespond: () => void;
  onNotNow: () => void;
  onOpen: () => void;
  bottom: number;
}) {
  const who = [pin.who, pin.age ? String(pin.age) : ''].filter(Boolean).join(', ');
  const group = pin.kind === 'group';
  return (
    <RAnimated.View key={pin.id} entering={riseIn(0, 8)} style={[s.cardWrap, { bottom }]}>
      {error ? <Text accessibilityRole="alert" style={s.replyError}>{error}</Text> : null}
      <HomeCard
        onPress={onOpen}
        avatar={(
          <View>
            <Face photo={pin.photo} name={pin.who} />
            <View style={s.avatarBadge}><CategoryGlyph name={iconNameFor(pin.topics[0] || '')} size={12} /></View>
          </View>
        )}
        title={pin.title || who}
        meta={(
          <>
            {who ? <Chunk icon={metaIcon(IconPerson)} text={who} shrink /> : null}
            {pin.when ? <Chunk icon={metaIcon(IconClock)} text={pin.when} /> : null}
            {!pin.when && pin.area ? <Chunk icon={metaIcon(IconPinMeta)} text={pin.area} shrink /> : null}
          </>
        )}
        action={group ? MAP.openIntent() : MAP.respond()}
        onAction={group ? onOpen : onRespond}
        busy={!group && sending}
        alt={{ label: MAP.notNow(), onPress: onNotNow }}
      />
    </RAnimated.View>
  );
}

// ===== вид
const s = StyleSheet.create({
  /*
   * Подложка экрана — космос, а не светлый фон темы. В середине перекрёстного затухания слои
   * полупрозрачны оба, и подложка просвечивает на четверть: светлая давала белую вспышку между
   * картой и шаром. В обычном виде её не видно вовсе — оба слоя непрозрачны.
   */
  root: { flex: 1, backgroundColor: '#05070f' },
  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },
  cardWrap: { position: 'absolute', left: 16, right: 16 },
  toastWrap: { position: 'absolute', left: 16, right: 16, alignItems: 'center' },
  scrim: { position: 'absolute', left: 0, top: 0, right: 0, bottom: 0, backgroundColor: 'rgba(17,19,26,0.22)' },

  spin: { position: 'absolute', alignSelf: 'center' },
  empty: {
    position: 'absolute', left: space.xl, right: space.xl,
    padding: space.lg, borderRadius: radius.xl, backgroundColor: color.card, ...shadow.card,
    gap: space.xs,
  },
  emptyTitle: { ...type.title, color: color.fg } as any,
  emptyNote: { ...type.bodySmall, color: color.muted } as any,
  retry: {
    marginTop: space.sm, alignSelf: 'flex-start',
    paddingHorizontal: space.lg, height: 40, borderRadius: radius.full,
    backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center',
  },
  retryText: { ...type.button, color: color.fg } as any,
  notice: {
    position: 'absolute', left: space.xl, right: space.xl, minHeight: 44,
    flexDirection: 'row', alignItems: 'center', gap: space.sm,
    paddingHorizontal: space.md, paddingVertical: space.sm,
    borderRadius: radius.xl, backgroundColor: color.card, ...shadow.card,
  },
  noticeText: { ...type.bodySmall, color: color.fg, flex: 1 } as any,
  noticeAction: { ...type.button, color: color.primary } as any,

  locate: {
    position: 'absolute', right: space.xl, width: 44, height: 44, borderRadius: 22,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center', ...shadow.card,
  },

  card: {
    position: 'absolute', left: space.xl, right: space.xl,
    padding: space.lg, borderRadius: radius.xxl, backgroundColor: color.card, ...shadow.card,
    gap: space.md,
  },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  avatarWrap: { width: 60, height: 60, alignItems: 'center', justifyContent: 'center' },
  avatar: { width: 56, height: 56, borderRadius: 28 },
  avatarEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  avatarInitial: { ...type.title, color: color.muted } as any,
  avatarBadge: {
    position: 'absolute', right: 0, bottom: 0, width: 24, height: 24, borderRadius: 12,
    backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center',
    borderWidth: 2, borderColor: color.card,
  },
  cardText: { flex: 1, gap: 2 },
  cardWho: { ...type.title, color: color.fg } as any,
  cardTitle: { ...type.bodySmall, color: color.muted } as any,
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 },
  meta: { ...type.bodySmall, color: color.fg } as any,
  chev: { transform: [{ rotate: '180deg' }] },

  actions: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  replyError: { ...type.bodySmall, color: color.danger } as any,
  primary: {
    flex: 1, height: 48, borderRadius: radius.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  primaryText: { ...type.button, color: color.onPrimary } as any,
  secondary: { flex: 1, height: 48, alignItems: 'center', justifyContent: 'center' },
  secondaryText: { ...type.button, color: color.fg } as any,

  bar: {
    position: 'absolute', left: space.xl, right: space.xl, height: 44,
    flexDirection: 'row', alignItems: 'center', gap: space.sm,
  },
  round: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: color.card,
    alignItems: 'center', justifyContent: 'center', ...shadow.card,
  },
  roundDark: { backgroundColor: color.glassDark },
  roundBadge: {
    position: 'absolute', top: -5, right: -6, minWidth: 22, height: 22, paddingHorizontal: 6,
    borderRadius: 11, backgroundColor: color.primary, borderWidth: 2, borderColor: color.card,
    alignItems: 'center', justifyContent: 'center',
  },
  roundBadgeText: { ...type.labelSmall, color: color.onPrimary, fontWeight: '700' } as any,
  segments: {
    flex: 1, height: 44, flexDirection: 'row', alignItems: 'center',
    borderRadius: radius.full, backgroundColor: color.fg, padding: 4,
  },
  segment: {
    flex: 1, height: 36, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, borderRadius: radius.full,
  },
  segmentOn: { backgroundColor: color.primary },
  segmentText: { ...type.button, color: color.onPrimary } as any,
  segmentTextOn: { color: color.onPrimary },
});
