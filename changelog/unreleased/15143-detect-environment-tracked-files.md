---
type: fix
scope: infra
issue: 15143
pr: 0000
---
`detect-environment.sh` now selects only env files this repo actually tracks, and fails loudly naming what's missing instead of silently falling through to defaults for the three modes with no unambiguous match.
