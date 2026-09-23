---
type: security
scope: settings
issue: 16501
pr: 0
---
`sync_config` and `update_hardware_priority` now record the real caller (an admin session's username, or the internal-service identity) in the config-revision audit trail, instead of crediting every write to the literal `"admin"` regardless of who made it — matching the fix `api/settings_config.py`'s own routes already got under #16278.
