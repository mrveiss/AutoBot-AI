---
type: security
scope: tooling
issue: 16514
pr: 0
---
`check_git_toplevel_env_scrubbed.py` now classifies `scripts/test_first_remediation.py` as production code rather than a test by name — it is a real automation tool with 11 git callers `pytest.ini` never collects — and its docstring records why `sync_orchestrator.py`'s SSH-wrapped git call is outside the checker's reach by design. The reclassification surfaced two genuinely unscrubbed git subprocess calls in that file (worktree removal, branch delete), now fixed with `env=scrubbed_git_env()` so they can no longer inherit an ambient `GIT_DIR` and operate on the wrong repository.
