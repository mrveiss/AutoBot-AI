---
type: fix
scope: backend
issue: 16975
pr: 0
---
`AgentTerminalSession` gains a `tenant_id` field, captured at creation from the creating principal's JWT `org_id` claim only -- never a caller-supplied value, and never recoverable afterwards, since nothing in `chat_history`'s session/conversation model or `conversation_id` itself carries tenancy. Presence (`#16947`) now reports a session under its real tenant, falling back to `UNKNOWN_TENANT` only when it genuinely can't be determined (a pre-#16975 session, or one created via a path with no authenticated context).
