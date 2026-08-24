/**
 * Тактильный словарь приложения.
 *
 * ЗАЧЕМ ОБЩИЙ ФАЙЛ, А НЕ ВЫЗОВЫ ПО МЕСТУ. Отклик — это язык, а не украшение: если «нажал» и
 * «получилось» ощущаются одинаково, палец перестаёт их различать и отклик превращается в фоновое
 * жужжание. Поэтому сила выбирается ЗДЕСЬ и один раз, а экраны называют событие, а не силу.
 *
 * Ступени намеренно редкие — их ровно столько, сколько человек различает вслепую:
 *   нажал        — лёгкий: обычная кнопка, «назад», выбор;
 *   сделал       — средний: главное действие экрана, после которого что-то происходит;
 *   щелчок       — самый мелкий: цифра встала в ячейку, шаг колеса;
 *   получилось   — системный успех: код принят;
 *   не вышло     — системная ошибка: код неверен, адрес кривой.
 *
 * ГОЛОСОВЫЕ ЭКРАНЫ ЖИВУТ СО СВОИМИ КОПИЯМИ (`src/voice.tsx`, `src/videonote.tsx`) — там свой
 * словарь для длинного нажатия. Переносить их сюда без владельца нельзя (см. зоны в AGENTS.md),
 * но ступени подобраны так, чтобы совпасть: лёгкий на начало, средний на замок.
 *
 * ВЕБ МОЛЧИТ. `expo-haptics` там ничего не умеет, и вызов уходит в отказ промиса — поэтому у
 * каждого вызова пустой `catch`: отсутствие вибромотора не повод ронять экран.
 */
import { Platform } from 'react-native';
import * as Haptics from 'expo-haptics';

const canBuzz = Platform.OS !== 'web';

const impact = (style: Haptics.ImpactFeedbackStyle) => {
  if (canBuzz) Haptics.impactAsync(style).catch(() => {});
};

/** Обычное нажатие: кнопка, «назад», выбор. */
export const hTap = () => impact(Haptics.ImpactFeedbackStyle.Light);
/** Главное действие экрана — весомее обычного нажатия. */
export const hCommit = () => impact(Haptics.ImpactFeedbackStyle.Medium);
/** Самый мелкий щелчок: цифра встала в ячейку. */
export const hTick = () => {
  if (canBuzz) Haptics.selectionAsync().catch(() => {});
};
/** Получилось. */
export const hOk = () => {
  if (canBuzz) Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
};
/** Не вышло. */
export const hFail = () => {
  if (canBuzz) Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
};

/**
 * ДЛИННЫЙ ОТКЛИК НА ПРОТЯЖКЕ.
 *
 * Непрерывной вибрации в `expo-haptics` нет вовсе — там только одиночные удары. Но длинный отклик
 * и не обязан быть одним событием: палец читает как «тянется» частую дробь, у которой меняется
 * плотность. Поэтому здесь ЗАСЕЧКИ ЧЕРЕЗ РАВНОЕ РАССТОЯНИЕ: чем быстрее ведёшь, тем чаще стучит,
 * и рука чувствует не «щелчок», а сопротивление материала — как у молнии или колеса барабана.
 *
 * СИЛА РАСТЁТ К ПОРОГУ. До точки невозврата засечки мягкие, после — обычные лёгкие; сам переход
 * через порог отмечен одним средним ударом. Получается нарастание, которое и читается как один
 * длинный отклик с концом, а не как россыпь одинаковых щелчков.
 *
 * ОГРАНИЧЕНИЕ ПО ВРЕМЕНИ ОБЯЗАТЕЛЬНО. На резком рывке пальца между двумя кадрами набегает сразу
 * сотня точек; без нижней границы интервала туда ушёл бы десяток ударов за один кадр, и мотор
 * слил бы их в кашу вместо дроби.
 */
const NOTCH = 12;     // точек хода на одну засечку
const GAP_MS = 24;    // ближе этого удары сливаются в кашу

export function makePull() {
  let lastNotch = 0;
  let lastAt = 0;
  let crossed = false;
  return {
    /** Вызывать на каждом движении: `travel` — сколько протянуто от покоя, `ready` — порог пройден. */
    move(travel: number, ready: boolean) {
      const now = Date.now();
      if (ready && !crossed) {
        crossed = true;
        lastNotch = travel;
        lastAt = now;
        impact(Haptics.ImpactFeedbackStyle.Medium);   // точка невозврата — один заметный удар
        return;
      }
      if (Math.abs(travel - lastNotch) < NOTCH || now - lastAt < GAP_MS) return;
      lastNotch = travel;
      lastAt = now;
      impact(ready ? Haptics.ImpactFeedbackStyle.Light : Haptics.ImpactFeedbackStyle.Soft);
    },
    /** Палец лёг на панель. */
    grab() {
      lastNotch = 0;
      lastAt = Date.now();
      crossed = false;
      impact(Haptics.ImpactFeedbackStyle.Soft);
    },
    /** Отпустили: `done` — ушло дальше, иначе вернулось на место. */
    release(done: boolean) {
      crossed = false;
      impact(done ? Haptics.ImpactFeedbackStyle.Heavy : Haptics.ImpactFeedbackStyle.Soft);
    },
  };
}
