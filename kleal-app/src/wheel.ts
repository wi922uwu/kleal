/**
 * Набор карточек для карусели настроений на главной (борд «GR.01 · Home · Kleal prompt»).
 *
 * ПОЧЕМУ СПИСОК ЖИВЁТ ОТДЕЛЬНО ОТ ЭКРАНА. Правило проекта: содержимое — в `src/*.ts`, экраны
 * только рисуют (см. AGENTS.md). Карусель про то, чем вообще можно заняться, и этот список будет
 * расти и меняться вместе с продуктом — менять его в разметке экрана значит однажды искать
 * кроссовок среди `<View>`.
 *
 * ЭТО ПРЕДМЕТЫ, А НЕ ФОТОГРАФИИ ЛЮДЕЙ. Кроссовок, ракетка, приставка, вишня, ноутбук, зеркальный
 * шар — вырезанные по контуру вещи, каждая означает занятие. Люди на первом экране обещали бы
 * ленту анкет, а Kleal не про это.
 *
 * КАРТИНКИ ПОДГОТОВЛЕНЫ, А НЕ ПОЛОЖЕНЫ КАК ЕСТЬ. У каждой обрезаны прозрачные поля — иначе предмет
 * занимает произвольную часть рамки, и в соседних карточках он стоит кто выше, кто ниже. Длинная
 * сторона приведена к 1050 пикселей — коробка предмета в карточке 244 точки, на трёхкратной
 * плотности это ~730, запас на крупный телефон. С 17.10.2026 — WebP (качество 85, прозрачность 90),
 * а не PNG на 255 цветов: 49 картинок колеса стали 2,5 МБ вместо 5,1, и у новых нет полос
 * палитры (они кодированы из исходных рендеров). Предметы вокруг карточек — до 360 пикселей.
 *
 * ПОДЛОЖКИ У ПРЕДМЕТА БОЛЬШЕ НЕТ. Раньше за колесом перетекали пятна фирменных цветов, у каждого
 * предмета свой набор (`glows`). В новом борде фон главной — одна неподвижная фотография, и
 * менять её вместе с карточкой нечему: карточки стеклянные, и смену видно по тому, что сквозь
 * них просвечивает, а не по цвету экрана.
 */
import type { ImageSourcePropType } from 'react-native';
import { T } from './i18n';

/**
 * Предмет, летающий вокруг карточки (смайлик, наушники, бокал, нота у зеркального шара).
 *
 * КООРДИНАТЫ — В ТОЧКАХ КАРТОЧКИ, а не экрана: начало в её левом верхнем углу, ширина карточки
 * взята эталонной, 299 (как в борде). Карусель сама умножает их на свой масштаб, поэтому на узком
 * телефоне предметы ужимаются вместе с карточкой и не разъезжаются с ней.
 *
 * `w × h` — ровно размер видимого предмета: файлы обрезаны по контуру, рамки вокруг нет.
 */
export type Decor = {
  source: ImageSourcePropType;
  x: number;
  y: number;
  w: number;
  h: number;
  /** Поверх всех карточек. По умолчанию предмет лежит ПОД ними и виден сквозь стекло размытым. */
  front?: boolean;
};

export type MoodItem = {
  key: string;
  /** Предмет в карточке — вырезанный по контуру, без фона. */
  source: ImageSourcePropType;
  /** Заголовок карточки: оклик («Побегаем?»), а не название предмета — см. ниже. */
  label: string;
  /** Что уйдёт в разговор, если по карточке нажать: «Хочу побегать». */
  query: string;
  /** Предметы вокруг карточки. Есть только там, где их нарисовал борд. */
  decor?: Decor[];
};

