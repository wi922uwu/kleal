# -*- coding: utf-8 -*-
"""Склад ветвей батареи: копится, не перезаписывается.

ЗАЧЕМ ОТДЕЛЬНЫЙ СКЛАД. Кольцо событий `battery-live.jsonl` батарея подрезает сама, и история в
панели живёт полчаса. Владелец (17.09.2026): «данные должны накапливаться, а не перезаписываться».
Здесь каждый ЗАКОНЧЕННЫЙ сценарий складывается в одну строку: форма разговора (ходы и где сработал
попап, затея, два чтения мастер ↔ попап, беды) И САМИ РЕПЛИКИ.

СЛОВА ХРАНИМ, И ВОТ ПОЧЕМУ. Сперва тексты сюда не клали — они лежат в кольце и в журналах
`/root/kleal-archive/battery/*.log`. Оказалось, ни то ни другое не годится: кольцо коротко, и у
сценария из прошлого круга в панели оставалась ОДНА строка вместо разговора (снято владельцем со
скриншота: «почему диалоги из одного слова»); а журналы пишут 64 потока разом, блоки перемешаны, и
достать оттуда разговор по метке нельзя. Замер: реплика в среднем 53 знака, ходов 6,2 — прибавка
≈330 байт на ветвь при нынешних 650. Это 113 МБ в сутки при 65 ГБ свободных, и ротация их держит.

В КОЛЬЦА СЛОВА НЕ ЕДУТ: `tail()` отдаёт ветви без реплик (панель рисует форму), а разговор
выбранной ветки запрашивается отдельно — `find()`.

ПОЧЕМУ ПИШЕТ АДМИНКА, А НЕ БАТАРЕЯ. `tools/buddy_battery.py` — измерительный прибор, его правят
по своей дисциплине и часто; складывать туда ещё и хранение — значит цеплять панель к каждой его
правке. Админка кольцо и так читает каждые две с половиной секунды; складка — тот же хвост.

ФАЙЛ ТОЛЬКО РАСТЁТ. При размере больше `ROTATE_BYTES` он переименовывается в `.1` (прежний `.1`
уходит) — это ротация, не подрезка: панель читает оба файла подряд.
"""
import json
import os
import re
import threading
import time

TREE = "/root/kleal-archive/battery-tree.jsonl"
LIVE = "/root/kleal-archive/battery-live.jsonl"
# Со словами ветвь весит ~1 КБ, круг — полмегабайта. Полгигабайта на файл и один запасной — это
# примерно девять суток истории и один процент диска.
ROTATE_BYTES = 512 * 1024 * 1024
TEXT_MAX = 300
SETTLE_S = 5.0          # сценарий закончен, когда после scen_done по нему тихо столько секунд
SEEN_TAIL = 5000        # сколько последних ключей читать при старте, чтобы не дублировать
_AT = re.compile(r"на ходу (\d+)")
_LOCK = threading.Lock()


def branch_from_events(events, round_t=0.0):
    """События одного сценария → ветвь. ТА ЖЕ форма, что у `ветвьИзСобытий` в ui.py.

    Порядок событий в кольце не всегда хронологический по смыслу: `intent` и `problem` бывают
    ПОСЛЕ `scen_done` (снято 17.09.2026), поэтому складываем по видам, а не по позиции."""
    ev = sorted(events, key=lambda e: float(e.get("t") or 0))
    start = next((e for e in ev if e.get("kind") == "scen_start"), None)
    dones = [e for e in ev if e.get("kind") == "scen_done"]
    done = dones[-1] if dones else None
    turns, ready_at = [], 0
    for e in ev:
        if e.get("kind") == "human":
            turns.append({"k": "h", "ready": 0, "txt": str(e.get("text") or "")[:TEXT_MAX]})
        elif e.get("kind") == "kleal":
            r = 1 if e.get("ready") else 0
            turns.append({"k": "k", "ready": r, "txt": str(e.get("text") or "")[:TEXT_MAX]})
            if r and not ready_at:
                ready_at = sum(1 for t in turns if t["k"] == "h")
    intents = [e for e in ev if e.get("kind") == "intent"]
    intent = None
    if intents:
        i = intents[-1]
        intent = {"title": str(i.get("text") or "")[:80], "subject": str(i.get("subject") or "")[:40],
                  "topics": [str(x)[:24] for x in (i.get("topics") or [])][:6],
                  "at": int(i.get("turns") or ready_at or 0)}
    results = [e for e in ev if e.get("kind") == "result"]
    res = results[-1] if results else None
    master = popup = None
    fired = turns_said = 0
    if res:
        m = res.get("master") or {}
        master = {"title": str(m.get("title") or "")[:80], "subject": str(m.get("subject") or "")[:40],
                  "role": str(m.get("role") or "")[:20]} if m else None
        p = res.get("popup")
        popup = {"title": str(p.get("title") or "")[:80]} if p else None
        fired = int(res.get("fired") or 0)
        turns_said = int(res.get("turns_said") or 0)
    problems = []
    for e in ev:
        if e.get("kind") != "problem":
            continue
        txt = str(e.get("text") or "")
        m = re.match(r"^([А-ЯЁ\- ]+):\s*(.*)$", txt)
        kind, rest = (m.group(1).strip(), m.group(2)) if m else ("БЕДА", txt)
        at = _AT.search(rest)
        problems.append({"kind": kind[:32], "at": int(at.group(1)) if at else None, "text": rest[:120]})
    src = (start or done or {})
    t0 = float((done or {}).get("t0") or (start or {}).get("t") or (ev[0].get("t") if ev else 0) or 0)
    t1 = float(ev[-1].get("t") or 0) if ev else 0.0
    # `bad` в scen_done пишется ДО проверки попапа: там 0 при живой беде «ПОПАП НЕ СРАБОТАЛ».
    bad = max(int((done or {}).get("bad") or 0), len(problems))
    return {"scen": str(src.get("scen") or (ev[0].get("scen") if ev else "")),
            "lang": str(src.get("lang") or ""), "hard": int(src.get("hard") or 0),
            "src": str(src.get("src") or ""), "r": float(round_t or 0), "t0": t0, "t1": t1,
            "turns": turns, "intent": intent, "fired": fired, "turns_said": turns_said,
            "master": master, "popup": popup, "problems": problems, "bad": bad,
            "done": bool(done)}


