# -*- coding: utf-8 -*-
"""Persistent, idempotent evidence for opt-in profile-interest suggestions."""
import hashlib
import threading
import time

from interest_normalization import normalize_confirmed_interest


THRESHOLD = 6
REOFFER_EVIDENCE_DELTA = 3
COOLDOWN_SECONDS = 30 * 24 * 3600
SOURCE = "confirmed_intent"
SCHEMA_VERSION = 1


def _digest(value):
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:24]


def _user_key(value):
    return " ".join(str(value or "").strip().lower().split())


class InterestSuggestionTracker:
    """Mutates one supplied JSON document under one lock.

    Raw text is never persisted. Evidence contains only hashed event/intent ids, source and time.
    The caller supplies ``save`` so the same logic works with JSON and the existing PostgreSQL
    top-level JSONB store.
    """

    def __init__(self, document, lock=None, save=None, normalizer=normalize_confirmed_interest):
        self.document = document
        self.lock = lock or threading.RLock()
        self.save = save or (lambda: None)
        self.normalizer = normalizer
        self.document.setdefault("v", SCHEMA_VERSION)
        self.document.setdefault("users", {})

    def _user(self, user_id):
        return self.document["users"].setdefault(_user_key(user_id), {
            "events": {}, "interests": {}, "pending": None,
        })

    def _normalized_ids(self, values):
        out = set()
        for value in values or []:
            item = self.normalizer(value)
            if item:
                out.add(item.canonical_id)
        return out

    def _public(self, user, rec):
        pending = user.get("pending") or {}
        if not rec or pending.get("canonical_id") != rec.get("canonical_id"):
            return None
        return {
            "id": pending.get("id"),
            "canonical_id": rec.get("canonical_id"),
            "profile_key": rec.get("profile_key"),
            "labels": dict(rec.get("labels") or {}),
            "evidence_count": int(rec.get("count") or 0),
        }

    def _suppress_existing(self, user, profile_interests, now):
        have = self._normalized_ids(profile_interests)
        pending = user.get("pending") or {}
        cid = pending.get("canonical_id")
        if cid and cid in have:
            rec = (user.get("interests") or {}).get(cid) or {}
            rec["resolved"] = "profile_present"
            rec["resolved_at"] = now
            user["pending"] = None
            return True
        return False

    def pending(self, user_id, profile_interests=None, now=None):
        now = float(now if now is not None else time.time())
        with self.lock:
            user = self._user(user_id)
            changed = self._suppress_existing(user, profile_interests, now)
            pending = user.get("pending") or {}
            rec = (user.get("interests") or {}).get(pending.get("canonical_id"))
            if changed:
                self.save()
            return self._public(user, rec)

    def record(self, user_id, event_id, topics, profile_interests=None, negative_topics=None,
               intent_id=None, now=None):
        now = float(now if now is not None else time.time())
        user_key = _user_key(user_id)
        if not user_key or not str(event_id or "").strip():
            return {"counted": False, "reason": "identity_required", "suggestion": None}
        event_hash = _digest(event_id)
        with self.lock:
            user = self._user(user_key)
            if event_hash in user["events"]:
                pending = user.get("pending") or {}
                rec = user["interests"].get(pending.get("canonical_id"))
                return {"counted": False, "reason": "duplicate_event", "suggestion": self._public(user, rec)}

            negative = self._normalized_ids(negative_topics)
            existing = self._normalized_ids(profile_interests)
            normalized = {}
            for topic in topics or []:
                item = self.normalizer(topic)
                if item and item.canonical_id not in negative:
                    normalized[item.canonical_id] = item

            user["events"][event_hash] = {
                "at": now, "source": SOURCE, "intent": _digest(intent_id) if intent_id else None,
                "canonical_ids": sorted(normalized),
            }
            for cid, item in normalized.items():
                rec = user["interests"].setdefault(cid, {
                    "canonical_id": cid, "profile_key": item.profile_key,
                    "labels": dict(item.labels), "count": 0, "evidence": [],
                })
                rec["count"] = int(rec.get("count") or 0) + 1
                rec["last_evidence_at"] = now
                rec["evidence"] = (list(rec.get("evidence") or []) + [{
                    "event": event_hash, "intent": _digest(intent_id) if intent_id else None,
                    "source": SOURCE, "at": now,
                }])[-20:]

            self._suppress_existing(user, profile_interests, now)
            if not user.get("pending"):
                eligible = []
                for cid, rec in user["interests"].items():
                    if cid in existing or rec.get("resolved") == "confirmed":
                        continue
                    count = int(rec.get("count") or 0)
                    prompted_count = int(rec.get("last_prompt_count") or 0)
                    prompted_at = float(rec.get("last_prompt_at") or 0)
                    first = not prompted_count and count >= THRESHOLD
                    again = (prompted_count and count - prompted_count >= REOFFER_EVIDENCE_DELTA
                             and now - prompted_at >= COOLDOWN_SECONDS)
                    if first or again:
                        eligible.append((count, cid, rec))
                if eligible:
                    _count, cid, rec = sorted(eligible, key=lambda x: (-x[0], x[1]))[0]
                    sid = "isg_" + _digest("%s|%s|%s" % (user_key, cid, rec["count"]))
                    user["pending"] = {"id": sid, "canonical_id": cid, "created_at": now}
                    rec["last_prompt_count"] = rec["count"]
                    rec["last_prompt_at"] = now
            self.save()
            pending = user.get("pending") or {}
            rec = user["interests"].get(pending.get("canonical_id"))
            return {"counted": bool(normalized), "reason": "recorded", "suggestion": self._public(user, rec)}

    def act(self, user_id, suggestion_id, action, now=None):
        now = float(now if now is not None else time.time())
        with self.lock:
            user = self._user(user_id)
            pending = user.get("pending") or {}
            if not pending or pending.get("id") != suggestion_id:
                return {"ok": False, "error": "STALE_SUGGESTION"}
            rec = user["interests"].get(pending.get("canonical_id")) or {}
            if action == "confirm":
                rec["resolved"] = "confirmed"
                rec["confirmed_at"] = now
            elif action in ("dismiss", "decline"):
                rec["resolved"] = "dismissed"
                rec["dismissed_at"] = now
            else:
                return {"ok": False, "error": "BAD_ACTION"}
            user["pending"] = None
            self.save()
            return {"ok": True}

    def forget(self, user_id):
        with self.lock:
            removed = self.document["users"].pop(_user_key(user_id), None) is not None
            if removed:
                self.save()
            return {"ok": True, "removed": removed}
