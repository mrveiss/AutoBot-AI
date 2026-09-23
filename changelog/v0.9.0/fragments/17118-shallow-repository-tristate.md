---
type: fix
scope: backend
issue: 17118
pr: 0000
---
`services.git_subprocess.is_shallow_repository` now returns a `ShallowCheck` (SHALLOW/FULL/UNKNOWN) instead of a plain bool, so a broken `repo_root` (not a git repository, a corrupted `.git`, git unavailable) can no longer read as "not shallow". Fixed the live consequence in `ensure_full_history`: it previously returned a false success ("already has full history") for an undeterminable repo_root, which `scripts/sync_deletion_planner.py`'s `ensure-full-history` CLI mode would report as exit 0. `compute_bootstrap_plan`'s shallow-clone guard now also refuses on UNKNOWN, not only on confirmed SHALLOW.
