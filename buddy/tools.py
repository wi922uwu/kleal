"""Buddy tool registry. v1: one tool, `find_people`.

Adding a capability later (edit_profile, research via MCP) = add a schema + executor here.
"""
from . import matching

# OpenAI-style function schema (used directly in native tool_mode; described in the prompt
# in prompt tool_mode).
FIND_PEOPLE_TOOL = {
    "type": "function",
    "function": {
        "name": "find_people",
        "description": (
            "Find people or plans that match the user's social intent. Call ONLY when the "
            "user clearly wants to find someone or put together a plan (e.g. a Dota teammate, "
            "coffee tonight, Spanish practice, watch the match). NEVER call for general chit-chat."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string",
                             "enum": [c for c in matching.CATEGORIES if c != "dating"]},
                "activity": {"type": "string", "description": "e.g. 'dota teammate', 'watch football'"},
                "tags": {"type": "array", "items": {"type": "string"},
                         "description": "topic/entity tags: 'dota 2', 'FC Barcelona', 'spanish'"},
                "mode": {"type": "string", "enum": ["online", "offline", "hybrid"]},
                "format": {"type": "string",
                           "enum": ["one_on_one", "small_group", "open_group", "online_room", "game_lobby"]},
                "time": {"type": "string", "description": "'now', 'today evening', 'weekend'"},
                "languages": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string"},
            },
            "required": ["category"],
        },
    },
}


def run_find_people(user_id, args, store, limit=4):
    """Execute the tool: normalize intent, persist it, return matches."""
    intent = matching.normalize_intent(args if isinstance(args, dict) else {})
    store.set_active_intent(user_id, intent)
    matches = matching.find_candidates(intent, user_id, store, limit)
    return {"intent": intent, "matches": matches}
