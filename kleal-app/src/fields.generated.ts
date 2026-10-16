/**
 * СГЕНЕРИРОВАННЫЙ ФАЙЛ. Не править руками.
 *
 * Источник: kleal-ms/shared/fields.json
 * Обновить: python3 tools/sync_fields.py
 *
 * Реестр полей профиля — единственное место, где написано, как называется та или иная вещь про
 * человека в приложении и в строке пользователя на сервере. Пользоваться им нужно через src/fields.ts,
 * а не читать отсюда напрямую.
 */

export type FieldFact = {
  meaning: string;
  /** Путь в профиле приложения. null — приложение этот факт не хранит. */
  app: string | null;
  /** Ключ в строке users.json. null — на сервере такого поля нет. */
  row: string | null;
  patchable: boolean;
  quirks: string[];
};

export const FIELDS_VERSION = 1;

export const FIELDS: Record<string, FieldFact> = {
  "name": {
    "meaning": "Имя. Оно же ключ строки в users.json — другого идентификатора у хранилища нет.",
    "app": "name",
    "row": "name",
    "patchable": false,
    "quirks": [
      "Пустое имя превращается в «New user» при записи строки."
    ]
  },
  "age": {
    "meaning": "Возраст. Жёсткий гейт матчинга: младше 18 не ранжируется вовсе.",
    "app": "age",
    "row": "age",
    "patchable": true,
    "quirks": [
      "Если возраст не задан, в строку пишется 28 — то есть выдуманное число."
    ]
  },
  "gender": {
    "meaning": "Пол. Значение из SEXES: Male | Female | Any.",
    "app": "gender",
    "row": "gender",
    "patchable": true,
    "quirks": [
      "«Any» означает «не важно», а не «другое». Показывать его как пол человека нельзя."
    ]
  },
  "location.area": {
    "meaning": "Район или город, который человек считает своим. Показывается людям.",
    "app": "city",
    "row": "area",
    "patchable": true,
    "quirks": [
      "В строку берётся city, а если его нет — первый из geo.comfortableAreas.",
      "Матчинг сравнивает районы строками: «Gràcia» и «Gracia» для него разные места."
    ]
  },
  "location.country": {
    "meaning": "Страна, где человек живёт. Вместе с городом отвечает на «где искать»; в листе локации ею выбирается список городов.",
    "app": "country",
    "row": "country",
    "patchable": true,
    "quirks": [
      "Ключ английский («Spain»), подпись человеку даёт countryLabel — не показывать ключ.",
      "Страны нет в реестре с самого начала: экран профиля её ПОКАЗЫВАЛ и давал менять, а сохранить не мог — writeFact такого факта не знал, и выбор пропадал молча."
    ]
  },
  "location.lat": {
    "meaning": "Широта, огрублённая до ~1 км. Точную точку человека не хранит никто.",
    "app": "geo.coarseLat",
    "row": "lat",
    "patchable": true,
    "quirks": [
      "Без lat/lon радиус не работает: _with_km не считает расстояние и гейт не срабатывает."
    ]
  },
  "location.lon": {
    "meaning": "Долгота, огрублённая до ~1 км.",
    "app": "geo.coarseLon",
    "row": "lon",
    "patchable": true,
    "quirks": [
      "lat=0 и lon=0 сервер считает отсутствием координат, а не точкой в Атлантике."
    ]
  },
  "location.radiusKm": {
    "meaning": "Как далеко человек готов ехать. Жёсткий фильтр поиска, а не пожелание.",
    "app": "geo.maxDistanceKm",
    "row": "radiusKm",
    "patchable": true,
    "quirks": []
  },
  "languages": {
    "meaning": "Языки, на которых человеку комфортно. Жёсткий гейт: без общего языка встречи не будет.",
    "app": "languages.comfortable",
    "row": "langs",
    "patchable": true,
    "quirks": [
      "В строку попадают только ПЕРВЫЕ ЧЕТЫРЕ языка — остальные молча теряются.",
      "Пустой список превращается в ['en']: человек без языков становится англоговорящим.",
      "Код нельзя получать обрезкой названия: Spanish даёт «sp» (нет такого), Estonian — «es» (испанский)."
    ]
  },
  "interests": {
    "meaning": "Чем человек любит заниматься с людьми. Основа ранжирования.",
    "app": "interests.explicit",
    "row": "interests",
    "patchable": true,
    "quirks": [
      "В строку попадают только ПЕРВЫЕ ШЕСТЬ интересов — остальные молча теряются.",
      "Пустой список превращается в ['social'].",
      "Приводятся к нижнему регистру. Написанное по-русски так и остаётся русским: «скалодром» совпадёт только со «скалодромом», но не с climbing."
    ]
  },
  "interests.unused": {
    "meaning": "Интересы, которые человек выключил из подбора, не удаляя из профиля.",
    "app": "interests.unused",
    "row": null,
    "patchable": false,
    "quirks": [
      "Живёт только на устройстве. Сервер о таком выключении не знает и учитывает интерес."
    ]
  },
  "summary": {
    "meaning": "Что Kleal рассказывает о человеке своими словами.",
    "app": "summary",
    "row": "summary",
    "patchable": true,
    "quirks": [
      "Проговаривает факты вслух, поэтому обязана пересобираться после правки локации, языков, основного и интересов.",
      "Обрезается до PROSE_MAX (900 символов) при записи."
    ]
  },
  "personality": {
    "meaning": "Текст, который пишет тест личности. Отдельное поле от сводки.",
    "app": "personality",
    "row": "personality",
    "patchable": true,
    "quirks": [
      "Слипание с summary уже однажды съедало сводку. Это два поля с двумя владельцами."
    ]
  },
  "persona": {
    "meaning": "Ответы теста личности по осям. Закрытый словарь значений.",
    "app": "persona",
    "row": "persona",
    "patchable": true,
    "quirks": [
      "Незнакомое значение оси ОТБРАСЫВАЕТСЯ, а не заменяется умолчанием."
    ]
  },
  "story": {
    "meaning": "История жизни своими словами.",
    "app": "story",
    "row": "story",
    "patchable": true,
    "quirks": [
      "Обрезается до 4000 символов."
    ]
  },
  "photo": {
    "meaning": "Фото профиля.",
    "app": "photo",
    "row": "photo",
    "patchable": false,
    "quirks": [
      "В приложении это data-URL, в строке — ссылка на файл на сервере.",
      "НЕ уходит в attach: там это лишние сотни килобайт в файле с паролями."
    ]
  },
  "safety.publicPlacesOnly": {
    "meaning": "Встречаться только в публичных местах.",
    "app": "safety.publicPlacesOnly",
    "row": "safety.publicPlacesOnly",
    "patchable": true,
    "quirks": [
      "Все читатели проверяют его как «!== false»: не заданное значит включено."
    ]
  },
  "safety.verifiedOnly": {
    "meaning": "Предпочитать подтверждённых людей.",
    "app": "safety.verifiedOnly",
    "row": "safety.verifiedOnly",
    "patchable": true,
    "quirks": []
  },
  "safety.hideExactLocation": {
    "meaning": "Не показывать точное место, только район.",
    "app": "safety.hideExactLocation",
    "row": "safety.hideExactLocation",
    "patchable": true,
    "quirks": []
  },
  "permissions.useProfileForMatching": {
    "meaning": "Разрешение использовать профиль для подбора.",
    "app": "permissions.useProfileForMatching",
    "row": null,
    "patchable": false,
    "quirks": [
      "На сервере отдельного поля нет: согласие подразумевается фактом регистрации."
    ]
  },
  "permissions.allowAdjacentMatches": {
    "meaning": "Разрешение предлагать смежные интересы, а не только точные совпадения.",
    "app": "permissions.allowAdjacentMatches",
    "row": null,
    "patchable": false,
    "quirks": [
      "Читается как «!== false». В интенте это отдельный ключ adjacentAllowed."
    ]
  },
  "vibe": {
    "meaning": "Как человек воспринимается. Единственное, что из теста личности влияет на подбор.",
    "app": "vibe",
    "row": "vibe",
    "patchable": true,
    "quirks": []
  },
  "open": {
    "meaning": "Готов ли человек к встречам прямо сейчас (статус приёма).",
    "app": null,
    "row": "open",
    "patchable": false,
    "quirks": [
      "Меняется через /api/onboarding/receiving, а не патчем профиля. Состояние паузы разложено по трём полям строки — это известное расхождение."
    ]
  },
  "km": {
    "meaning": "Расстояние до искателя. Считается на лету, в профиле не хранится.",
    "app": null,
    "row": "km",
    "patchable": false,
    "quirks": [
      "В строке это поле есть у синтетического пула и означает расстояние до фиксированной точки.",
      "Для настоящих людей его проставляет _with_km на каждый запрос. Хранить его в профиле нельзя: расстояние зависит от того, КТО спрашивает."
    ]
  }
};
