# -*- coding: utf-8 -*-
"""§14.2 Технические гарантии — optimistic concurrency, idempotency, uniqueness, capacity CAS.

Гарантии: version-CAS; idempotency key на write (C#7); уникальные active pair/purpose (две волны не
создают дубль пары); compare-and-swap при concurrent accepts (C#8: два accept последнего слота не
превышают capacity). Всё под общим RLock (in-memory прототип; на проде — БД-транзакция + constraint).
"""
import threading

_LOCK = threading.RLock()


class VersionConflict(Exception):
    pass


class VersionedStore:
    """Хранилище с optimistic concurrency: обновление проходит только при совпадении version."""
    def __init__(self):
        self._d = {}

    def put(self, key, obj):
        with _LOCK:
            o = dict(obj)
            o.setdefault("version", 1)
            self._d[key] = o
            return o

    def get(self, key):
        with _LOCK:
            o = self._d.get(key)
            return dict(o) if o else None

    def items(self):
        with _LOCK:
            return [(k, dict(v)) for k, v in self._d.items()]

    def compare_and_swap(self, key, expected_version, updates):
        """CAS: применить updates только если текущая version == expected; иначе VersionConflict."""
        with _LOCK:
            cur = self._d.get(key)
            if cur is None:
                raise KeyError(key)
            if cur.get("version") != expected_version:
                raise VersionConflict("%s: expected v%s, have v%s" % (key, expected_version, cur.get("version")))
            cur = dict(cur)
            cur.update(updates)
            cur["version"] = expected_version + 1
            self._d[key] = cur
            return dict(cur)


class IdempotencyStore:
    """C#7: повторный write с тем же idem key возвращает ТОТ ЖЕ результат, не выполняя операцию снова."""
    def __init__(self):
        self._d = {}

    def assert_or_return(self, key):
        """Возвращает (hit, result). hit=True -> операция уже выполнена, вернуть result без побочных эффектов."""
        with _LOCK:
            if key in self._d:
                return True, self._d[key]
            return False, None

    def store_result(self, key, result):
        with _LOCK:
            self._d[key] = result
            return result


class UniquePairRegistry:
    """Уникальность active (pair, purpose): две волны не создают duplicate pair (§14.4)."""
    def __init__(self):
        self._active = set()

    def _k(self, a, b, purpose):
        return (tuple(sorted((str(a).lower(), str(b).lower()))), purpose)

    def claim(self, a, b, purpose):
        with _LOCK:
            k = self._k(a, b, purpose)
            if k in self._active:
                return False
            self._active.add(k)
            return True

    def release(self, a, b, purpose):
        with _LOCK:
            self._active.discard(self._k(a, b, purpose))


class CapacityLedger:
    """C#8 + §14.2 reservation-TTL: атомарный claim слота; истёкшие reservations авто-освобождаются.
    Параллельные accept последнего слота не превышают capacity."""
    def __init__(self):
        self._slots = {}                                # resource -> [expiry_ts | None, ...]

    def _sweep(self, resource, now):
        live = [e for e in self._slots.get(resource, []) if e is None or now is None or e > now]
        self._slots[resource] = live
        return live

    def claim_slot(self, resource, max_capacity, *, now=None, ttl_sec=None):
        """Атомарно занять слот (опц. с TTL). Возвращает (ok, current). ok=False, если capacity исчерпана
        (после авто-освобождения истёкших)."""
        with _LOCK:
            live = self._sweep(resource, now)
            if len(live) >= int(max_capacity):
                return False, len(live)
            exp = (float(now) + float(ttl_sec)) if (now is not None and ttl_sec) else None
            live.append(exp)
            self._slots[resource] = live
            return True, len(live)

    def release_slot(self, resource, now=None):
        with _LOCK:
            live = self._sweep(resource, now)
            if live:
                live.pop()
            self._slots[resource] = live

    def in_use(self, resource, now=None):
        with _LOCK:
            return len(self._sweep(resource, now))
