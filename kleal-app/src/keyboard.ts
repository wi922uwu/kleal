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

export function useKeyboardInset(): number {
  const [inset, setInset] = useState(0);

  useEffect(() => {
    if (Platform.OS !== 'android') return;

    /*
      СЧИТАЕМ ОТ ВЫСОТЫ КЛАВИАТУРЫ, А НЕ ОТ ПАМЯТИ О ТОМ, «КАК БЫЛО».

      Раньше высота окна без клавиатуры лежала в ref и сравнивалась с текущей. Две дыры, и обе
      стреляли: базу обновлял тот же эффект, что и подписывался, а зависел он от собственного
      результата — значит на каждом открытии клавиатуры слушатели снимались и вешались заново,
      прямо посреди события. И база переживала повороты, разделённый экран и переходы между
      экранами, где уже ничего не значила.

      Здесь ход, которому ни память, ни система координат не нужны: берём высоту клавиатуры и
      вычитаем то, на сколько окно УЖЕ короче экрана. Ужала система сама — разница равна
      клавиатуре, добавка нулевая. Окно во весь экран (edge-to-edge, SDK 54) — разница ноль,
      поднимаем на всю высоту. Оба случая одной формулой. Подписка одна на всю жизнь экрана.
    */
    const show = (e: any) => {
      const kbH = Math.round(Number(e?.endCoordinates?.height || 0));
      const win = Dimensions.get('window').height;
      const scr = Dimensions.get('screen').height;
      const already = Math.max(0, Math.round(scr - win));
      const next = Math.max(0, kbH - already);
      // ЗАМЕР НА ЖИВОМ ТЕЛЕФОНЕ. Дважды починка «по рассуждению» не сработала; третий раз гадать
      // нельзя. Виден только в дев-сборке, в журнале Metro: journalctl -u kleal-expo | grep '[kb]'
      if (__DEV__) {
        console.log('[kb] ' + JSON.stringify({ kbH, win, scr, already, next,
                                               screenY: Math.round(Number(e?.endCoordinates?.screenY || 0)) }));
      }
      setInset(next);
    };
    const s1 = Keyboard.addListener('keyboardDidShow', show);
    const s2 = Keyboard.addListener('keyboardDidHide', () => setInset(0));
    return () => { s1.remove(); s2.remove(); };
  }, []);

  return inset;
}


/**
 * Отступ снизу для панели с полем ввода: пока клавиатуры нет — безопасная зона (жест-бар),
 * когда она открыта — её высота. Складывать их нельзя: клавиатура и так закрывает жест-бар.
 */
export function dockBottom(safeBottom: number, keyboard: number, min = 10): number {
  return keyboard > 0 ? keyboard : Math.max(safeBottom, min);
}
