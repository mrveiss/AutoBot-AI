---
type: fix
scope: security
issue: 16566
pr: 0
---
The frontend role's TLS key-permission task set the node's shared TLS private key to mode `0644` root:root — world-readable to every local user and process. It is now `0640 root:frontend_group`, the one group that needs it (nginx runs as root; the frontend service reads the key directly as a non-root service user), matching the tighter `0600` the backend role and the shared generator already use. A guard test fails on any ansible task giving a TLS key path a world- or group-readable mode without a recorded reason, and the same fix is wired into the builtin updater (`update-all-nodes.yml`), not just full provisioning.
