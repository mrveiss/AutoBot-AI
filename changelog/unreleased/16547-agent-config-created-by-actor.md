---
type: fix
scope: backend
issue: 16547
pr: 0000
---
`api/agent_config.py`'s model-update, enable and disable routes now record the actual admin (or the internal-service key) in the audit trail, instead of the literal string `"admin"`.
