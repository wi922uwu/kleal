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

# ---- 7. topics: multi-word phrases, accents, and the EN-first union ----
check("multi-word alias resolves WHOLE ('table tennis' is not 'tennis')",
      B.norm_topics(["table tennis"]) == ["pingpong"], str(B.norm_topics(["table tennis"])))
check("a multi-word phrase with no alias still splits",
      "ai" in B.norm_topics(["artificial intelligence", "ai"]), str(B.norm_topics(["artificial intelligence", "ai"])))
check("plain single words are unaffected", B.norm_topics(["футбол"]) == ["football"],
      str(B.norm_topics(["футбол"])))

check("spanish sport resolves", B.norm_topic("fútbol") == "football", B.norm_topic("fútbol"))
check("spanish padel resolves", B.norm_topic("pádel") == "padel", B.norm_topic("pádel"))
check("spanish coffee resolves", B.norm_topic("café") == "coffee", B.norm_topic("café"))
check("every ES/EN alias points at a real taxonomy word",
      all(v in B.BROAD_OF for v in B._EN_SYN.values()),
      str([k for k, v in B._EN_SYN.items() if v not in B.BROAD_OF]))

import re as _re
_TOK = _re.compile(r"[a-zа-яёáéíóúüñç0-9]{4,}")
check("tokeniser keeps «sábado» whole (was 'bado')", "sábado" in _TOK.findall("jugar el sábado"),
      str(_TOK.findall("jugar el sábado")))
check("tokeniser keeps «fútbol» whole (was 'tbol')", "fútbol" in _TOK.findall("jugar al fútbol"),
      str(_TOK.findall("jugar al fútbol")))

check("spanish function words are stopped", all(w in B._RAW_STOP for w in ("quiero", "quedar", "jugar", "alguien")))
check("weekdays are not topics", all(w in B._GENERIC_TOPIC for w in ("saturday", "sábado", "суббота")))
check("«кого» fragment is stopped", "кого" in B._RAW_STOP)

# ---- 8. the search trigger speaks Spanish (the ES audience could not reach matching at all) ----
for _t in ("quiero encontrar a alguien para jugar al pádel", "busco gente para tomar un café",
           "busco compañero de pádel", "¿alguien se apunta a jugar?", "preséntame a alguien",
           "quiero conocer gente en Barcelona", "encuéntrame a alguien para jugar",
           "intercambio de idiomas en español"):
    check("es ask triggers a search: %s" % _t[:34], B.wants_people(_t, False) is True)
for _t in ("busco un libro sobre historia", "qué es el padel", "hola cómo estás",
           "ayer jugué al pádel con mi hermano"):
    check("es non-ask stays chat: %s" % _t[:34], B.wants_people(_t, False) is False)
# the RU/EN triggers must be untouched
check("ru ask still triggers", B.wants_people("найди мне кого-то поиграть в футбол", False) is True)
check("en ask still triggers", B.wants_people("find me someone to play football", False) is True)
check("ru chit-chat still stays chat", B.wants_people("что такое хламидиоз", False) is False)

# ---- 9. every user-facing string exists in all three languages ----
# A missing "es" row was not a cosmetic gap: these are indexed as dict[lang] on the search-result
# path, so KeyError('es') killed a Spanish search AFTER matching had already found people.
_LOCALISED = {"_FALLBACK_REPLY": B._FALLBACK_REPLY, "_CLICK": B._CLICK, "_BROADER": B._BROADER,
              "_BROADENED": B._BROADENED, "_NEEDCLAR": B._NEEDCLAR, "_ASK_ACTIVITY": B._ASK_ACTIVITY,
              "_NO_ONE": B._NO_ONE, "_FILED": B._FILED, "_NEW": B._NEW, "_GLITCH": B._GLITCH,
              "MINOR_REPLY": B.MINOR_REPLY, "HARM_REPLY": B.HARM_REPLY}
for _n, _d in _LOCALISED.items():
    check("%s covers ru/en/es" % _n, {"ru", "en", "es"} <= set(_d), str(sorted(_d)))
# the %s placeholders must match across languages, or a localised reply raises at format time
for _n, _d in _LOCALISED.items():
    if isinstance(_d.get("en"), str):
        _c = _d["en"].count("%s")
        check("%s has the same placeholders in every language" % _n,
              all(v.count("%s") == _c for v in _d.values() if isinstance(v, str)),
              str({k: v.count("%s") for k, v in _d.items() if isinstance(v, str)}))

# ---- 9b. a request that names no ACTIVITY must be a question, not a slate of strangers ----
def _bare(tops):
    return not [t for t in tops if t not in B._NO_ACTIVITY and t not in B._GENERIC_TOPIC
                and t not in B._FILLER_TOPICS]


# Real filtration output for «найди мне кого-нибудь» / "find me someone" / "busco a alguien".
# The old guard only caught the literal "social"/"other" placeholders, so once filtration started
# answering with richer wording it stopped firing and ranked the whole pool on nothing.
for _t in ([], ["social"], ["other"], ["person", "find", "someone"], ["meet people", "new friends"],
           ["person", "friend"], ["person", "search"], ["people", "company"], ["gente", "alguien"],
           # exactly what filtration returned on the pod for these two Russian asks
           ["person", "find", "someone", "meet"], ["meet people", "socialize", "friends", "network"]):
    check("vague ask -> clarify: %s" % _t, _bare(_t) is True, str(_t))
for _t in (["football", "match"], ["coffee"], ["yoga"], ["chess", "strategy"], ["padel", "racket"],
           ["coffee", "company"], ["language", "exchange"], ["labubu"], ["bachata"],
           ["startup", "founder", "networking", "business"], ["gym", "workout", "fitness"]):
    check("real ask -> search: %s" % _t, _bare(_t) is False, str(_t))

