"""Доступ к полям профиля по реестру shared/fields.json.

Смысл в том, чтобы имя поля было написано ОДИН раз — в реестре, — а код обращался к факту, а не к
строке. До этого модуля одна и та же локация читалась по четырём разным именам в четырёх местах, и
узнать об этом можно было только наткнувшись.

Как пользоваться:

    from fields import row_get, row_set, app_get, patch_from_app

    area = row_get(user_row, "location.area")          # вместо user_row.get("area")
    row_set(user_row, "location.radiusKm", 15)         # вместо user_row["radiusKm"] = 15
    patch = patch_from_app(app_profile, ["location.area", "location.lat", "location.lon"])

Модуль намеренно не тащит зависимостей и не кеширует агрессивно: сервисы здесь однофайловые, и
лишняя магия в общем модуле обошлась бы дороже, чем разбор небольшого JSON один раз за процесс.
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.join(_HERE, "fields.json")

with open(_PATH, "r", encoding="utf-8") as _f:
    REGISTRY = json.load(_f)

FACTS = REGISTRY["facts"]


class UnknownFact(KeyError):
    """Факта нет в реестре.

    Это не мелочь, которую можно проглотить: опечатка в имени факта иначе тихо вернула бы None, и
    поле «просто не сохранилось» — ровно тот класс расхождений, ради которого реестр и заведён.
    """


def _fact(name):
    try:
        return FACTS[name]
    except KeyError:
        raise UnknownFact(
            "поля «%s» нет в shared/fields.json. Сначала опишите его там, потом используйте." % name
        )


def _dig(d, path):
    """Достать по точечному пути. Отсутствующая середина — это None, а не исключение."""
    cur = d or {}
    for part in str(path).split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _put(d, path, value):
    cur = d
    parts = str(path).split(".")
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value
    return d


def row_key(name):
    """Имя факта в строке users.json. None — факта в строке нет вовсе."""
    return _fact(name).get("row")


def app_key(name):
    """Имя факта в профиле приложения. None — приложение его не хранит."""
    return _fact(name).get("app")


def row_get(row, name, default=None):
    key = row_key(name)
    if not key:
        return default
    v = _dig(row, key)
    return default if v is None else v


def row_set(row, name, value):
    key = row_key(name)
    if not key:
        raise UnknownFact("факт «%s» не хранится в строке пользователя" % name)
    return _put(row if isinstance(row, dict) else {}, key, value)


def app_get(profile, name, default=None):
    key = app_key(name)
    if not key:
        return default
    v = _dig(profile, key)
    return default if v is None else v


def patchable(name):
    return bool(_fact(name).get("patchable"))


def patch_from_app(profile, facts):
    """Собрать патч для /api/onboarding/profile-update из профиля приложения.

    Берутся только факты, которые сервер действительно принимает: непатчируемое сюда попасть не
    должно даже по недосмотру — сервер его молча выбросит, и правка «применится» только на экране.
    """
    out = {}
    for name in facts:
        if not patchable(name):
            raise UnknownFact("факт «%s» не патчится через profile-update" % name)
        key = row_key(name)
        v = app_get(profile, name)
        if key and v is not None:
            out[key] = v
    return out


def quirks(name):
    """Известные особенности поля — то, что оно делает с данными молча."""
    return list(_fact(name).get("quirks") or [])


def all_row_keys():
    """Все ключи строки, которые реестр знает по имени. Для сверки со схемой хранилища."""
    keys = set()
    for f in FACTS.values():
        r = f.get("row")
        if r:
            keys.add(str(r).split(".")[0])
    keys.update(REGISTRY.get("row_only_keys") or [])
    return sorted(keys)
