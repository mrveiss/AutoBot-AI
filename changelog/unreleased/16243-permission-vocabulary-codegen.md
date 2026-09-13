---
type: fix
scope: frontend
issue: 16243
pr: 0
---
The frontend's permission-checking vocabulary now comes from the same generated source as the backend's, instead of a hand-maintained set of strings that shared nothing with it. The `v-permission` directive, previously defined but never registered, now actually works.
