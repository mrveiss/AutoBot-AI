---
type: fix
scope: frontend
issue: 16243
pr: 16493
---
The frontend's permission checks now use the backend's own permission vocabulary and its own role-to-permission grants, both generated from the backend source instead of hand-maintained copies. A control can no longer be offered to a role the backend refuses, or hidden from one it allows. The role ranking behind `meta.minRole` is generated the same way. The `v-permission` directive, previously defined but never registered, now works.
