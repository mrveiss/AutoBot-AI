---
type: fix
scope: backend
issue: 21018
---

Demoting, deactivating or deleting the only active platform admin is now refused with 409 and the stable code `last_platform_admin` (the response `detail` is `{"code", "message"}`, so a screen can translate it). One check, `ensure_not_last_platform_admin`, is reached by `set_platform_admin`, `deactivate_user` and `delete_user` in the shared `UserService`, so `PUT /users/{id}/admin`, the deactivate and delete routes, the SLM user routes and the SCIM deprovisioning calls all use it; the SLM person-copy push, which writes `is_active` directly, calls the same check. The check locks every active-admin row (`SELECT ... FOR UPDATE`, in id order), so two concurrent changes to the last two admins cannot both succeed. A refusal is written to the identity audit log with outcome `denied`. Self-demotion is the same path: allowed only while another active admin exists. Not delivered here: the user management screens' translated message for the code.
