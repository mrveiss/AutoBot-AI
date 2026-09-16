---
type: security
scope: backend
issue: 16771
pr: 16791
---
The chat's RAG retrieval path now inspects every retrieved KB/doc chunk through the content firewall before it reaches the model prompt, and delimits it as untrusted data — closing the gap where #10552's firewall only guarded a path the chat never called.
