---
type: fix
scope: ci
issue: 16353
pr: 0000
---
`.secrets.baseline` no longer stores a `line_number` per finding, so a PR that only shifts lines in a file with existing findings commits no baseline change and can no longer conflict with another such PR; detect-secrets' own finding identity is `(filename, secret_hash, type)`, unaffected by the strip.