/**
 * ПОДПИСЬ — ЭТО ПРЕДЛОЖЕНИЕ, А НЕ НАЗВАНИЕ ПРЕДМЕТА. Под кроссовком стоит «Побегаем?», а не
 * «Кроссовки»: карусель отвечает на вопрос «чем заняться», который тут же задан в строке ввода, и
 * подпись должна звучать как чужая реплика, на которую хочется ответить. Название предмета
 * превратило бы карусель в витрину.
 *
 * ЗАПРОС — НЕ ТА ЖЕ СТРОКА, ЧТО ПОДПИСЬ. Подпись это оклик («Побегаем?»), а в разговор уходит
 * ответ на него от первого лица («Хочу побегать»). Отправить в чат вопрос значило бы начать
 * разговор с того, что человек спрашивает у агента ровно то, о чём агент спросил его.
 *
 * ФУНКЦИЯ, А НЕ КОНСТАНТА: строки двуязычные, и `T()` обязан вызываться на каждой отрисовке —
 * иначе смена языка не доходит до уже собранного списка.
 */
/*
  ПРЕДМЕТЫ ВОКРУГ КАЖДОЙ КАРТОЧКИ (17.10.2026, владелец: «придумай фоновых картинок к каждой
  карточке, как у диско шара»). Сгенерированы Codex в той же манере, что и сами карточки, по три на
  карточку: два позади (видны сквозь стекло размытыми — над верхним краем и у боковой кромки) и один
  резкий спереди у противоположной кромки. Раскладка чередуется зеркально от карточки к карточке,
  чтобы колесо не повторялось одним рисунком. Файлы — assets/art/wheel/decor, ≤ 360 px, 255 цветов.
*/
export const WHEEL = (): MoodItem[] => [
  /*
    ЗАГОЛОВОК ИЗ БОРДА, а не оклик по образцу соседей: «Set Fire to the Night» стоит на кадре GR.01
    дословно. Запрос прежний — в разговор по-прежнему уходит «хочу пойти танцевать».
    Предметы вокруг сняты с того же кадра (слои image 16/17/18/20): три лежат под карточками и
    видны сквозь стекло размытыми, нота — поверх всего, она одна резкая.
    Первым в списке — потому что на кадре карусель открывается именно этой карточкой.
  */
  { key: 'disco', label: T('Зажжём эту ночь', 'Set Fire to the Night', 'Enciende la noche'),
    query: T('Хочу пойти танцевать', 'I want to go dancing', 'Quiero ir a bailar'),
    source: require('../assets/art/wheel/disco.webp'),
    decor: [
      { source: require('../assets/art/home/decor-smiley.webp'), x: 19, y: 10, w: 57, h: 59 },
      { source: require('../assets/art/home/decor-headphones.webp'), x: -54, y: 161, w: 101, h: 104 },
      { source: require('../assets/art/home/decor-martini.webp'), x: 179, y: -65, w: 81, h: 105 },
      { source: require('../assets/art/home/decor-note.webp'), x: 256, y: 150, w: 70, h: 100, front: true },
    ] },
  { key: 'sneaker', label: T('Побегаем?', 'Go for a run?', '¿Vamos a correr?'),
    query: T('Хочу побегать', 'I want to go for a run', 'Quiero salir a correr'),
    source: require('../assets/art/wheel/sneaker.webp'),
    decor: [
      { source: require('../assets/art/wheel/decor/sneaker-bottle.webp'), x: 28, y: -56, w: 48, h: 84 },
      { source: require('../assets/art/wheel/decor/sneaker-earbuds.webp'), x: -50, y: 156, w: 87, h: 98 },
      { source: require('../assets/art/wheel/decor/sneaker-stopwatch.webp'), x: 252, y: 140, w: 59, h: 76, front: true },
    ], },
  { key: 'padel', label: T('Партию в падел?', 'A game of padel?', '¿Una partida de pádel?'),
    query: T('Хочу сыграть в падел', 'I want to play padel', 'Quiero jugar a pádel'),
    source: require('../assets/art/wheel/padel.webp'),
    decor: [
      { source: require('../assets/art/wheel/decor/padel-sweatband.webp'), x: 206, y: -56, w: 82, h: 84 },
      { source: require('../assets/art/wheel/decor/padel-bottle.webp'), x: 278, y: 156, w: 54, h: 98 },
      { source: require('../assets/art/wheel/decor/padel-ball.webp'), x: -21, y: 140, w: 76, h: 76, front: true },
    ], },
  { key: 'gamepad', label: T('Поиграем?', 'Play something?', '¿Jugar algo?'),
    query: T('Хочу поиграть в приставку', 'I want to play console games', 'Quiero jugar a videojuegos'),
    source: require('../assets/art/wheel/gamepad.webp'),
    decor: [
      { source: require('../assets/art/wheel/decor/gamepad-cartridge.webp'), x: 10, y: -52, w: 84, h: 77 },
      { source: require('../assets/art/wheel/decor/gamepad-headset.webp'), x: -53, y: 156, w: 94, h: 98 },
      { source: require('../assets/art/wheel/decor/gamepad-heart.webp'), x: 244, y: 142, w: 76, h: 72, front: true },
    ], },
  { key: 'cherries', label: T('Поедим фруктов?', 'Grab some fruit?', '¿Quieres coger algo de fruta?'),
    query: T('Хочу сходить на рынок за фруктами', 'I want to hit the market for fruit', 'Quiero ir al mercado a por fruta'),
    source: require('../assets/art/wheel/cherries.webp'),
    decor: [
      { source: require('../assets/art/wheel/decor/cherries-fig.webp'), x: 205, y: -49, w: 84, h: 70 },
      { source: require('../assets/art/wheel/decor/cherries-strawberry.webp'), x: 262, y: 156, w: 85, h: 98 },
      { source: require('../assets/art/wheel/decor/cherries-cherry.webp'), x: -10, y: 140, w: 53, h: 76, front: true },
    ], },
  { key: 'laptop', label: T('Поработаем рядом?', 'Work side by side?', '¿Trabajar juntos?'),
    query: T('Хочу поработать в кофейне за компанию', 'I want to work from a cafe with someone', 'Quiero trabajar desde una cafetería con alguien'),
    source: require('../assets/art/wheel/laptop.webp'),
    decor: [
      { source: require('../assets/art/wheel/decor/laptop-notes.webp'), x: 10, y: -52, w: 84, h: 75 },
      { source: require('../assets/art/wheel/decor/laptop-coffee.webp'), x: -42, y: 156, w: 72, h: 98 },
      { source: require('../assets/art/wheel/decor/laptop-pen.webp'), x: 251, y: 140, w: 62, h: 76, front: true },
    ], },
  /*
    ТРЕНДОВЫЕ ПРЕДМЕТЫ (17.10.2026, владелец): сгенерированы той же школой рендера, что и шесть
    выше (промпты — prompts-wheel.md в папке Ивана). Подготовлены так же: поля обрезаны, длинная
    сторона ≤ 1300, палитра на 255. Порядок колеса на главной перемешивается при каждом заходе
    (см. app/home.tsx), поэтому их место в списке ничего не значит.
  */
  { key: 'matcha', label: T('По матче?', 'Matcha date?', '¿Un matcha?'),
    query: T('Хочу выпить матчу в кафе с кем-нибудь', 'I want to grab a matcha with someone', 'Quiero tomar un matcha con alguien'),
    source: require('../assets/art/wheel/matcha.webp'),
    decor: [
      { source: require('../assets/art/wheel/decor/matcha-whisk.webp'), x: 216, y: -56, w: 61, h: 84 },
      { source: require('../assets/art/wheel/decor/matcha-macaron.webp'), x: 256, y: 162, w: 98, h: 85 },
      { source: require('../assets/art/wheel/decor/matcha-ice.webp'), x: -20, y: 140, w: 74, h: 76, front: true },
    ], },
  { key: 'camera', label: T('Пофоткаем на мыльницу?', 'Point-and-shoot walk?', '¿Salimos a hacer fotos?'),
    query: T('Хочу погулять и пофоткать на камеру', 'I want to go on a photo walk', 'Quiero dar un paseo haciendo fotos'),
    source: require('../assets/art/wheel/camera.webp'),
    decor: [
      { source: require('../assets/art/wheel/decor/camera-film.webp'), x: 20, y: -56, w: 65, h: 84 },
      { source: require('../assets/art/wheel/decor/camera-flashbulb.webp'), x: -42, y: 156, w: 71, h: 98 },
      { source: require('../assets/art/wheel/decor/camera-photo.webp'), x: 250, y: 140, w: 64, h: 76, front: true },
    ], },
  { key: 'bracelets', label: T('На концерт?', 'Catch a concert?', '¿Vamos a un concierto?'),
    query: T('Хочу сходить на концерт', 'I want to go to a concert', 'Quiero ir a un concierto'),
    source: require('../assets/art/wheel/bracelets.webp'),
    decor: [
      { source: require('../assets/art/wheel/decor/bracelets-ticket.webp'), x: 205, y: -46, w: 84, h: 65 },
      { source: require('../assets/art/wheel/decor/bracelets-glowstick.webp'), x: 256, y: 166, w: 98, h: 78 },
      { source: require('../assets/art/wheel/decor/bracelets-pick.webp'), x: -16, y: 140, w: 66, h: 76, front: true },
    ], },
  { key: 'sunglasses', label: T('Фармим ауру?', 'Farming aura?', '¿Farmeamos aura?'),
    query: T('Хочу погулять по городу', 'I want to walk around the city', 'Quiero pasear por la ciudad'),
    source: require('../assets/art/wheel/sunglasses.webp'),
    decor: [
      { source: require('../assets/art/wheel/decor/sunglasses-bubble.webp'), x: 10, y: -56, w: 84, h: 83 },
      { source: require('../assets/art/wheel/decor/sunglasses-hoop.webp'), x: -48, y: 156, w: 83, h: 98 },
      { source: require('../assets/art/wheel/decor/sunglasses-star.webp'), x: 244, y: 141, w: 76, h: 74, front: true },
    ], },
  { key: 'keychain', label: T('Обменяемся фигурками?', 'Swap figures?', '¿Intercambiamos figuras?'),
    query: T('Хочу обменяться коллекционными фигурками', 'I want to trade collectible figures', 'Quiero intercambiar figuras coleccionables'),
    source: require('../assets/art/wheel/keychain.webp'),
    decor: [
      { source: require('../assets/art/wheel/decor/keychain-box.webp'), x: 206, y: -56, w: 81, h: 84 },
      { source: require('../assets/art/wheel/decor/keychain-heart.webp'), x: 256, y: 160, w: 98, h: 90 },
      { source: require('../assets/art/wheel/decor/keychain-charm.webp'), x: -16, y: 140, w: 67, h: 76, front: true },
    ], },
  { key: 'balloons67', label: T('Сегодня в 6–7?', 'Tonight at 6–7?', '¿Hoy a las 6–7?'),
    query: T('Хочу встретиться с кем-нибудь сегодня вечером', 'I want to meet up with someone tonight', 'Quiero quedar con alguien esta tarde'),
    source: require('../assets/art/wheel/balloons67.webp'),
    decor: [
      { source: require('../assets/art/wheel/decor/balloons67-popper.webp'), x: 11, y: -56, w: 82, h: 84 },
      { source: require('../assets/art/wheel/decor/balloons67-coupe.webp'), x: -44, y: 156, w: 77, h: 98 },
      { source: require('../assets/art/wheel/decor/balloons67-confetti.webp'), x: 246, y: 140, w: 71, h: 76, front: true },
    ], },
];

/**
 * КОЛЕСО В СЛУЧАЙНОМ ПОРЯДКЕ (владелец 17.10.2026: «чтобы они при каждом заходе выпадали
 * рандомно»). Порядок — список ключей, а не сами карточки: карточки собираются на каждой
 * отрисовке (язык), а порядок живёт, пока человек на главной, и меняется при следующем заходе.
 */
export function shuffledWheelKeys(): string[] {
  const keys = WHEEL().map((it) => it.key);
  for (let i = keys.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [keys[i], keys[j]] = [keys[j], keys[i]];
  }
  return keys;
}

/** Колесо в заданном порядке. Ключи, которых нет в порядке (новые карточки), — в конец. */
export function wheelInOrder(order: string[]): MoodItem[] {
  const all = WHEEL();
  const rank = new Map(order.map((k, i) => [k, i]));
  return [...all].sort((a, b) => (rank.get(a.key) ?? 999) - (rank.get(b.key) ?? 999));
}
