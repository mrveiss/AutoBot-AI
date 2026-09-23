---
type: fix
scope: backend
issue: 14981
---
`GET /api/kb-stats`'s `claim_sources` is no longer a hardcoded 65/22/13 split reported even on an empty knowledge base. Every field in the response — responses grounded, claims extracted, claims verified, claim sources, average confidence, conflicts created/resolved — is now a real counter written when a response is actually grounded or a conflict actually resolved, and `claim_sources` reports only the verification methods (`kb_lookup`, `claim_verifier_rag`) something in the pipeline actually produces today.
