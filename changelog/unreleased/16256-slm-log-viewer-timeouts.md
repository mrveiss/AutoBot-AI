---
type: fix
scope: slm-frontend
issue: 16256
pr: 0
---
The SLM's two service-log viewers now fetch the journal through one path (`useNodeServices.getLogs`) with one timeout: the remote-exec budget a journal read over SSH actually needs, not the API client's 30-second CRUD-read default that could abort a slow one.
