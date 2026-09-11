---
type: fix
scope: backend
issue: 15700
pr: 16345
---
Compiling a chat into the knowledge base now frames the transcript as data for the summariser and caps its length, keeping code intact. A chat that carries an instruction to an AI model, or has no content, is refused with a reason (HTTP 422) instead of producing an entry.
