"""Buddy SQLite store: user profiles + conversation history.

Self-contained, Kleal-shaped schema (own DB by default). Path via env BUDDY_DB.
`signals.active_intent` mirrors the dating_ai convention so a later adapter can point
at the pod's dating_ai.db.
"""
import os
import json
import time
import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profile (
  user_id        TEXT PRIMARY KEY,
  name           TEXT    DEFAULT '',
  city           TEXT    DEFAULT '',
  languages      TEXT    DEFAULT '[]',
  interests      TEXT    DEFAULT '[]',
  formats        TEXT    DEFAULT '[]',
  availability   TEXT    DEFAULT '',
  dating_enabled INTEGER DEFAULT 0,
  blocked        TEXT    DEFAULT '[]',
  signals        TEXT    DEFAULT '{}',
  updated_at     TEXT    DEFAULT ''
);
CREATE TABLE IF NOT EXISTS conversations (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    TEXT,
  agent_type TEXT DEFAULT 'buddy',
  role       TEXT,
  content    TEXT,
  created_at TEXT
);
"""

_JSON_LIST_FIELDS = ("languages", "interests", "formats", "blocked")
_DEFAULTS = {"name": "", "city": "", "languages": [], "interests": [], "formats": [],
             "availability": "", "dating_enabled": 0, "blocked": [], "signals": {}}


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Store:
    def __init__(self, db_path=None):
        self.db_path = db_path or os.environ.get("BUDDY_DB", "buddy.db")
        self._init()

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        c = self._conn()
        c.executescript(_SCHEMA)
        c.commit()
        c.close()

    def _row_to_profile(self, r):
        p = dict(r)
        for f in _JSON_LIST_FIELDS:
            try:
                p[f] = json.loads(p.get(f) or "[]")
            except Exception:
                p[f] = []
        try:
            p["signals"] = json.loads(p.get("signals") or "{}")
        except Exception:
            p["signals"] = {}
        p["dating_enabled"] = bool(p.get("dating_enabled"))
        return p

    def get_profile(self, user_id):
        c = self._conn()
        r = c.execute("SELECT * FROM user_profile WHERE user_id=?", (user_id,)).fetchone()
        c.close()
        return self._row_to_profile(r) if r else None

    def list_profiles(self, exclude=None):
        c = self._conn()
        rows = c.execute("SELECT * FROM user_profile").fetchall()
        c.close()
        return [self._row_to_profile(r) for r in rows if r["user_id"] != exclude]

    def upsert_profile(self, user_id, **fields):
        prof = {"user_id": user_id}
        prof.update({k: (v.copy() if isinstance(v, (list, dict)) else v) for k, v in _DEFAULTS.items()})
        existing = self.get_profile(user_id)
        if existing:
            for k in _DEFAULTS:
                if k in existing:
                    prof[k] = existing[k]
        prof.update(fields)
        c = self._conn()
        c.execute(
            """INSERT INTO user_profile
               (user_id,name,city,languages,interests,formats,availability,dating_enabled,blocked,signals,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 name=excluded.name, city=excluded.city, languages=excluded.languages,
                 interests=excluded.interests, formats=excluded.formats, availability=excluded.availability,
                 dating_enabled=excluded.dating_enabled, blocked=excluded.blocked,
                 signals=excluded.signals, updated_at=excluded.updated_at""",
            (user_id, prof["name"], prof["city"], json.dumps(prof["languages"], ensure_ascii=False),
             json.dumps(prof["interests"], ensure_ascii=False), json.dumps(prof["formats"], ensure_ascii=False),
             prof["availability"], int(bool(prof["dating_enabled"])),
             json.dumps(prof["blocked"], ensure_ascii=False), json.dumps(prof["signals"], ensure_ascii=False), _now()),
        )
        c.commit()
        c.close()

    def set_active_intent(self, user_id, intent):
        prof = self.get_profile(user_id)
        signals = (prof.get("signals") if prof else {}) or {}
        signals["active_intent"] = intent
        self.upsert_profile(user_id, signals=signals)

    def add_message(self, user_id, role, content, agent_type="buddy"):
        c = self._conn()
        c.execute(
            "INSERT INTO conversations (user_id,agent_type,role,content,created_at) VALUES (?,?,?,?,?)",
            (user_id, agent_type, role, content, _now()),
        )
        c.commit()
        c.close()

    def get_history(self, user_id, limit=12):
        c = self._conn()
        rows = c.execute(
            "SELECT role,content FROM conversations WHERE user_id=? AND role IN ('user','assistant') "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        c.close()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def seed_demo(store):
    """A few Barcelona-heavy profiles for local runs and tests."""
    demo = [
        {"user_id": "u_alex", "name": "Alex", "city": "Barcelona", "languages": ["en", "es"],
         "interests": ["football", "fc barcelona", "dota 2"], "formats": ["small_group", "one_on_one"],
         "availability": "weekday evenings"},
        {"user_id": "u_mar", "name": "Mar", "city": "Barcelona", "languages": ["es", "en"],
         "interests": ["spanish", "coffee", "architecture"], "formats": ["one_on_one"],
         "availability": "weekends"},
        {"user_id": "u_dima", "name": "Dima", "city": "Barcelona", "languages": ["ru", "en"],
         "interests": ["dota 2", "cs2", "ai"], "formats": ["game_lobby", "online_room"],
         "availability": "evenings"},
        {"user_id": "u_lena", "name": "Lena", "city": "Madrid", "languages": ["es"],
         "interests": ["running", "yoga"], "formats": ["small_group"], "availability": "mornings"},
        {"user_id": "u_tom", "name": "Tom", "city": "Barcelona", "languages": ["en"],
         "interests": ["startup", "ai", "networking"], "formats": ["one_on_one", "small_group"],
         "availability": "weekday evenings"},
    ]
    for p in demo:
        store.upsert_profile(**p)
