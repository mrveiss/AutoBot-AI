---
type: security
scope: backend
issue: 16507
pr: 0
---
`api/knowledge_search.py`, `api/knowledge_search_aggregator.py`, `api/knowledge_suggestions.py` and `api/voice_stream.py`'s `WS /stream` now require an authenticated caller — the last four of #15745's ten originally-ungated routers, `voice_stream` now matching `api/websockets.py`'s identity-check convention instead of only checking WebSocket origin.
