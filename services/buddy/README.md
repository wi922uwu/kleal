# buddy-service (:7075)

The **general chatbot** — the agent the user just talks to, like they would with ChatGPT (answers
questions, riffs, recommends — not only matchmaking; deeper tools like web research come later). While
chatting it quietly notes the user's **signals** (vibe / languages / time / area / datingOk /
dealBreakers), seeded from their profile. When the user clearly wants to meet someone, the buddy calls
the **filtration** agent to categorise the request, then the **matching** agent to score — and drops the
best match into the chat.

```
user  <->  buddy :7075 (talk, LLM)  --/api/filter/categorize-->  filtration :7076
                                     --/api/agent/match--------->  matching  :7074
```

## API
| Method | Path | Body → Response |
|---|---|---|
| POST | `/api/buddy/chat` | `{messages, profile, signals}` → `{reply, signals, match}` |

`signals` is the running signal set (client holds it, passes it back each turn — server is stateless).
`match` is `null` until the buddy decides to match, then `{intent, top, candidates}`.

## Depends on
`llm-service` (conversation) · `filtration-service` (`/api/filter/categorize`, via `FILTER_URL`) ·
`matching-service` (`/api/agent/match`, via `MATCH_URL`). Falls back gracefully if the LLM is down
(canned reply + keyword-based meet-intent detection).

## Env
`BUDDY_PORT` (7075) · `V2_MODEL` (default `llama_self`) · `LLM_URL` · `FILTER_URL` (http://127.0.0.1:7076) · `MATCH_URL` (http://127.0.0.1:7074).

## Run
`BUDDY_PORT=7075 LLM_URL=http://127.0.0.1:7071 MATCH_URL=http://127.0.0.1:7074 python app.py`. stdlib only.
