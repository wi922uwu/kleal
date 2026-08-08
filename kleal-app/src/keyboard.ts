/**
 * Сколько места снизу занимает клавиатура ПРЯМО СЕЙЧАС — и надо ли поднимать на это поле ввода.
 *
 * Зачем это вообще. Во всех экранах с полем внизу стоит
 *
 *     <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
 *
 * — то есть на Android компонент не делает НИЧЕГО и вся надежда на то, что окно само ужмётся под
 * клавиатуру (`windowSoftInputMode=adjustResize`). Так было годами, и в SDK 54 это перестало
 * работать: на Android приложение теперь рисуется edge-to-edge, а окно, которое рисует под
 * системными панелями, под клавиатуру НЕ ужимается — клавиатура просто ложится поверх композера.
 *
 * Настоящее решение — react-native-keyboard-controller, но это нативный модуль, а с ним кончается
 * Expo Go (см. AGENTS.md). Поэтому поднимаем сами, из JS, и это работает и в Expo Go.
 *
 * ПОЧЕМУ НЕ ПРОСТО «добавить высоту клавиатуры». Там, где окно всё-таки ужимается (старые версии,
 * сборка без edge-to-edge, планшеты), композер уже поднят системой, и добавка подняла бы его
 * ВТОРОЙ раз — поле улетело бы на середину экрана. Поэтому хук сравнивает высоту окна с той, что
 * была до клавиатуры: ужалось — возвращаем 0 и не вмешиваемся, не ужалось — возвращаем высоту
 * клавиатуры. Само себя выключает там, где не нужно.
 *
 * На iOS всегда 0: там `behavior="padding"` работает и добавка тоже была бы двойной.
 */
import { useEffect, useRef, useState } from 'react';
import { Dimensions, Keyboard, Platform } from 'react-native';

/** Меньше этого сжатие окна — не сжатие, а дрожание строки статуса. */
const RESIZED_BY = 60;

export function useKeyboardInset(): number {
  const [inset, setInset] = useState(0);
  /** Высота окна БЕЗ клавиатуры. Обновляется, пока клавиатуры нет. */
  const bare = useRef(Dimensions.get('window').height);

  useEffect(() => {
    if (Platform.OS !== 'android') return;

    const dim = Dimensions.addEventListener('change', ({ window }) => {
      // Пока клавиатуры нет, любое изменение окна (поворот, разделённый экран) — новая база.
      if (!inset) bare.current = window.height;
    });
    const show = Keyboard.addListener('keyboardDidShow', (e) => {
      const now = Dimensions.get('window').height;
      const resized = now < bare.current - RESIZED_BY;
      setInset(resized ? 0 : Math.round(e.endCoordinates?.height || 0));
    });
    const hide = Keyboard.addListener('keyboardDidHide', () => {
      bare.current = Dimensions.get('window').height;
      setInset(0);
    });
    return () => { dim.remove(); show.remove(); hide.remove(); };
  }, [inset]);

  return inset;
}

/**
 * Отступ снизу для панели с полем ввода: пока клавиатуры нет — безопасная зона (жест-бар),
 * когда она открыта — её высота. Складывать их нельзя: клавиатура и так закрывает жест-бар.
 */
export function dockBottom(safeBottom: number, keyboard: number, min = 10): number {
  return keyboard > 0 ? keyboard : Math.max(safeBottom, min);
}
