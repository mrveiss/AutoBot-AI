---
type: security
scope: backend
issue: 21376
pr: 0000
---
The heartbeat routes are now scoped to the company that owns the agent: reads need membership, pause, resume, terminate, config and error writes need owner or admin of that company, a platform admin is exempt, and an agent the caller may not see (another company, unknown, or a platform agent with no company) answers 404. `paused_by_name` is shown only for a user the caller may see. Pause, resume and terminate now lock the runtime-state row, write an `attempted` audit row, change state, call the scheduler, and then write a linked `success` or `failed` row, so the trail never claims a change that did not happen and a scheduler failure restores the row and is returned as a 503. The heartbeat panel sends the stable reason codes `manual_pause_ui` and `manual_wakeup_ui` and renders them through i18n; legacy free-text reasons render unchanged.
