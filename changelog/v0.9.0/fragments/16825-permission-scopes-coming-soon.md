---
type: feat
scope: frontend
issue: 16825
pr: 0
---
Fine-grained permission scopes (a permission vocabulary, scope bundles, API-key scope
enforcement) have no backend or frontend today -- unlike the other two features #16825 named
(MCP server admin, live pricing), which already shipped complete pages, reachable via the Admin
menu since #16933. Added `AdminPermissionScopesView.vue`, an honest "coming in a later release"
panel (no fabricated version number -- #16803's v0.9.0 scope is still an open decision) with no
working form, table, or API call, so it can't be mistaken for a broken feature. Routed at
`/admin/permission-scopes`, listed in `adminMenuItems` (same `hideInNav` + admin-menu pairing
`nav-items-coverage.test.ts` enforces for every other `/admin/*` page), all strings i18n'd
across all 11 locales.