def fold(events, now=None, settle=SETTLE_S, known=None):
    """Все события кольца → законченные ветви (с отметкой круга), незаконченные пропускаем.

    `known` — отметки прогонов, виденные РАНЬШЕ. Хвост кольца держит примерно один прогон, и у
    сценариев, начавшихся до `run_start` в этом хвосте, отметки не было вовсе: они сваливались в
    общий мешок `r=0` и рисовались одной жирной дугой поверх настоящих. Теперь такой ветви
    достаётся последний известный прогон, начавшийся не позже неё."""
    now = time.time() if now is None else now
    by, round_t, round_of = {}, 0.0, {}
    for e in sorted(events, key=lambda e: float(e.get("t") or 0)):
        k = e.get("kind")
        if k == "run_start":
            round_t = float(e.get("t") or 0)
            continue
        s = e.get("scen")
        if not s:
            continue
        by.setdefault(s, []).append(e)
        # Круг ветви — тот, в котором она НАЧАЛАСЬ: события сценария могут перевалить за run_start
        # следующего круга, и ветвь не должна уезжать в чужое кольцо.
        if s not in round_of:
            round_of[s] = round_t
    прошлые = sorted(float(x) for x in (known or []) if x)
    out = []
    for s, ev in by.items():
        if not any(e.get("kind") == "scen_done" for e in ev):
            continue
        last = max(float(e.get("t") or 0) for e in ev)
        if now - last < settle:
            continue
        b = branch_from_events(ev, round_of.get(s, 0.0))
        if not b["r"] and прошлые:
            ранее = [x for x in прошлые if x <= b["t0"] + 1]
            if ранее:
                b["r"] = ранее[-1]
        out.append(b)
    return out


def _key(b):
    return "%s@%.3f" % (b.get("scen"), float(b.get("t0") or 0))


