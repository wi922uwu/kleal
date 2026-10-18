import { useEffect, useState } from 'react';
import { View, ActivityIndicator, Platform, StatusBar as RNStatusBar } from 'react-native';

/*
  ANDROID: ФОН ПОД СТРОКОЙ СОСТОЯНИЯ, КАК НА iPHONE. Без этого Android (Expo Go, Android 14) красил полосу
  над приложением в чёрный: сверху каждого экрана стояла чёрная плашка 136 px, а фирменный фон и
  стекло начинались под ней (снято на эмуляторе 18.10.2026). expo-status-bar 57 прозрачность больше не
  принимает — включаем её у системной строки напрямую. Отступы экранов и так идут от safe area.
*/
if (Platform.OS === 'android') {
  try {
    RNStatusBar.setTranslucent(true);
    RNStatusBar.setBackgroundColor('transparent');
  } catch { /* на новых Android край к краю уже включён — нечего делать */ }
}
import { BlurTargetView } from 'expo-blur';
import { Stack, router } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useFonts } from 'expo-font';
import { Asset } from 'expo-asset';
import { initLang } from '../src/i18n';
import { restore, checkSession } from '../src/state';
import { startSummaryWatch } from '../src/profile';
import { color } from '../src/theme';
import { PostCallPrompt } from '../src/components/PostCallPrompt';
import { AgeVerificationBoundary } from '../src/components/AgeVerificationBoundary';
import { MonetizationBoundary } from '../src/components/MonetizationBoundary';
import { recoveryScreenIdentity } from '../src/monetization-actions';
import { blurTargetRef } from '../src/components/LiquidGlass';
import { NavHost } from '../src/components/BottomNav';
import { VoiceOverlayHost } from '../src/voice';

/**
 * КАРТИНКИ ГРУЗЯТСЯ ДО ТОГО, КАК ПОНАДОБЯТСЯ.
 *
 * `require` на картинку не приносит её в память — он даёт только ссылку. Сам файл читается в тот
 * момент, когда `Image` впервые оказывается на экране, и до этого на его месте пусто. На экране
 * входа это особенно заметно: заголовок и кнопки уже стоят, а капля и значки проступают позже, и
 * кадр собирается на глазах.
 *
 * ЧЕРЕЗ ТУННЕЛЬ ЭТО НЕ МИЛЛИСЕКУНДЫ. В Expo Go каждая картинка едет по сети от Metro отдельным
 * запросом; фотография экрана пользы весит под триста килобайт и приезжает заметно позже, чем
 * появляется белый лист поверх неё.
 *
 * Поэтому список разделён надвое. Первый экран ЖДЁТ свои две картинки — заставка без логотипа это
 * пустой кремовый прямоугольник. Остальное греется в фоне, пока заставка держит свои 1,8 секунды:
 * к переходу на экран пользы фотография уже в кеше, а к входу — капля и значки.
 */
const ART_FIRST = [
  require('../assets/art/welcome-hand.png'),
  // Intro can be opened directly: its fixed photo must be ready before the first frame.
  require('../assets/art/usp-friends-v2.jpg'),
];
/**
 * Графика ГЛАВНОЙ. Греется раньше всего остального фонового, и это не вкусовщина: вернувшийся
 * человек попадает на главную сразу после заставки, а экранов входа больше не увидит никогда.
 *
 * Здесь же самые тяжёлые файлы приложения — карточки колеса (с 17.10.2026 двенадцать, WebP,
 * ~1,6 МБ вместе; раньше шесть PNG на 2.6 МБ, до 693 КБ каждая). Пока они
 * не грелись вовсе, и это было видно: на месте картинки стоял серый квадрат, который сменялся
 * рисунком через заметную паузу. В заставку их класть нельзя — двумя с половиной мегабайтами
 * запуск удлиняется для всех, включая тех, кто до главной ещё не дошёл.
 */
