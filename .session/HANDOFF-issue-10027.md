# Handoff: issue-10027
status: complete
pr: #10072
base_at_push: 7ccc67096 (rebased)
gates: guards-unit=PASS(6) full-chain-DDL-parity=PASS(sha-identical) ruff=PASS migration-matrix=PASS(CI)
needs_rebase_before_merge: no
remaining: (none)
notes: |
  Shared alembic guard helpers (migrations/guards.py); refactored 002/018/022/027/030/031/032/036.
  DDL byte-identical proven via pg_dump --schema-only diff (base vs branch) = same sha, 4040 lines.
  Design: enum values literal in version scripts; NO shared registry (a migration is frozen history).
  #9980 fixed model-side, not here. SLM psycopg2 utils.py deliberately untouched (#9785).
worktree: .worktrees/issue-10027 (safe to remove after merge)
