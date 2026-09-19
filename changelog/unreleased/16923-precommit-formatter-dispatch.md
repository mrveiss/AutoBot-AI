---
type: fix
scope: ci
issue: 16923
pr: 0000
---
`.pre-commit-config.yaml` declares black, isort, flake8, autoflake, mypy and this repo's own local guards, but the local `pre-commit` git hook slot held only the Target Branch Guard — no local hook ever ran any of them, so the first thing to catch a formatting mistake was CI, one full round-trip after every commit. `tools/git-hooks/pre-commit` now runs the branch guard first (unchanged), then dispatches to the `pre-commit` framework binary against exactly the staged files (`pre-commit run --hook-stage pre-commit --files <staged>`), correcting or refusing an unformatted commit locally instead. Skips gracefully when the `pre-commit` binary isn't installed. Covers a file created by a shell command (heredoc, generator script) exactly the same as one edited interactively, since the hook only cares that a file is staged. `github-actions[bot]`'s `auto-fix-generated-types.yml` commits inside a fresh Actions checkout that never runs `scripts/install-git-hooks.sh`, so it stays hook-less and unaffected by construction.
