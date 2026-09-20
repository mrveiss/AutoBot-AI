---
type: feat
scope: frontend
issue: 17040
pr: 0
---
Added an SLM admin "Data hygiene" page (`views/settings/admin/DataHygieneView.vue`):
unreferenced-storage candidates from `GET /admin/orphan-storage`, selected and previewed before
proposing cleanup (never deleting directly) via `POST /approval-gates`
(`approval_type: "destructive_action"`, `context: {action: "orphan_storage_delete", provider,
candidate_id}` -- the exact contract `services/orphan_storage_cleanup_action.py` already
documents); unreachable resources from `GET /admin/orphans` repaired via the existing
`POST /admin/orphans/repair`; and an audit view over `GET /logs`. Reachable from SLM settings
navigation, admin-gated on the route. All strings go through i18n keys in `en.json` -- the SLM
frontend has no other locale files yet (#14781), so full 11-locale coverage isn't claimed here.
