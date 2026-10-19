---
type: fix
scope: backend
issue: 18803
pr: 0000
---
Load approval comments and task links before serializing a newly created approval, so a committed request returns its HTTP 201 response instead of a lazy-load error.
