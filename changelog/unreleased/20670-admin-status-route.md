---
type: security
scope: auth
issue: 20670
pr: 0000
---
`PUT /api/user-management/users/{user_id}/admin` is now the one route that makes a user a platform admin or removes that, and it is admin-only. `is_platform_admin` is the single source of the login token's admin role; the role routes (`POST` and `DELETE /{user_id}/roles/{role_id}`, `PUT /{user_id}/role`) change permissions only and their descriptions now say so. The change voids the user's earlier tokens through the password epoch after the commit, so it applies on their next request and a demoted admin cannot keep acting on an old token; a failed revocation write is answered 503 with the change kept, as for deactivation. Each change is written to the identity audit log as `platform_admin_changed` with the before and after values. Not delivered here: a guard against removing the last admin, and the user management screens' wording.
