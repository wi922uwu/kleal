"""Buddy unit tests — no network. A FakeLLM scripts the model turns.

Run: python tests/test_buddy.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buddy.store import Store, seed_demo
from buddy import agent, matching


def _store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = Store(path)
    seed_demo(s)
    s.upsert_profile(user_id="me", name="Me", city="Barcelona",
                     languages=["ru", "en"], interests=["dota 2", "football"], formats=["small_group"])
    return s


class FakeLLM:
    """Callable that returns scripted assistant messages in order."""
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []

    def __call__(self, messages, tools=None, tool_choice="auto", **kw):
        self.calls.append(messages)
        return {"content": self.scripted.pop(0)}


def test_chat_only():
    s = _store()
    fake = FakeLLM(["Привет! Чем занят сегодня?"])
    r = agent.handle_message("me", "привет", s, llm_chat=fake, tool_mode="prompt")
    assert r["tool_call"] is None, r
    assert r["matches"] is None, r
    assert "Привет" in r["reply"]
    assert len(fake.calls) == 1
    print("ok  chat_only")


def test_intent_matching():
    s = _store()
    fake = FakeLLM([
        'TOOL_CALL find_people {"category":"games","activity":"dota teammate","tags":["dota 2"],"mode":"online","format":"game_lobby"}',
        "Нашёл варианты: **Dima** — dota 2, тот же город. Погнали?",
    ])
    r = agent.handle_message("me", "хочу катку в доту вечером", s, llm_chat=fake, tool_mode="prompt")
    assert r["tool_call"] == "find_people", r
    assert r["intent"]["category"] == "games", r["intent"]
    assert r["matches"], r
    ids = [m["user_id"] for m in r["matches"]]
    assert "u_dima" in ids, ids
    # u_dima (games + dota2 + langs + format) should outrank u_alex
    assert r["matches"][0]["user_id"] == "u_dima", r["matches"]
    assert len(fake.calls) == 2
    print("ok  intent_matching ->", ids)


def test_category_inference():
    i = matching.normalize_intent({"tags": ["dota 2"], "activity": "teammate"})
    assert i["category"] == "games", i
    j = matching.normalize_intent({"activity": "practice spanish", "tags": []})
    assert j["category"] == "language_practice", j
    print("ok  category_inference")


def test_no_match_fallback():
    s = _store()
    fake = FakeLLM([
        # online mode (no same-city boost) + a topic nobody shares -> genuinely empty
        'TOOL_CALL find_people {"category":"culture_event","activity":"opera stream","tags":["opera"],"mode":"online"}',
        "Пока точного нет — расширить поиск?",
    ])
    r = agent.handle_message("me", "найди компанию посмотреть оперу онлайн", s, llm_chat=fake, tool_mode="prompt")
    assert r["tool_call"] == "find_people", r
    assert r["matches"] == [], r["matches"]  # nobody shares culture_event/opera, online = no city boost
    assert "расширить" in r["reply"]
    print("ok  no_match_fallback")


def test_malformed_tool_json():
    s = _store()
    fake = FakeLLM([
        'TOOL_CALL find_people {"category":"games","tags":["dota 2"]',  # missing closing brace
        "Вот варианты.",
    ])
    r = agent.handle_message("me", "доту", s, llm_chat=fake, tool_mode="prompt")
    assert r["tool_call"] == "find_people", r
    assert r["intent"]["category"] == "games", r["intent"]
    print("ok  malformed_tool_json (lenient repair)")


def test_history_persisted():
    s = _store()
    fake = FakeLLM(["ответ раз", "ответ два"])
    agent.handle_message("me", "первый", s, llm_chat=fake, tool_mode="prompt")
    agent.handle_message("me", "второй", s, llm_chat=fake, tool_mode="prompt")
    hist = s.get_history("me")
    assert hist[0]["content"] == "первый" and hist[0]["role"] == "user", hist
    assert hist[-1]["content"] == "ответ два", hist
    print("ok  history_persisted")


if __name__ == "__main__":
    test_chat_only()
    test_intent_matching()
    test_category_inference()
    test_no_match_fallback()
    test_malformed_tool_json()
    test_history_persisted()
    print("\nALL BUDDY TESTS PASSED")