const ART_HOME = [
  // Карточки колеса — WebP с 17.10.2026: 12 штук легче прежних шести PNG, греем все.
  require('../assets/art/wheel/sneaker.webp'),
  require('../assets/art/wheel/padel.webp'),
  require('../assets/art/wheel/gamepad.webp'),
  require('../assets/art/wheel/cherries.webp'),
  require('../assets/art/wheel/laptop.webp'),
  require('../assets/art/wheel/disco.webp'),
  require('../assets/art/wheel/matcha.webp'),
  require('../assets/art/wheel/camera.webp'),
  require('../assets/art/wheel/bracelets.webp'),
  require('../assets/art/wheel/sunglasses.webp'),
  require('../assets/art/wheel/keychain.webp'),
  require('../assets/art/wheel/balloons67.webp'),
  // Тело Kleal в нижней панели. Не грелось вовсе — и на каждом новом экране со своей панелью
  // маскот ~0,5 с стоял одними глазами без тела (замечание владельца 17.10.2026).
  require('../assets/art/logo-mark-body.png'),
];

/**
 * Картинки ОНБОРДИНГА — орбита экрана входа и 3D-темы карты интересов (18.10.2026). Иван: «прогружаются
 * очень медленно, должны быть готовы уже на шаге выбора языка». Они мелкие (~180 КБ все вместе), поэтому
 * греются первыми, сразу после заставки, параллельно с главной: к шагу «Интересы» они давно в кэше.
 */
const ART_ONB = [
  require('../assets/art/logo-mark.png'),
  require('../assets/art/orbit/disco.webp'),
  require('../assets/art/orbit/sneaker.webp'),
  require('../assets/art/orbit/matcha.webp'),
  require('../assets/art/orbit/camera.webp'),
  require('../assets/art/orbit/gamepad.webp'),
  require('../assets/art/orbit/cherries.webp'),
  require('../assets/art/topics/sports.webp'),
  require('../assets/art/topics/social.webp'),
  require('../assets/art/topics/culture.webp'),
  require('../assets/art/topics/outdoors.webp'),
  require('../assets/art/topics/music.webp'),
  require('../assets/art/topics/games.webp'),
  require('../assets/art/topics/learning.webp'),
  require('../assets/art/topics/tech.webp'),
];

const ART_REST = [
  require('../assets/art/logo-mark.png'),
  require('../assets/art/icon-apple.png'),
  require('../assets/art/icon-google.png'),
  require('../assets/art/auth-keyhole.png'),
];

/**
 * ВСЕ ЭКРАНЫ ПРИЛОЖЕНИЯ И ИХ ПЕРЕХОДЫ.
 *
 * Раньше здесь перечислялись только особенные — те, у кого своя анимация. Теперь список полный,
 * потому что каждому нужен `dangerouslySingular` (см. разметку ниже): экран, забытый в этом
 * списке, снова начнёт копиться в стопке.
 *
 * Пусто вместо настроек — переход по умолчанию, `ios_from_right` из `screenOptions`.
 */
/** Вкладки нижней панели: смена раздела, а не шаг вглубь, — жёсткая смена кадра без сдвига. */
const TAB = { animation: 'none' } as const;
/**
 * Входные кадры не едут, а проявляются: заставка передаёт эстафету (`replace`), вход происходит
 * под чёрным занавесом, а «готово» — исход, а не шаг вглубь. Сдвиг вправо-влево врал бы трижды.
 */
const FADE = { animation: 'fade' } as const;

const SCREENS: [string, object?][] = [
  ['intro', FADE], ['auth', FADE], ['auth-done', FADE],
  ['home', TAB], ['activity', TAB], ['messages', TAB], ['profile/index', TAB],
  // История разговоров — модальным окном: заглянул и вернулся туда, откуда пришёл.
  ['history', { presentation: 'modal', animation: 'slide_from_bottom' }],
  ['auth-code'], ['auth-email'], ['age-verification'], ['summary'], ['done'], ['chat'], ['ai-fill'], ['ai-finish'],
  // Шаги мастера «Creating intent» на борде — ОДИН экран с общей шапкой (GR.04–GR.12): переход
  // от «что делаем» к остальным шагам проявляется, а не уезжает вбок, — шапка остаётся на месте.
  ['buddy'], ['create'], ['intent', FADE], ['results'], ['candidate'], ['person'],
  ['invite'], ['ginvite'], ['conversation'], ['plan'],
  ['group'], ['gmembers'], ['grole'], ['gplan'], ['group-report'], ['myintent'], ['map'], ['map-intent'],
  ['profile/interests'], ['profile/personality'], ['profile/safety'], ['profile/test'], ['profile/location'],
  ['plus'], ['settings/index'], ['settings/account'], ['settings/availability'],
  ['settings/blocked'], ['settings/privacy'], ['settings/visibility'],
];

