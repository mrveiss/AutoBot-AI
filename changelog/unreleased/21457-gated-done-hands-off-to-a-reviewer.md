---
type: fix
scope: backend
issue: 21457
---

When a review gate stops an agent from finishing a work item, the item is now handed to the named reviewer with the arguments the handoff service declares; the call used to pass the company id as the agent and an undeclared keyword, so it would have raised `TypeError`. A gated finish with no reviewer is refused as an invalid transition instead of completing past the gate. No route reaches this path yet; wiring it is tracked separately.
