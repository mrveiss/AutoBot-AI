---
type: fix
scope: backend
issue: 17141
pr: 0
---
`services/approval_execution.py`'s `run_post_approval_actions` now records every way execution can fail to reach a handler's own success trail: a handler raising, an approved action naming no registered handler (a deployment defect -- the proposing module was never imported -- not a silent no-op), and a handler's own early return on a malformed context (`orphan_storage_cleanup_action.py` now raises instead of returning quietly, so the dispatcher's single recording path catches it). Each failure gets an `ApprovalComment` and an `audit_log` entry naming the action and a sanitized reason (`safe_error_reason()`, never a bare `str(exc)`, so an exception's own text can't leak a host filesystem path into the trail), then returns exactly as before -- a handler failure still can never crash or roll back the approval decision itself. The dispatcher is the sole owner of this recording, so a future action registered by anyone else inherits it without needing to remember it.
