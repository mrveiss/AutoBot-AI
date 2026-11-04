# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guards that still call ``ast.parse`` directly (#20814).

Read by ``parse_cache_test.py``, which fails on a direct caller missing from
this set AND on an entry whose file no longer calls ``ast.parse``. Shrink only:
remove a path in the change that moves its file to ``tools.lint._parse_cache``.

The four left each sit at their file-size ceiling and cannot take the import
line until they are split (#20820).
"""

ALLOWED_DIRECT = frozenset(
    {
        "repo_tests/enum_union_guard_test.py",
        "repo_tests/phase_validation_paths_and_skips_17089_test.py",
        "repo_tests/router_auth_enumerator.py",
        "repo_tests/sync_deletions_ansible_wiring_16310_test.py",
    }
)