# ---- 9c. "practice" is a HOW-word: 16 people in the pool list it as their whole interest ----
check("practice is filtered as generic", "practice" in B._GENERIC_TOPIC)
check("practise too", "practise" in B._GENERIC_TOPIC)

# ---- 10. a bare "tell me more" is a follow-up, never an intent ----
# Reported twice from the app: «что такое герцы» answered well, then «а подробнее» came back as
# "О чём хочется поговорить за кофе — про кодинг, игры или просто познакомиться?".
for _t in ("а подробнее", "подробнее", "поподробнее", "детальнее", "ещё", "еще", "примеры",
           "а как", "почему", "дальше", "продолжай", "more", "tell me more", "examples",
           "why", "go on", "continue", "más", "más detalles", "ejemplos", "sigue", "por qué"):
    check("follow-up: %s" % _t, bool(B._FOLLOWUP.match(_t)) is True)
# a real ask that merely CONTAINS one of those words must still build
for _t in ("хочу поиграть в футбол", "подробнее расскажи про падел в барселоне",
           "найди мне кого-то для кофе", "more coffee places to meet people",
           "почему бы не сходить в кино вместе", "ejemplos de sitios para jugar padel",
           "ещё хочу найти напарника в теннис"):
    check("not a follow-up: %s" % _t[:34], bool(B._FOLLOWUP.match(_t)) is False)

# ---- 11. «поговорить об этом»: the ask points back, the conversation is the subject ----
# Reported from the app: a chat about hertz, then «я хочу с кем-то поговорить об этом» ->
# «О чём именно хочется поговорить?» -> «я выше писал». The builder is blind to small talk, so it
# genuinely could not see what «это» referred to.
for _t in ("я хочу с кем-то поговорить об этом", "хочу с кем-то это обсудить",
           "обсудить это с кем-нибудь", "давай про это поговорим", "это обсудить хочу",
           "я выше писал", "как я писал выше", "talk about this", "i want to discuss it",
           "sobre esto", "lo mismo", "como dije"):
    check("refers back: %s" % _t[:32], bool(B._ANAPHORA.search(_t)) is True)
for _t in ("хочу обсудить падел", "это интересно", "хочу поговорить о стартапах",
           "обсудить облигации", "i want to discuss startups", "хочу поиграть в футбол"):
    check("names its own subject: %s" % _t[:30], bool(B._ANAPHORA.search(_t)) is False)

# the referent is the last turn that actually named something — follow-ups are skipped
_thread = [U("что такое герцы", True), A("Единица частоты.", True), U("а подробнее", True),
           A("Используются в музыке.", True), U("я хочу с кем-то поговорить об этом")]
check("subject is recovered from the chat", B._subject_from_history(_thread) == "что такое герцы",
      B._subject_from_history(_thread))
check("builder sees the whole thread when the ask refers back",
      len(B._builder_msgs(_thread, keep_chat=True)) == 5, str(len(B._builder_msgs(_thread, keep_chat=True))))
check("and still hides small talk when it does not",
      len(B._builder_msgs(_thread)) == 1, str(len(B._builder_msgs(_thread))))
check("no history -> no subject, and no crash", B._subject_from_history([]) == "")

# ---- 12. the card title has to name what will actually happen ----
# From the app: a chat about hertz produced a card headed «я хочу с кем-то об этом поговорить» —
# the sentence the person typed, which names nothing.
check("discuss gets a talk suffix, not «встреча»",
      B._title_for(["hertz", "frequency", "music"], ["hertz", "разговоры"], "social", "ru", "discuss")[0]
      == "Hertz — разговор",
      B._title_for(["hertz", "frequency", "music"], ["hertz", "разговоры"], "social", "ru", "discuss")[0])
check("the subject wins over a merely-translatable later topic",
      "Музыка" not in B._title_for(["hertz", "frequency", "music"], [], "social", "ru", "discuss")[0])
check("the person's own Russian word is preferred when ours is Latin",
      B._title_for(["chlamydia"], ["хламидиоз"], "social", "ru", "discuss")[0] == "Хламидиоз — разговор",
      B._title_for(["chlamydia"], ["хламидиоз"], "social", "ru", "discuss")[0])
check("play still reads as a meetup", B._title_for(["football"], ["football"], "sport", "ru", "play")[0]
      == "Футбол — встреча", B._title_for(["football"], ["football"], "sport", "ru", "play")[0])
# the tag bag IS arbitrary order — there a scan for a translatable word is still right
check("untranslated synonym cannot win from the tag bag",
      B._title_for([], ["soccer", "football"], "sport", "ru", "play")[0] == "Футбол — встреча",
      B._title_for([], ["soccer", "football"], "sport", "ru", "play")[0])
check("all-generic topics are named once, not twice",
      B._title_for(["conversation"], ["разговоры"], "social", "ru", "discuss")[0] == "Разговор",
      B._title_for(["conversation"], ["разговоры"], "social", "ru", "discuss")[0])
check("dating is untouched", B._title_for([], [], "dating", "ru", "meet")[0] == "Свидание")
check("es discuss", B._title_for(["padel"], [], "sport", "es", "discuss")[0] == "Padel — charla",
      B._title_for(["padel"], [], "sport", "es", "discuss")[0])
check("en play", B._title_for(["padel"], [], "sport", "en", "play")[0] == "Padel meetup",
      B._title_for(["padel"], [], "sport", "en", "play")[0])

print()
if _fails:
    print("FAILED %d:" % len(_fails), ", ".join(_fails))
    sys.exit(1)
print("ALL PASS")
