# filtration-service (:7076)

The **categorisation** agent. It takes a user's free-text request/intent and "magnetises" it to one of
our existing categories — using world knowledge for novel items (`labubu` → `toys_collectibles`,
`matcha` → `food_drink`, `wordle` → `gaming`). It extracts canonical topics and maps the category to a
matching `type`, so the matching agent can score cleanly. Used by the buddy before it calls matching.

## API
| Method | Path | Body → Response |
|---|---|---|
| POST | `/api/filter/categorize` | `{text}` → `{topics, category, subcategory, type, role, isNew, note}` |
| GET | `/api/filter/categories` | → `{categories:[...]}` |

Categories: sports, gaming, esports, tabletop, music, film_tv, art_culture, books, food_drink, coffee,
nightlife, outdoors, travel, tech, startups, career, languages, wellness, fashion, toys_collectibles,
pets, photography, dating, social, other. Falls back to a keyword magnet when the LLM is down.

## Depends on
`llm-service` (via `shared/llm_client`). Holds no keys.

## Env
`FILTER_PORT` (7076) · `V2_MODEL` (default `llama_self`) · `LLM_URL`.

## Run
`FILTER_PORT=7076 LLM_URL=http://127.0.0.1:7071 python app.py`. stdlib only.
