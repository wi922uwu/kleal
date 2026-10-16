# -*- coding: utf-8 -*-
"""Названия языков → коды ISO. Одна таблица на всё дерево.

Лежала дословно одинаковой в двух сервисах — онбординге и админке, по двадцать три записи и по
шесть строк в каждом. Дословно одинаковой она была на 1 сентября 2026; ровно так же дословно
одинаковыми были и зеркала таксономии, пока одно из них не отстало на двести восемьдесят три слова.
Копия расходится не потому, что кто-то невнимателен, а потому, что править приходится в двух местах,
а помнить об этом — в одном.
"""

#: Ключи — как язык называют в анкете (нижним регистром), значения — код ISO 639-1.
LANG_CODES = {
    "english": "en", "spanish": "es", "german": "de", "french": "fr", "portuguese": "pt",
    "italian": "it", "russian": "ru", "ukrainian": "uk", "polish": "pl", "dutch": "nl",
    "swedish": "sv", "norwegian": "no", "danish": "da", "finnish": "fi", "czech": "cs",
    "greek": "el", "turkish": "tr", "arabic": "ar", "hebrew": "he", "hindi": "hi",
    "chinese": "zh", "japanese": "ja", "korean": "ko",

    # Сербского не было, хотя «sr» лежит в списке валидных кодов админки: код признавали, название —
    # нет. Слово «Serbian» из анкеты превращалось в пустоту, и человек переставал совпадать по языку
    # с теми, с кем совпадал по всему остальному.
    "serbian": "sr", "croatian": "hr", "bosnian": "bs", "bulgarian": "bg", "romanian": "ro",
    "hungarian": "hu", "catalan": "ca", "georgian": "ka", "armenian": "hy", "kazakh": "kk",
    "belarusian": "be", "estonian": "et", "latvian": "lv", "lithuanian": "lt", "slovak": "sk",
    "slovenian": "sl", "thai": "th", "vietnamese": "vi", "indonesian": "id", "persian": "fa",

    # ПРИЛОЖЕНИЕ РУССКОЯЗЫЧНОЕ, А ТАБЛИЦА БЫЛА ТОЛЬКО АНГЛИЙСКОЙ.
    # Человек пишет в анкете «русский», «английский» — и не получал кода вообще. Это тот же провал,
    # что и с сербским, только массовый: он касался каждого, кто заполнял анкету своими словами.
    "русский": "ru", "английский": "en", "испанский": "es", "немецкий": "de",
    "французский": "fr", "португальский": "pt", "итальянский": "it", "украинский": "uk",
    "польский": "pl", "нидерландский": "nl", "голландский": "nl", "шведский": "sv",
    "норвежский": "no", "датский": "da", "финский": "fi", "чешский": "cs", "греческий": "el",
    "турецкий": "tr", "арабский": "ar", "иврит": "he", "хинди": "hi", "китайский": "zh",
    "японский": "ja", "корейский": "ko", "сербский": "sr", "хорватский": "hr",
    "болгарский": "bg", "румынский": "ro", "венгерский": "hu", "грузинский": "ka",
    "армянский": "hy", "казахский": "kk", "белорусский": "be", "литовский": "lt",
    "латышский": "lv", "эстонский": "et", "словацкий": "sk", "словенский": "sl",
    "тайский": "th", "вьетнамский": "vi", "персидский": "fa",

    # «sp» — не код языка, а старая опечатка вместо «es», уже лежащая в живых анкетах. Двухбуквенная
    # проверка её не спасала: в списке валидных кодов «sp» нет, и она молча превращалась в пустоту.
    # Чиним, а не выбрасываем: за ней стоит живой человек, указавший испанский.

    # ИСПАНСКИЙ ИНТЕРФЕЙС — ИСПАНСКИЕ НАЗВАНИЯ. Человек пишет «alemán», «inglés», «ruso» — и без
    # этих строк не получал кода, как русский не получал его с «немецкий». Список тот же, что
    # в приложении (LANG_ES в src/languages.ts), плюс разговорные формы и написания без ударений.
    "afrikáans": "af", "albanés": "sq", "alemán": "de", "amárico": "am", "armenio": "hy",
    "azerí": "az", "bengalí": "bn", "bielorruso": "be", "birmano": "my", "bosnio": "bs",
    "búlgaro": "bg", "catalán": "ca", "checo": "cs", "chino": "zh", "cingalés": "si",
    "coreano": "ko", "croata": "hr", "danés": "da", "eslovaco": "sk", "esloveno": "sl",
    "español": "es", "estonio": "et", "filipino": "tl", "finés": "fi", "francés": "fr",
    "gallego": "gl", "galés": "cy", "georgiano": "ka", "griego": "el", "gujarati": "gu",
    "hausa": "ha", "hebreo": "he", "hindi": "hi", "húngaro": "hu", "indonesio": "id",
    "inglés": "en", "irlandés": "ga", "islandés": "is", "italiano": "it", "japonés": "ja",
    "javanés": "jv", "jemer": "km", "kannada": "kn", "kazajo": "kk", "kirguís": "ky", "kurdo": "ku",
    "lao": "lo", "letón": "lv", "lituano": "lt", "macedonio": "mk", "malayalam": "ml",
    "malayo": "ms", "maltés": "mt", "maratí": "mr", "mongol": "mn", "neerlandés": "nl",
    "nepalí": "ne", "noruego": "no", "pastún": "ps", "persa": "fa", "polaco": "pl",
    "portugués": "pt", "punjabi": "pa", "rumano": "ro", "ruso": "ru", "serbio": "sr",
    "somalí": "so", "suajili": "sw", "sueco": "sv", "tailandés": "th", "tamil": "ta",
    "tayiko": "tg", "telugu": "te", "turco": "tr", "turcomano": "tk", "ucraniano": "uk",
    "urdu": "ur", "uzbeko": "uz", "vasco": "eu", "vietnamita": "vi", "yidis": "yi", "yoruba": "yo",
    "zulú": "zu", "árabe": "ar", "castellano": "es", "euskera": "eu", "holandés": "nl",
    "neerlandes": "nl", "ingles": "en", "aleman": "de", "frances": "fr", "portugues": "pt",
    "arabe": "ar", "japones": "ja", "chino mandarín": "zh", "mandarín": "zh",
    "sp": "es",
}


def code_of(name, default=""):
    """Код языка по его названию. Регистр и лишние пробелы значения не имеют."""
    return LANG_CODES.get(str(name or "").strip().lower(), default)
