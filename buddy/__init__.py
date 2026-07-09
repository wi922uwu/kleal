"""Kleal Buddy — conversational agent + orchestrator (thin v1: chat + matching).

Buddy talks to the user and, on a clear social intent, calls the `find_people` tool
(matching). Architected as a tool-dispatch loop so more tools (edit_profile, research/MCP)
plug in later. See docs/superpowers/specs/2026-07-09-buddy-api-design.md.
"""
