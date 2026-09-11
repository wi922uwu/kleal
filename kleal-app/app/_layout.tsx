import React, { useEffect, useState } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useFonts } from 'expo-font';
import { Asset } from 'expo-asset';
import { initLang } from '../src/i18n';
import { restore } from '../src/state';
import { startSummaryWatch } from '../src/profile';
import { color } from '../src/theme';
import { PostCallPrompt } from '../src/components/PostCallPrompt';

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
  require('../assets/art/logo-wordmark.png'),
  require('../assets/art/welcome-hand.png'),
  // Intro can be opened directly: its fixed photo must be ready before the first frame.
  require('../assets/art/usp-friends-v2.jpg'),
];
/**
 * Графика ГЛАВНОЙ. Греется раньше всего остального фонового, и это не вкусовщина: вернувшийся
 * человек попадает на главную сразу после заставки, а экранов входа больше не увидит никогда.
 *
 * Здесь же самые тяжёлые файлы приложения — шесть картинок на 2.6 МБ, до 693 КБ каждая. Пока они
 * не грелись вовсе, и это было видно: на месте картинки стоял серый квадрат, который сменялся
 * рисунком через заметную паузу. В заставку их класть нельзя — двумя с половиной мегабайтами
 * запуск удлиняется для всех, включая тех, кто до главной ещё не дошёл.
 */
const ART_HOME = [
  require('../assets/art/wheel/sneaker.png'),
  require('../assets/art/wheel/padel.png'),
  require('../assets/art/wheel/gamepad.png'),
  require('../assets/art/wheel/cherries.png'),
  require('../assets/art/wheel/laptop.png'),
  require('../assets/art/wheel/disco.png'),
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
  ['auth-code'], ['auth-email'], ['login'], ['summary'], ['done'], ['chat'],
  ['buddy'], ['create'], ['intent'], ['results'], ['candidate'], ['person'],
  ['invite'], ['ginvite'], ['group-invite'], ['conversation'], ['plan'],
  ['group'], ['gplan'], ['group-report'], ['myintent'], ['map'], ['map-intent'],
  ['profile/interests'], ['profile/personality'], ['profile/safety'], ['profile/test'],
  ['settings/index'], ['settings/account'], ['settings/availability'],
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
      Asset.loadAsync(ART_HOME)
        .catch(() => {})
        .finally(() => { Asset.loadAsync(ART_REST).catch(() => {}); });

      // Сводка догоняет профиль сама, с какого бы экрана он ни изменился. Включается ПОСЛЕ
      // restore(): иначе первое же восстановление с диска выглядит как правка и зовёт модель.
      startSummaryWatch();
    });
  }, []);

  // Ждём и состояние, и шрифты: первый экран набран Special Gothic, и подмена системного на
  // фирменный уже после первого кадра видна как скачок заголовка.
  if (!ready || !fontsReady) {
    return (
      <View style={{ flex: 1, backgroundColor: color.bg, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator color={color.primary} />
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: color.bg },
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
        }}
      >
        {/*
          НИ ОДИН ЭКРАН НЕ ЛЕЖИТ В СТОПКЕ ДВАЖДЫ.

          Это и есть ответ на «смахиваю — попадаю в миллиард экранов». Стопка росла на ровном
          месте: план открывает чат, из чата снова план, из плана снова чат — и каждый раз это
          НОВЫЙ экран, потому что `navigate` считает разными два вызова одного маршрута с разными
          параметрами. Десять минут переписки — и «назад» надо было нажать восемь раз, проходя те
          же два экрана по кругу.

          `dangerouslySingular` даёт маршруту постоянный опознаватель (имя маршрута), и переход на
          уже открытый экран ВОЗВРАЩАЕТ к нему, обновляя параметры, вместо того чтобы класть копию.
          Название пугающее, но опасность у него одна и здесь неприменимая: если бы продукту нужны
          были два разных экземпляра одного экрана рядом в стопке (два чата подряд, две карточки),
          они бы схлопнулись в один. У нас таких мест нет — чат один, план один, карточка одна, и
          параметры в них меняются, а не размножаются.

          Перечислены ВСЕ экраны, а не только те, у которых свои настройки: пропущенный остался бы
          с прежним поведением, и стопка снова росла бы — но уже в одном незаметном месте.
        */}
        {SCREENS.map(([name, options]) => (
          <Stack.Screen key={name} name={name} dangerouslySingular options={options as any} />
        ))}
      </Stack>
      <PostCallPrompt />
    </SafeAreaProvider>
  );
}
