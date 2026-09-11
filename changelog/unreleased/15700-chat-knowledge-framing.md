---
type: fix
scope: backend
issue: 15700
pr: 16345
---
Compiling a chat into the knowledge base now screens the transcript for prompt injection, caps its length and frames it as data for the summariser. A transcript that is blocked, or has no content, is refused instead of producing an entry.
