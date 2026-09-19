---
type: fix
scope: ci
issue: 16960
pr: 0000
---
`.secrets.baseline` gains the two audit entries for `authApiKey`'s translation label (`en.json`/`ur.json`) that a prior merge landed without baselining, which was failing "Secret Detection (whole tree)" on every open PR regardless of that PR's own diff.
