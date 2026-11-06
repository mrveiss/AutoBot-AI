---
type: fix
scope: backend
issue: 20884
pr: 20912
---
Current Claude model IDs are written once (`ssot_claude_models`) and every default, template, hire form and doc reads them; thinking requests use the adaptive form on current models, and legacy `AUTOBOT_FALLBACK_CHAIN_*` names keep working with a deprecation warning.

Adaptive thinking is now the default for every Claude ID except the explicit pre-4.6 families (dated, Bedrock and Vertex spellings and tier aliases resolve first), and a caller-supplied `budget_tokens` thinking dict is converted for such a model; the hire form accepts earlier-generation model IDs and tier aliases by mapping them to the current ID (stored rows are not rewritten); unknown `claude-*` cost estimates use the current-generation price rows; every still-listed earlier model keeps a default fallback chain; Haiku's unstated cache-read price is recorded as unknown, not free. The model list reports a Claude model's context window from the context-window table (1M for the current generation, unknown when absent) instead of a fixed 200K, and the chat context meter no longer guesses a Claude window.
