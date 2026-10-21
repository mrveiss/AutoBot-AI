---
type: fix
scope: backend
issue: 18297
pr: 18812
---
The `auto` model alias now honors `backend.llm.routing_strategy` when selecting a model for OpenAI-compatible chat completions.
