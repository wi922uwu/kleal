# -*- coding: utf-8 -*-
"""§4.3 / §8.4 — Interval algebra для Time-блока: UTC-нормализация + пересечение окон + длительность.

Все времена нормализуются в UTC-минуты (исходный tz_offset вычитается), сравнение — после нормализации.
Переход на летнее время моделируется разным tz_offset у сторон (§8.4 «DST входит в обязательные тесты»).
"""


def to_utc_min(hhmm, tz_offset_min=0):
    """'HH:MM' + смещение зоны -> минуты в UTC (0..1439). None если не парсится."""
    try:
        h, m = str(hhmm).split(":")
        return (int(h) * 60 + int(m) - int(tz_offset_min)) % 1440
    except Exception:
        return None


def _norm(windows, tz):
    out = []
    for w in (windows or []):
        if len(w) != 2:
            continue
        s, e = to_utc_min(w[0], tz), to_utc_min(w[1], tz)
        if s is None or e is None:
            continue
        if e <= s:
            e += 1440                      # окно через полночь
        out.append((s, e))
    return out


def overlap_min(a, b):
    """Пересечение двух UTC-окон [start,end] в минутах. 0 если нет."""
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    return max(0, hi - lo)


def windows_overlap(a_windows, b_windows, *, min_duration_min=0, a_tz=0, b_tz=0):
    """§4.3 interval algebra: (feasible, overlap_min). Есть ли общее окно достаточной длительности."""
    A, B = _norm(a_windows, a_tz), _norm(b_windows, b_tz)
    best = 0
    for a in A:
        for b in B:
            # учтём и сдвиг на сутки (одно из окон могло уехать за полночь)
            for shift in (0, 1440, -1440):
                lo, hi = max(a[0], b[0] + shift), min(a[1], b[1] + shift)
                best = max(best, max(0, hi - lo))
    need = max(1, int(min_duration_min)) if min_duration_min else 1
    return (best >= need, best)
