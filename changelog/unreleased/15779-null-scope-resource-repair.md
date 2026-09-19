---
type: fix
scope: security
issue: 15779
pr: 16927
---
A knowledge fact or an envelope secret that no live user could reach — its owner deleted, no share or grant held by anyone still present, and a scope nobody holds — was denied to everyone, admins included, with no way to fix it inside AutoBot. Administrators can now find such resources (`GET /api/admin/orphans?resource_type=knowledge_fact|secret`) and assign a live user as the new owner (`POST /api/admin/orphans/repair`). A repair is refused unless the resource is genuinely unreachable: a resource any live user can still reach is left untouched and the request answers 409. Every attempt, successful, refused or failed, is written to the audit log with the conditions it was judged on. Repairing a secret re-wraps its key for the new owner's vault; the secret's value is never decrypted or shown. A deactivated (not deleted) user still counts as present, so their resources cannot be taken this way.
