# buddy-service (:7075)

The **conversational** agent — the one the user just talks to. It chats naturally, quietly accumulates
the user's **signals** (topics / role / type / vibe / languages / time / area / datingOk / dealBreakers),
seeded from their profile and refined through the conversation. When the user clearly wants to meet
someone, the buddy **calls the matching agent** (agent-to-agent, over HTTP) with the assembled signals
and surfaces the best match in the chat.

```
user  <->  buddy :7075 (talk, LLM)  --HTTP /api/agent/match-->  matching :7074 (rank)
```

## API
| Method | Path | Body → Response |
|---|---|---|
| POST | `/api/buddy/chat` | `{messages, profile, signals}` → `{reply, signals, match}` |

`signals` is the running signal set (client holds it, passes it back each turn — server is stateless).
`match` is `null` until the buddy decides to match, then `{intent, top, candidates}`.

## Depends on
`llm-service` (conversation, via `shared/llm_client`) · `matching-service` (`/api/agent/match`, via `MATCH_URL`).
Falls back gracefully if the LLM is down (canned reply + keyword-based meet-intent detection).

## Env
`BUDDY_PORT` (7075) · `V2_MODEL` (default `llama_self`) · `LLM_URL` · `MATCH_URL` (http://127.0.0.1:7074).

## Run
`BUDDY_PORT=7075 LLM_URL=http://127.0.0.1:7071 MATCH_URL=http://127.0.0.1:7074 python app.py`. stdlib only.
