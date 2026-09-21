---
type: fix
scope: frontend
issue: 16919
pr: 0
---
Added `src/test/dependency-floor-reporter.ts`, the frontend twin of the backend's
`repo_tests/dependency_floor_banner.py` (#15091): a vitest reporter, local-runs-only, that
compares every package.json-declared dependency's numeric floor against what is actually
installed in `node_modules` and prints a warning (never fails) when the environment is older
than what's declared -- the gap #16919 hit directly (`vitest@4.1.9` against a declared
`^5.0.0`, `jsdom` entirely absent against a declared `^30.0.1`). This does not reinstall or
reconcile `node_modules` itself (this session does not run installs against the checkout); it
makes the drift visible the next time someone does. #16919 stays open for the actual
reinstall/reconciliation.
