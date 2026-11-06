# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Frozen count of in-tree log-path spellings in non-test Python (#20894).

BOUNDARY: every git-tracked `.py` file, except tests (`*_test.py`, `test_*.py`, `conftest.py`,
anything under `tests/`, `repo_tests/`). Counted, by AST (comments and docstrings cannot match):
a `getenv`/`environ.get` call whose default is the literal "logs", and a `<expr> / "logs"` whose
left side names PROJECT_ROOT, project_root, base_dir, __file__ or a `.parent`.

Frozen at the #20894 PR: 11 sites in 10 files (derived by the detector itself, then listed). The
logging manager and the backend API are at 0 -- the one resolver is autobot_shared/log_dir.py. What
is left is standalone tooling and the audit-log default, tracked in the follow-up issue. Each entry only goes DOWN.
"""

BASELINE: dict[str, int] = {
    "autobot-infrastructure/shared/scripts/apply_memory_optimizations.py": 2,
    "autobot-infrastructure/shared/scripts/backup_manager.py": 1,
    "autobot-infrastructure/shared/scripts/comprehensive_log_aggregator.py": 1,
    "autobot-infrastructure/shared/scripts/logging/log_forwarder.py": 1,
    "autobot-infrastructure/shared/scripts/monitoring/monitoring_backends.py": 1,
    "autobot-infrastructure/shared/scripts/seq_log_forwarder.py": 1,
    "autobot-infrastructure/shared/scripts/trace_backend.py": 1,
    "autobot-infrastructure/shared/scripts/utilities/init_memory_graph_redis.py": 1,
    "autobot-npu-worker/resources/windows-npu-worker/gui/main.py": 1,
    "debug/capture_output.py": 1,
}
