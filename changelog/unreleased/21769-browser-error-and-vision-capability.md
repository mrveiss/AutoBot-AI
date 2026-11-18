---
type: fix
scope: backend
issue: 21769
pr: 21779
---
A failed browser tool call now tells the model and the user its class, selector or URL and elapsed timeout (no internals), and the chat vision gate asks the model runtime for the model's reported capabilities, with name patterns only as the fallback (#21770).
