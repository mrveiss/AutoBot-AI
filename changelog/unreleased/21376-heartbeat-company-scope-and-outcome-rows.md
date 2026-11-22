---
type: security
scope: backend
issue: 21376
pr: 21979
---
The heartbeat routes are now scoped to the company that owns the agent: reads need membership, pause, resume, terminate, config and error writes need owner or admin of that company, a platform admin is exempt, and an agent the caller may not see (another company, unknown, or a platform agent with no company) answers 404. `paused_by_name` is shown only for a user the caller may see. Pause, resume and terminate now lock the runtime-state row, write an `attempted` audit row, change state, call the scheduler, and then write a linked `success` or `failed` row, so the trail never claims a change that did not happen. A scheduler failure is returned as a 503, and the row is restored on a best-effort basis: if a newer control has committed since (each control writes a fresh `control_id`, new nullable column), or the database fails during the restore, the row is left as it is and the `failed` row records `superseded` or `reconcile_failed`. The heartbeat panel sends the stable reason codes `manual_pause_ui` and `manual_wakeup_ui`. The panel and the budget-policy status view both render these codes through i18n, and legacy free-text reasons render unchanged.
