---
type: fix
scope: infrastructure
issue: 16348
pr: 0000
---
`generate_service_keys.py` wrote its plaintext live-key export to a path relative to the process's working directory, so a manual run from inside a checkout dropped keys into the work tree (the mechanism behind #16301's exposure). The export directory now comes from an explicit `--output-dir` or SSOT's configured install root, the script refuses to write inside any git work tree, `rotate-service-keys.yml` no longer hard-codes `/opt/autobot`, and a rotation now keeps only the newest export instead of accumulating every plaintext copy.
