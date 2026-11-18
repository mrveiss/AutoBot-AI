---
type: fix
scope: backend
issue: 20521
---

Releasing a work item now refuses with 409 when a person holds it. Before, any valid agent id in the release request cleared the checkout of an item a person had claimed. Who may act as a named agent is still open on the issue.
