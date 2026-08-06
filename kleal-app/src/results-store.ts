/**
 * Передача выдачи с экрана поиска на экран результатов.
 *
 * Почему не через параметры маршрута, как это делается обычно: ответ матчинга большой. Скомпилированный
 * интент — это одиннадцать блоков §4.3, и к нему шестнадцать карточек, у каждой свой trace, snapshot и
 * allocation_trace. В адресной строке это 64 килобайта, и веб-сборка на них отвечает 431 Request Header
 * Fields Too Large — то есть переход по кнопке работает (он клиентский), а обновление страницы даёт
 * ПУСТОЙ экран. Проверено: /results?payload=<60k> → 431, тот же путь с коротким payload → 200.
 *
 * Модульная переменная, а не хранилище: выдача живёт ровно один переход. Класть её в AsyncStorage
 * значило бы показывать вчерашних людей как сегодняшних — у карточек есть «доступен сейчас», и
 * восстановленная из кэша она врала бы именно в этом.
 */

export type ResultsHandoff = {
  intent: any;
  candidates: any[];
  /** Профиль в том виде, в каком он ушёл в поиск: расширение должно идти с тем же самым. */
  profile: any;
  query?: string;
};

let handoff: ResultsHandoff | null = null;

export function setResults(r: ResultsHandoff) {
  handoff = r;
}

/** null означает «экран открыт напрямую» — например после обновления страницы. */
export function takeResults(): ResultsHandoff | null {
  return handoff;
}

export function clearResults() {
  handoff = null;
}

/**
 * Кандидат, открытый из списка (O.12 → O.13). Тот же принцип, что и с выдачей: карточка большая
 * (trace, snapshot, profile_view), в параметры маршрута её класть нельзя, и живёт она один переход.
 */
let candidate: any | null = null;

export function setCandidate(c: any) {
  candidate = c;
}

/** null — экран открыт напрямую (обновление страницы): показать нечего, честный путь назад. */
export function takeCandidate(): any | null {
  return candidate;
}
