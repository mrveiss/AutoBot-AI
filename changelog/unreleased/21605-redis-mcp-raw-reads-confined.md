---
type: fix
scope: backend
issue: 21605
pr: 21739
---
Non-admin Redis MCP read tools are confined to the agent namespace and cannot reach the knowledge database; admin reads of it are audited, and a guard fails on an unclassified index drop or database flush (#21383).
