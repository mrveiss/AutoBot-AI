---
type: fix
scope: backend
issue: 16908
pr: 0000
---
Four `(method, path)` pairs were registered by two different modules each — FastAPI matches routes in registration order, so the second registration of each pair was dead code that read as a live endpoint. `api/admin_schedulers.py` (whose GET `/admin/schedulers` ignored operator overrides, unlike the sibling `services.scheduler_toggles`-backed implementation the frontend was already built against) is deleted entirely; `api/self_capabilities.py` is re-registered at its own documented `/self/capabilities` path instead of an empty prefix that collided with `api/chat.py`'s `/capabilities`; `api/knowledge_ai_stack.py`'s `/stats` moves to `/ai-stack/stats` (matching a path its own generated OpenAPI types already documented); and its `/search` handler — which combined multiple search sources with zero tenant filtering, unlike the surviving `api/knowledge_search.py` implementation — is deleted rather than revived at a new path. A new guard (`repo_tests/duplicate_route_registration_16908_test.py`) fails CI when two modules register the same `(method, path)` again, built on the codebase's existing `BackendEndpointScanner` rather than a new parser. Four more such collisions the scanner also found are tracked separately (#16913) and baselined in the guard pending their own resolution.
