---
type: fix
scope: backend
issue: 19302
---
Disabled plugins no longer receive hook calls. Unloading a plugin removes its hooks and capability grants itself, whatever the plugin's own shutdown does, and registering the same hook callback twice fires it once. Reloading a plugin now re-imports its code and reports failure when the reload did not happen. Tools a plugin registers are not yet reversed by the host.
