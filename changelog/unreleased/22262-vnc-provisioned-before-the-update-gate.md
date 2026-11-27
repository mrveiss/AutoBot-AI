---
type: fix
scope: slm
issue: 22262
pr: 0000
---
The fleet update provisions a node's pending vnc role before update-all-nodes.yml, so a node that holds vnc (assigned or detected) but was never provisioned gets its `autobot-vnc` account before the play's account gate, instead of failing every update.
