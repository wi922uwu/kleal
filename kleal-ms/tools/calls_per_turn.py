#!/usr/bin/env python3
"""Сколько вызовов модели стоит один ход разговора. Батарея на время замера остановлена."""
import json, re, subprocess, time, urllib.request

MET = "http://127.0.0.1:17071/metrics"
CHAT = "http://127.0.0.1:7075/buddy/chat"
PROF = {"name": "Иван", "age": 30, "area": "Barcelona", "langs": ["ru"]}


def counters():
    try:
        txt = urllib.request.urlopen(MET, timeout=20).read().decode()
    except Exception as e:
        return None, str(e)[:60]
    req = sum(float(m) for m in re.findall(r'vllm:request_success_total\{[^}]*\}\s+([0-9.e+]+)', txt))
    pt = re.search(r'vllm:prompt_tokens_total\{[^}]*\}\s+([0-9.e+]+)', txt)
    gt = re.search(r'vllm:generation_tokens_total\{[^}]*\}\s+([0-9.e+]+)', txt)
    return (req, float(pt.group(1)) if pt else 0, float(gt.group(1)) if gt else 0), None


def chat(msgs, lang="ru"):
    req = urllib.request.Request(CHAT, data=json.dumps({"messages": msgs, "lang": lang, "profile": PROF}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=200).read().decode())


print("останавливаю батарею…", flush=True)
subprocess.run(["systemctl", "stop", "kleal-battery"], check=False)
time.sleep(45)
try:
    CASES = [("простая просьба", ["хочу поиграть в настолки в субботу"]),
             ("болтовня", ["привет, как дела"]),
             ("разговор из трёх ходов", ["скучно сегодня", "может, кино", "давай"])]
    for name, says in CASES:
        before, err = counters()
        if err:
            print("метрики недоступны: %s" % err); break
        msgs = []
        for s in says:
            msgs.append({"role": "user", "content": s})
            r = chat(msgs)
            msgs.append({"role": "assistant", "content": r.get("reply") or ""})
        time.sleep(3)
        after, _ = counters()
        print("%-24s ходов %d -> вызовов модели %d (%.1f на ход), промпт %d ток., генерация %d ток."
              % (name, len(says), after[0] - before[0], (after[0] - before[0]) / len(says),
                 after[1] - before[1], after[2] - before[2]), flush=True)
finally:
    subprocess.run(["systemctl", "start", "kleal-battery"], check=False)
    print("батарея поднята", flush=True)
