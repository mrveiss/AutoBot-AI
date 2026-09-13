---
type: fix
scope: chat
issue: 14840
pr: 16345
---
Context-overflow summarisation now reaches the canonical LLM service and actually runs. It had imported a module that never existed, so every overflow fell back to keeping the full history. Its temperature and token cap now reach the model as request settings.
