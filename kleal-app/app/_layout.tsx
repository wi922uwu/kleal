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
];
const ART_REST = [
  require('../assets/art/usp-friends-v2.jpg'),
  require('../assets/art/logo-mark.png'),
  require('../assets/art/icon-apple.png'),
  require('../assets/art/icon-google.png'),
  require('../assets/art/auth-keyhole.png'),
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
      // Остальное греется уже под нарисованной заставкой и никого не ждёт.
      Asset.loadAsync(ART_REST).catch(() => {});

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
          ВКЛАДКИ НИЖНЕЙ ПАНЕЛИ ПЕРЕКЛЮЧАЮТСЯ БЕЗ АНИМАЦИИ.

          Переход по панели — это два действия подряд: свернуть стопку до главной и открыть
          вкладку (см. BottomNav — иначе чередование вкладок наращивает стопку). Со `slide_from_right`
          оба видны по очереди: экран уезжает, показывается главная, поверх неё наезжает вкладка.
          Со стороны это читается не как переход, а как перерисовка внахлёст.

          Вкладка — не «шаг вглубь», а смена раздела, и ей уместнее жёсткая смена кадра.
          Проваливание вглубь (карточка, план, разговор) анимацию сохраняет: там движение
          вправо-влево говорит человеку, куда он идёт и как вернуться.
        */}
        {/*
          ТРИ КАДРА ВХОДА НЕ ЕДУТ, А ПРОЯВЛЯЮТСЯ.

          Сдвиг вправо-влево говорит «ты пошёл вглубь, назад тем же путём». Здесь это неправда
          трижды, и каждый раз по-своему:

          `intro` — заставка не «уровень выше» экрана пользы, она ему передаёт эстафету и уходит
          из истории (`replace`). Сдвигать её некуда.

          `auth` — переход происходит ПОД чёрным занавесом, который к этому моменту закрыл экран
          целиком. Со сдвигом занавес уезжает влево чёрной плитой, и вместо мягкой передачи видно
          именно её. С проявлением он растворяется в экране входа — движение остаётся одно.

          `auth-done` — это не шаг вглубь, а исход: код погашен, сессия выдана, возвращаться
          некуда. Ему идёт проявление, и оно же даёт ореолу под иллюстрацией разгореться, а не
          въехать сбоку готовым.
        */}
        <Stack.Screen name="intro" options={{ animation: 'fade' }} />
        <Stack.Screen name="auth" options={{ animation: 'fade' }} />
        <Stack.Screen name="auth-done" options={{ animation: 'fade' }} />

        <Stack.Screen name="home" options={{ animation: 'none' }} />
        <Stack.Screen name="activity" options={{ animation: 'none' }} />
        <Stack.Screen name="messages" options={{ animation: 'none' }} />
        <Stack.Screen name="profile/index" options={{ animation: 'none' }} />
      </Stack>
      <PostCallPrompt />
    </SafeAreaProvider>
  );
}
