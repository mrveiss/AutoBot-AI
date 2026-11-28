---
type: fix
scope: slm
issue: 22262
pr: 22341
---
The fleet update provisions a node's pending vnc role before update-all-nodes.yml, so a node with an assigned vnc role that was never provisioned gets its `autobot-vnc` account before the play's account gate, instead of failing every update. A vnc role a node only detects (such as the SLM manager's own vncserver) no longer activates that gate. The infrastructure playbook route provisions first too.
