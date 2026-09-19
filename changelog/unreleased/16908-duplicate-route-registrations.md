---
type: fix
scope: backend
issue: 16908
pr: 0
---
Four `(method, path)` pairs were registered by two different modules each — FastAPI matches routes in registration order, so the second registration of each pair was dead code that read as a live endpoint. `api/admin_schedulers.py` (whose GET `/admin/schedulers` ignored operator overrides, unlike the sibling `services.scheduler_toggles`-backed implementation the frontend was already built against) is deleted entirely; `api/self_capabilities.py` is re-registered at its own documented `/self/capabilities` path instead of an empty prefix that collided with `api/chat.py`'s `/capabilities`; `api/knowledge_ai_stack.py`'s `/stats` moves to `/ai-stack/stats` (matching a path its own generated OpenAPI types already documented); and its `/search` handler — which combined multiple search sources with zero tenant filtering, unlike the surviving `api/knowledge_search.py` implementation — is deleted rather than revived at a new path. The dedupe lands here, consolidated with #16716's KB/RAG read-visibility fix since both touched `knowledge_ai_stack.py`'s search helpers. The CI guard against a future duplicate (#16908's own AC3/AC4) is carried in a follow-up, blocked on a resolver gap discovered while wiring it up.
