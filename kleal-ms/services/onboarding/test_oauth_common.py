#!/usr/bin/env python3
"""Общее для входов через чужой сервис: python3 services/onboarding/test_oauth_common.py

Здесь проверяется самое опасное в такой затее и одинаковое у Google и Apple: белый список адресов
возврата (без него ручка `start` — открытый перенаправитель) и одноразовость меток. Сети не нужно.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oauth_common as C          # noqa: E402

_fails = []


def check(name, ok, got=""):
    print(("  ok  " if ok else "FAIL  ") + name + ("" if ok else "  -> %s" % (got,)))
    if not ok:
        _fails.append(name)


print("-- куда можно возвращать браузер (иначе это открытый перенаправитель)")
for good in ("exp://192.168.1.5:8081/--/auth", "exps://aiopenware.com/--/auth",
             "kleal://auth", "https://aiopenware.com/done", "https://localhost:3000/x"):
    check("можно: %s" % good, C.safe_redirect(good) is True)
for bad in ("https://evil.example/steal", "http://aiopenware.com/x", "javascript:alert(1)",
            "//evil.example", "", "   ", "exp://ok/\nLocation: https://evil.example",
            "https://aiopenware.com.evil.example/x", "ftp://aiopenware.com"):
    check("нельзя: %r" % bad[:34], C.safe_redirect(bad) is False)
check("слишком длинный адрес отвергается", C.safe_redirect("kleal://" + "a" * 500) is False)

print("-- метка запроса одноразовая и протухает")
s = C.new_state("kleal://auth")
check("метка отдаёт адрес", C.take_state(s) == "kleal://auth")
check("второй раз — ничего", C.take_state(s) is None)
check("чужая метка — ничего", C.take_state("нет такой") is None)
s2 = C.new_state("kleal://auth")
C._STATES[s2]["exp"] = time.time() - 1
check("протухшая метка — ничего", C.take_state(s2) is None)

print("-- одноразовая метка вместо сессии в адресной строке")
t = C.new_ticket({"ok": True, "token": "секрет"})
check("метка отдаёт полезное", (C.take_ticket(t) or {}).get("token") == "секрет")
check("второй раз — ничего", C.take_ticket(t) is None)
t2 = C.new_ticket({"ok": True})
C._TICKETS[t2]["exp"] = time.time() - 1
check("протухшая — ничего", C.take_ticket(t2) is None)

print("-- возврат в приложение")
check("к адресу без вопроса добавляется ?",
      C.back_to_app("kleal://auth", ticket="T") == "kleal://auth?ticket=T")
check("к адресу с вопросом добавляется &",
      C.back_to_app("exps://a.com/--/auth?x=1", ticket="T") == "exps://a.com/--/auth?x=1&ticket=T")
check("пустые поля не добавляются", "error" not in C.back_to_app("kleal://auth", ticket="T", error=""))

print()
print("FAILED %d: %s" % (len(_fails), ", ".join(_fails)) if _fails else "ALL PASS")
sys.exit(1 if _fails else 0)
