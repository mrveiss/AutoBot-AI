---
type: fix
scope: frontend
issue: 21357
pr: 0000
---
A chat response stream (and a resumed approval or stall-question stream) now writes to the chat it was started in. Switching to another chat mid-stream no longer appends the remaining chunks to that chat or leaves the original reply truncated; the typing indicator and pending-approval flag stay with the chat that owns them, and returning to a still-streaming chat shows its indicator again.
