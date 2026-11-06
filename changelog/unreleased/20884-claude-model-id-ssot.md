---
type: fix
scope: backend
issue: 20884
pr: 20912
---
Current Claude model IDs are written once (`ssot_claude_models`) and every default, template, hire form and doc reads them; thinking requests use the adaptive form on current models, and legacy `AUTOBOT_FALLBACK_CHAIN_*` names keep working with a deprecation warning.
