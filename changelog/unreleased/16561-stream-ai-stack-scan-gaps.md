---
type: fix
scope: backend
issue: 16561
pr: 0000
---
`/stream-ai-stack` now returns a real 400 for a PII-blocked or hard-blocked message instead of a swallowed SSE error, scans regardless of `use_ai_stack`, and `/chats/{chat_id}/resume`'s `reason` field is scanned before reaching the graph — closing the four edge-case gaps #16545's chat-wide PII/injection scan left open.
