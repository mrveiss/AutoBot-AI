---
type: fix
scope: backend
issue: 16580
pr: 0000
---
GET /api/collaboration/{session_id}/presence now enforces the VIEWER permission its docstring documents. It depended on get_current_user alone, so any signed-in user could list the online users of any session id, while every sibling route in the module checks a level. The handler's existing catch-all also had to learn to re-raise HTTPException: without that, the 403 would have been swallowed and re-reported as a 500, leaving the gate closed but every refusal indistinguishable from a broken endpoint.