export default function RootLayout() {
  const [ready, setReady] = useState(false);

  /**
   * ШРИФТЫ БОРДА. Special Gothic Expanded One — заголовки входных экранов, Geist — весь остальной
   * текст. Ключи здесь это `fontFamily` в стилях (см. `font` в theme.ts), поэтому имена должны
   * совпадать буквально: опечатка не роняет сборку, а тихо возвращает системный шрифт.
   *
   * Каждое начертание Geist — ОТДЕЛЬНЫЙ файл и отдельное семейство: в React Native `fontWeight`
   * поверх подключённого файла не работает, движок не синтезирует полужирный.
   */
  const [fontsReady] = useFonts({
    SpecialGothicExpandedOne: require('../assets/fonts/SpecialGothicExpandedOne.ttf'),
    'Geist-400': require('../assets/fonts/Geist-400.ttf'),
    'Geist-500': require('../assets/fonts/Geist-500.ttf'),
    'Geist-600': require('../assets/fonts/Geist-600.ttf'),
    /*
      Широкий дисплейный С КИРИЛЛИЦЕЙ. В шрифте борда её нет ни одной буквы (проверено по таблице
      символов: латиница 58 из 58, кириллица 0 из 64), и русские заголовки до сих пор набирались
      обычным полужирным Geist — то есть выглядели как системные. Unbounded покрывает кириллицу
      целиком и по характеру ближе всего к борду: такой же расширенный геометрический гротеск.
    */
    'Unbounded-700': require('../assets/fonts/Unbounded-700.ttf'),
    // Макет «First run» (сентябрь 2026): заголовки TASA Orbiter, цифры точечным Doto.
    'TASAOrbiter-700': require('../assets/fonts/TASAOrbiter-700.ttf'),
    'TASAOrbiter-600': require('../assets/fonts/TASAOrbiter-600.ttf'),
    'Doto-700': require('../assets/fonts/Doto-700.ttf'),
  });

  // Язык и незаконченный онбординг читаются до первого кадра: иначе экран успевает нарисоваться
  // по-английски и тут же перерисоваться по-русски, и это видно.
  useEffect(() => {
    // Картинки первого экрана — в общем ожидании: они и так грузятся параллельно языку и состоянию,
    // и почти никогда не оказываются самыми медленными. Упасть загрузка не должна ронять запуск:
    // без картинки экран некрасив, без запуска его нет вовсе — поэтому `catch` пустой.
    const first = Asset.loadAsync(ART_FIRST).catch(() => {});
    Promise.all([initLang(), restore(), first]).finally(() => {
      setReady(true);
      // Остальное греется уже под нарисованной заставкой и никого не ждёт. Порядок важен:
      // главная идёт первой, потому что до неё доходят все, а до экранов входа — только новые.
      Asset.loadAsync(ART_ONB).catch(() => {});
      Asset.loadAsync(ART_HOME)
        .catch(() => {})
        .finally(() => { Asset.loadAsync(ART_REST).catch(() => {}); });

      // Сводка догоняет профиль сама, с какого бы экрана он ни изменился. Включается ПОСЛЕ
      // restore(): иначе первое же восстановление с диска выглядит как правка и зовёт модель.
      startSummaryWatch();

      // Сессия могла истечь или быть погашена — тогда на вход, а не в пустое приложение.
      // См. checkSession в src/state.ts.
      checkSession().then((lost) => {
        if (!lost) return;
        try { router.replace('/intro'); } catch { /* навигатор ещё не готов — заставка уведёт сама */ }
      });
    });
  }, []);

  // Ждём и состояние, и шрифты: первый экран набран Special Gothic, и подмена системного на
  // фирменный уже после первого кадра видна как скачок заголовка.
  if (!ready || !fontsReady) {
    return (
      <View style={{ flex: 1, backgroundColor: color.ambientBase, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator color={color.primary} />
      </View>
    );
  }

  const stack = (
    <Stack
      screenOptions={{
        headerShown: false,
        /*
          Кремовая подложка стоит и ЗДЕСЬ, под самим навигатором: между экранами на кадр
          видно его собственный фон, и серый там читался как вспышка чужого цвета в тёплом
          приложении. Сам фирменный слой кладёт каждый экран своим `<Ambient />`.
        */
        contentStyle: { backgroundColor: color.ambientBase },
        /*
          ПЕРЕХОД ВГЛУБЬ — НАСТОЯЩИЙ iOS-ПЕРЕХОД, А НЕ ПОХОЖИЙ НА НЕГО.

          `slide_from_right` — своя анимация библиотеки: оба экрана едут с одной скоростью,
          без тени по кромке и без отставания нижнего. Со стороны это «сдвинули картинку».
          `ios_from_right` на iOS отдаёт переход системному контроллеру: уходящий экран
          отстаёт примерно втрое, по кромке приходящего лежит мягкая тень, кривая — та самая,
          что во всех родных приложениях, и работает возврат протяжкой от левого края.
          На Android та же анимация повторяется вручную, так что оба клиента двигаются
          одинаково, а не «как принято на своей платформе».
        */
        animation: 'ios_from_right',
        /*
          «НАЗАД» — ТОЛЬКО ОТ ЛЕВОГО КРАЯ, КАК ДО iOS 26. С iOS 26 система по умолчанию закрывает
          экран свайпом вправо из ЛЮБОЙ точки, и он перехватывал всё горизонтальное в приложении:
          ползунок радиуса и ленты дней/времени в мастере откатывали шаг, свайп по сообщению
          «ответить» закрывал чат (владелец 05.10.2026, проверено на симуляторе iOS 27).
          У нас горизонтальных жестов десятки — карусели, ленты, ползунки, ответ свайпом, — поэтому
          правило одно на всё приложение, а не заплатки по экранам.
        */
        fullScreenGestureEnabled: false,
      }}
    >
      {/*
        НИ ОДИН ЭКРАН НЕ ЛЕЖИТ В СТОПКЕ ДВАЖДЫ.

        Это и есть ответ на «смахиваю — попадаю в миллиард экранов». Стопка росла на ровном
        месте: план открывает чат, из чата снова план, из плана снова чат — и каждый раз это
        НОВЫЙ экран, потому что `navigate` считает разными два вызова одного маршрута с разными
        параметрами. Десять минут переписки — и «назад» надо было нажать восемь раз, проходя те
        же два экрана по кругу.

        Обычные маршруты имеют постоянную identity. Conversation и Plus сохраняют отдельный
        recoveryId для возврата A → Plus → C → Plus → A через dismissTo, без перестановки
        исходного native screen и потери пары/черновика.

        Перечислены ВСЕ экраны, а не только те, у которых свои настройки: пропущенный остался бы
        с прежним поведением, и стопка снова росла бы — но уже в одном незаметном месте.
      */}
      {SCREENS.map(([name, options]) => (
        <Stack.Screen key={name} name={name}
          dangerouslySingular={name==='conversation' || name==='plus' ? recoveryScreenIdentity : true}
          options={options as any} />
      ))}
    </Stack>
  );

  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      <AgeVerificationBoundary>
      {/*
        ANDROID: весь стек экранов — цель размытия, навбар — рядом с ней, поверх (см. NavHost).
        Иначе expo-blur на Android не размывает, а кладёт серую подложку.
      */}
      {Platform.OS === 'android' ? (
        <BlurTargetView ref={blurTargetRef} style={{ flex: 1 }}>{stack}</BlurTargetView>
      ) : stack}
      {Platform.OS === 'android' ? <NavHost /> : null}
      {/* Капля, кольца и замок записи голосового — над полем ввода, иначе поле их обрезает. */}
      <VoiceOverlayHost />
      <PostCallPrompt />
      <MonetizationBoundary />
      </AgeVerificationBoundary>
    </SafeAreaProvider>
  );
}
