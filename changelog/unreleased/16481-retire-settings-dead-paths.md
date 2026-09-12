---
type: fix
scope: frontend
issue: 16481
pr: 0
---
Removed four frontend paths into the settings API that had no real caller after the backend routes became admin-only, and stopped a live call site (chat initialization, on every page load) from uselessly calling that now admin-gated endpoint from a surface any signed-in user can reach.
