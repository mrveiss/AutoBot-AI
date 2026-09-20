---
type: feat
scope: backend
issue: 16949
pr: 0
---
Presence (`#16947`) now pushes a one-shot notice the moment a busy peer goes idle (`protocols/idle_notice.py`), instead of forcing a waiter to poll: `wait_for_idle()` resolves immediately for an already-idle target, otherwise subscribes to exactly one matching event or a bounded timeout (`AUTOBOT_IDLE_NOTICE_TIMEOUT_SECONDS`, default 300s), raising `IdleWaitExpiredError` and always unsubscribing. Built on the existing `events/bus.py` transport, not a new one.
