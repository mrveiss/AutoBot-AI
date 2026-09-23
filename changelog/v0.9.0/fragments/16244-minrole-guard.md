---
type: feature
scope: frontend
issue: 16244
pr: 0
---
Routes can now declare a minimum role (`meta.minRole`) that the router guard actually enforces, ranked against the same ordering the backend uses. This is a UI-routing convenience only; the backend's own permission gates remain the real authority.
