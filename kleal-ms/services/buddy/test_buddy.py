# -*- coding: utf-8 -*-
# Tests for the buddy agent — pure conversation/guard logic (no live LLM).
# Run: python3 test_buddy.py
import os
import sys
import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "shared"), os.path.join(_HERE, "shared")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
_spec = importlib.util.spec_from_file_location("buddy", os.path.join(_HERE, "app.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

_fails = []


def check(name, cond, extra=""):
    print(("  ok  " if cond else "FAIL  ") + name + (("  -> " + extra) if (extra and not cond) else ""))
    if not cond:
        _fails.append(name)


def U(t, chat=False): return {"role": "user", "content": t, "chat": chat}
def A(t, chat=False): return {"role": "assistant", "content": t, "chat": chat}


# ---- 1. _builder_msgs: the conversation is kept, the builder is blind to small talk ----
thread = [U("что такое хламидиоз", True), A("Это бактериальная инфекция.", True), U("расскажи детальнее")]
b = B._builder_msgs(thread)
check("builder hides chat-marked turns", len(b) == 1, str(len(b)))
check("builder keeps the newest user turn", b[0]["content"] == "расскажи детальнее", str(b))
check("the full thread is untouched", len(thread) == 3)

# every turn already answered conversationally -> the builder still gets the turn it must judge
allchat = [U("привет", True), A("Привет!", True)]
check("all-chat thread still yields the last user turn", B._builder_msgs(allchat) == [allchat[0]],
      str(B._builder_msgs(allchat)))
check("empty thread -> empty builder view", B._builder_msgs([]) == [])
check("no chat key at all (old client) -> everything is builder material",
      len(B._builder_msgs([{"role": "user", "content": "хочу кофе"}])) == 1)

# a real multi-turn build is unmarked and survives whole
build = [U("хочу в футбол"), A("Когда удобно?"), U("в субботу вечером")]
check("unmarked build thread passes through intact", B._builder_msgs(build) == build)

# ---- 2. _strip_foreign: drop the artifact, keep the sentence ----
s = B._strip_foreign("Кучевые облака (积云) — это красиво.")
check("strips a CJK gloss", "积" not in s and "云" not in s, s)
check("removes the emptied bracket", "()" not in s, s)
check("keeps the Russian sentence", "Кучевые облака" in s and "красиво" in s, s)
check("no space before punctuation", " —" in s and "  " not in s, repr(s))
check("greek zeta artifact removed", B._strip_foreign("биζнес") == "бинес", B._strip_foreign("биζнес"))
check("clean text is returned unchanged", B._strip_foreign("Обычный русский текст.") == "Обычный русский текст.")

# ---- 3. _salvage: rescue the glyph case, still reject the wrong language ----
check("salvages a Russian reply with a CJK gloss",
      B._salvage("Перистые облака (卷云) высоко в небе.", "ru").startswith("Перистые"),
      B._salvage("Перистые облака (卷云) высоко в небе.", "ru"))
check("salvage keeps a clean reply as-is", B._salvage("Всё хорошо.", "ru") == "Всё хорошо.")
check("salvage refuses an English reply to a Russian user", B._salvage("Sounds good, when are you free?", "ru") == "",
      repr(B._salvage("Sounds good, when are you free?", "ru")))
check("salvage refuses an empty reply", B._salvage("", "ru") == "")
check("salvage cleans glyphs for non-ru languages too",
      B._salvage("Cumulus clouds (积云) are fluffy.", "en") == "Cumulus clouds are fluffy.",
      B._salvage("Cumulus clouds (积云) are fluffy.", "en"))
check("spanish reply survives salvage", B._salvage("Las nubes son bonitas.", "es") == "Las nubes son bonitas.")

# ---- 4. _lang_ok still rejects what it should (guard did not get weaker) ----
check("lang_ok rejects raw CJK", B._lang_ok("Кучевые (积云)", "ru") is False)
check("lang_ok rejects an English answer to ru", B._lang_ok("Sounds good, when are you free?", "ru") is False)
check("lang_ok accepts normal Russian", B._lang_ok("Давай в субботу в 19:00.", "ru") is True)
check("lang_ok allows standalone Latin names in ru", B._lang_ok("Поиграем в Dota вечером?", "ru") is True)

# ---- 5. the mirror case: a Russian answer to an EN/ES user (the EN/ES audience bug) ----
check("lang_ok rejects a Russian answer to en",
      B._lang_ok("Привет, Иван! Падель - это разновидность тенниса.", "en") is False)
check("lang_ok rejects a Russian answer to es",
      B._lang_ok("Привет! Падель - это разновидность тенниса, очень популярная в Испании.", "es") is False)
check("lang_ok accepts plain English", B._lang_ok("Padel is a racket sport played in pairs.", "en") is True)
check("lang_ok accepts plain Spanish", B._lang_ok("El pádel se juega en pareja.", "es") is True)
check("lang_ok tolerates a Russian name inside an English sentence",
      B._lang_ok("Sure Иван, padel is a racket sport played in pairs on a small court.", "en") is True)
check("salvage rejects a Russian reply to an English user",
      B._salvage("Привет, Иван! Падель - это разновидность тенниса.", "en") == "")

# ---- 6. thread_lang: a one-word follow-up inherits the conversation's language ----
es_thread = [U("qué es el padel", True), A("El padel es un deporte...", True), U("ejemplos")]
check("spanish thread keeps spanish on a bare follow-up", B.thread_lang(es_thread, "ejemplos") == "es",
      B.thread_lang(es_thread, "ejemplos"))
ru_thread = [U("расскажи про облака", True), A("Облака бывают разные.", True), U("ещё")]
check("russian thread stays russian", B.thread_lang(ru_thread, "ещё") == "ru")
en_thread = [U("what is padel", True), A("Padel is a racket sport.", True), U("examples")]
check("english thread stays english", B.thread_lang(en_thread, "examples") == "en")
check("a decisive spanish turn wins over history",
      B.thread_lang(en_thread + [U("¿dónde puedo jugar?")], "¿dónde puedo jugar?") == "es")
check("a long english turn is trusted on its own",
      B.thread_lang(ru_thread, "could you tell me more about this topic") == "en")
check("thread_lang with no history falls back cleanly", B.thread_lang([], "") == "en")

print()
if _fails:
    print("FAILED %d:" % len(_fails), ", ".join(_fails))
    sys.exit(1)
print("ALL PASS")
