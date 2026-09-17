---
type: fix
scope: security
issue: 15779
pr: 0000
---
A resource with owner_id=None, no resource_grants row, and a scope whose own key is also null (ORGANIZATION with company_id=None, GROUP with no group_ids, or any of USER/PRIVATE/SESSION/SHARED/WORKFLOW) was denied to every principal including an admin, with no in-app remedy: the repair itself was gated by the same check that denied it. Added a pure `is_unreachable()` predicate for detecting this orphan state, an admin-only, audited `repair_grant()` break-glass path (exposed via `POST /admin/resource-grants/repair`) that grants access without needing to touch the resource's own owner/scope columns, and made `resource_grant_store.grant()`/`revoke()` invalidate the visibility cache automatically instead of relying on every caller to remember to.
