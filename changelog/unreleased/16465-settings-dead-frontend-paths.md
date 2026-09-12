---
type: fix
scope: frontend
issue: 16465
pr: 0
---
Removed five frontend paths into the settings API that had no real caller after the backend routes became admin-only, and stopped two live call sites (chat initialization, on every page load) from uselessly calling that now admin-gated endpoint from surfaces any signed-in user can reach.