class Store(object):
    """Дописывает ветви и отдаёт хвост. Один экземпляр на процесс."""

    def __init__(self, path=TREE, live=LIVE):
        self.path, self.live = path, live
        self.seen = set()
        self.count = 0                 # сколько разговоров в складе всего: считаем один раз и ведём
        self.rounds_seen = []          # отметки прогонов: хвост кольца помнит один, а нам нужны все
        self._load_seen()
        for _p in (self.path + ".1", self.path):
            try:
                with open(_p, "rb") as f:
                    self.count += sum(1 for _ in f)
            except FileNotFoundError:
                continue

    def _load_seen(self):
        for p in (self.path + ".1", self.path):
            try:
                with open(p, encoding="utf-8") as f:
                    for line in f.readlines()[-SEEN_TAIL:]:
                        try:
                            self.seen.add(_key(json.loads(line)))
                        except Exception:
                            continue
            except FileNotFoundError:
                continue

    def _rotate(self):
        try:
            if os.path.getsize(self.path) > ROTATE_BYTES:
                os.replace(self.path, self.path + ".1")
        except OSError:
            pass

    def append(self, branches):
        """Новые ветви — в файл; повторы молча пропускаем. Возвращает, сколько дописано."""
        new = [b for b in branches if _key(b) not in self.seen]
        if not new:
            return 0
        with _LOCK:
            self._rotate()
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                for b in new:
                    f.write(json.dumps(b, ensure_ascii=False) + "\n")
                    self.seen.add(_key(b))
            self.count += len(new)
        return len(new)

    def fold_live(self, now=None):
        """Один проход: хвост кольца → склад."""
        events = []
        try:
            with open(self.live, encoding="utf-8") as f:
                for line in f.readlines()[-7200:]:
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        continue
        except FileNotFoundError:
            return 0
        for e in events:
            if e.get("kind") == "run_start":
                t = float(e.get("t") or 0)
                if t and t not in self.rounds_seen:
                    self.rounds_seen.append(t)
        self.rounds_seen = sorted(self.rounds_seen)[-200:]
        return self.append(fold(events, now, known=self.rounds_seen))

    @staticmethod
    def _thin(b):
        """Ветвь для КОЛЕЦ: только то, чем рисуют дугу и штрих.

        ЗАЧЕМ ТАК СУХО. При холодном старте панель просит все дуги разом, и полная ветвь весит
        871 байт: шестнадцать прогонов — это шесть с половиной мегабайт на одно открытие страницы.
        Кольцам нужны угол, длина, цвет, где попап и как назвали; всё остальное — темы, предмет,
        роль, тексты бед — читается, когда разговор ОТКРОЮТ (`find`). Выходит ~310 байт."""
        p = (b.get("problems") or [])
        m, i = (b.get("master") or {}), (b.get("intent") or {})
        return {"scen": b.get("scen"), "t0": b.get("t0"), "t1": b.get("t1"), "r": b.get("r"),
                "lang": b.get("lang"), "hard": b.get("hard"), "src": b.get("src"),
                "done": b.get("done"), "bad": b.get("bad"), "fired": b.get("fired"),
                "turns": [{"k": t.get("k"), "ready": t.get("ready")} for t in (b.get("turns") or [])],
                "problems": [{"kind": x.get("kind")} for x in p[:1]],
                "master": ({"title": m.get("title")} if m.get("title") else None),
                "intent": ({"title": i.get("title")} if i.get("title") else None)}

    def rounds_tail(self, n=16):
        """Последние `n` ПРОГОНОВ целиком — то, что панель рисует дугами при холодном старте.

        По числу строк это не считается: прогон бывает и в 60 сценариев, и в 480. Идём по хвосту
        файла назад, пока не наберём n разных отметок круга."""
        rows = []
        for p in (self.path + ".1", self.path):
            try:
                with open(p, encoding="utf-8") as f:
                    rows.extend(f.readlines()[-40000:])
            except FileNotFoundError:
                continue
        out, seen = [], []
        for line in reversed(rows):
            try:
                b = json.loads(line)
            except Exception:
                continue
            r = round(float(b.get("r") or 0), 3)
            if r not in seen:
                if len(seen) >= n:
                    break
                seen.append(r)
            out.append(self._thin(b))
        out.reverse()
        return out

    def find(self, scen, t0=None):
        """Одна ветвь ЦЕЛИКОМ, с репликами: её просят, когда человек щёлкнул по ветке."""
        best = None
        for p in (self.path + ".1", self.path):
            try:
                with open(p, encoding="utf-8") as f:
                    for line in f.readlines()[-60000:]:
                        if scen not in line:
                            continue
                        try:
                            b = json.loads(line)
                        except Exception:
                            continue
                        if b.get("scen") != scen:
                            continue
                        if t0 is not None and abs(float(b.get("t0") or 0) - float(t0)) > 1.5:
                            continue
                        if best is None or float(b.get("t1") or 0) >= float(best.get("t1") or 0):
                            best = b
            except FileNotFoundError:
                continue
        return best

    def tail(self, since=0.0, limit=6000, thin=True):
        """Последние `limit` ветвей с t1 > since — из `.1` и основного файла подряд."""
        rows = []
        for p in (self.path + ".1", self.path):
            try:
                with open(p, encoding="utf-8") as f:
                    rows.extend(f.readlines()[-limit:])
            except FileNotFoundError:
                continue
        out = []
        for line in rows[-limit:]:
            try:
                b = json.loads(line)
            except Exception:
                continue
            if float(b.get("t1") or 0) > since:
                out.append(self._thin(b) if thin else b)
        return out


def start_folding(store, period_s=4.0):
    """Фоновый поток складки. Демон: умирает вместе с админкой, ничего не держит."""
    def loop():
        while True:
            try:
                store.fold_live()
            except Exception:
                pass
            time.sleep(period_s)
    t = threading.Thread(target=loop, name="battery-tree-fold", daemon=True)
    t.start()
    return t
