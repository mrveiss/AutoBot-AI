---
type: security
scope: backend
issue: 16595
pr: 0000
---
`ExternalSkillImporter.import_http_catalog` now fetches skill catalogs through the shared `fetch_safe_url` guard instead of a hand-rolled scheme/hostname/IP-pin sequence, closing CodeQL alert 1030 (`py/full-ssrf`) at its root: the hand-rolled guard was split across function boundaries, which CodeQL's `py/full-ssrf` query cannot follow, so it kept flagging (and re-flagging on unrelated PRs) a sink `fetch_safe_url`'s own two call sites are never flagged on. Also closes a gap the old guard had: `pinned_connector` alone never validated the URL scheme.
