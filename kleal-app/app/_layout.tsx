import React, { useEffect, useState } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { initLang } from '../src/i18n';
import { restore } from '../src/state';
import { startSummaryWatch } from '../src/profile';
import { color } from '../src/theme';

export default function RootLayout() {
  const [ready, setReady] = useState(false);

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

  if (!ready) {
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
      />
    </SafeAreaProvider>
  );
}
