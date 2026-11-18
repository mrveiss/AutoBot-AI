---
type: fix
scope: backend
issue: 17315
pr: 0000
---
An admin can now propose an orphan-storage deletion for human approval (POST /api/admin/orphan-storage/deletion-requests), and an approval naming an action no handler is registered for is refused when it is created rather than recorded as a failure after someone approves it.
