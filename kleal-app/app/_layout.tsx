import React, { useEffect, useState } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useFonts } from 'expo-font';
import { initLang } from '../src/i18n';
import { restore } from '../src/state';
import { startSummaryWatch } from '../src/profile';
import { color } from '../src/theme';

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
  });

  // Язык и незаконченный онбординг читаются до первого кадра: иначе экран успевает нарисоваться
  // по-английски и тут же перерисоваться по-русски, и это видно.
  useEffect(() => {
    Promise.all([initLang(), restore()]).finally(() => {
      setReady(true);
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
          animation: 'slide_from_right',
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
        <Stack.Screen name="home" options={{ animation: 'none' }} />
        <Stack.Screen name="activity" options={{ animation: 'none' }} />
        <Stack.Screen name="messages" options={{ animation: 'none' }} />
        <Stack.Screen name="profile/index" options={{ animation: 'none' }} />
      </Stack>
    </SafeAreaProvider>
  );
}
