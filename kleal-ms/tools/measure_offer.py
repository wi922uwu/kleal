#!/usr/bin/env python3
"""Замер: сколько разговорных ответов кончаются ГОТОВОЙ фразой и сколько — в кавычках."""
import json, re, sys, urllib.request
ФРАЗА = re.compile(r'(?iu)(Хочешь обсудить это с кем-нибудь|Want to talk this over with someone|Quieres hablarlo con alguien)')
КАВЫЧКИ = re.compile(r'[«"„][^»"“]{0,80}(обсудить|talk this over|hablarlo)[^»"“]{0,40}[»"“]')
SAYS = ['я строитель','стригу газон и крашу заборы','люблю велосипеды','вчера смотрел кино',
        'у меня кот рыжий','расскажи про Барселону','что такое опционы?','сегодня устал',
        'как думаешь, стоит учить испанский?','люблю кофе по утрам','вчера бегал в парке',
        'посоветуй сериал','у нас дома ремонт','играю на гитаре второй год','люблю горы']
msgs, канц, кав, n = [], 0, 0, 0
for s in SAYS:
    msgs.append({'role': 'user', 'content': s})
    r = urllib.request.Request('http://127.0.0.1:7075/buddy/chat',
        data=json.dumps({'messages': msgs, 'lang': 'ru', 'profile': {}}).encode(),
        headers={'Content-Type': 'application/json'})
    try:
        rep = str(json.loads(urllib.request.urlopen(r, timeout=180).read().decode()).get('reply') or '')
    except Exception as e:
        print('   сеть:', str(e)[:40]); continue
    msgs.append({'role': 'assistant', 'content': rep})
    n += 1
    if ФРАЗА.search(rep):
        канц += 1
        if КАВЫЧКИ.search(rep):
            кав += 1
        print('   ГОТОВАЯ%s «%s» -> ...%s' % (' В КАВЫЧКАХ' if КАВЫЧКИ.search(rep) else '', s[:20], rep[-56:].replace('\n', ' ')))
print()
print('разговорных ответов %d | готовой фразой %d (%.2f) | из них в кавычках %d' % (n, канц, канц / max(n, 1), кав))
