---
type: security
scope: backend
issue: 16771
pr: 0000
---
The chat's own RAG retrieval path (`ChatKnowledgeService.conversation_aware_retrieve`) never passed retrieved KB/doc text through the content firewall introduced by #10552 — that guard only covered `advanced_rag_optimizer.get_optimized_context`, a path the chat doesn't use. Retrieved text reached the model prompt un-inspected and un-delimited. Added `security.content_firewall.inspect_rag_context`, one shared inspection point both RAG paths now call: a blocked verdict drops the context and its citations rather than answering from poisoned context, and a passing verdict is delimited as untrusted DATA before it reaches the prompt.
