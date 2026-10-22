# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Frozen direct Redis constructions, each with a verdict (#18553; guard: `redis_direct_constructor_18553_test`).

A RATCHET, not an allowlist: a count here is exact. A new site, or a second site in a listed file,
fails the guard; a site that leaves the tree makes its entry stale and fails until the entry is
lowered or removed; `FROZEN_TOTAL` is the sum and may only go down. Never raise it to admit a
construction -- use `autobot_shared.redis_client.get_redis_client` / `get_async_redis_client`.

The matcher and the path rules live in `tools/lint/check_no_direct_redis.py`, shared by the guard, the
`no-direct-redis` pre-commit hook and the CI step: one matcher, this one baseline.

BOUNDARY: python and shell source under the guard's `SCAN_ROOTS`, tests and `autobot_shared/redis*`
(the canonical engine) excluded. Frozen 2026-10-16 on origin/main d050455c7e; the population was
derived a second way (`git grep` over the same roots) and the file sets differ only by the four
files that merely MENTION `redis.Redis(` in a string or docstring.

Entry: ``path -> (site_count, verdict, reason)``.

EXCEPTION  stays: the canonical client cannot serve it, and the reason says why.
MIGRATE    moves to the canonical client; the text names the slice. Removing the construction
           removes the entry in the same change.
"""

from __future__ import annotations

EXCEPTION = "EXCEPTION"
MIGRATE = "MIGRATE"
VERDICTS = (EXCEPTION, MIGRATE)

_SCRIPT_A = "#18553 scripts batch A: standard named db, decode_responses=True; moves to get_redis_client"
_SCRIPT_B = (
    "#18553 scripts batch B, owner decision pending: needs decode_responses=False or a raw db-number loop, "
    "which the canonical client does not offer"
)
_SHELL = "shell-embedded python in a pre-install/deploy script; cannot import app code (#1086)"
_ANSIBLE_ROOT = "autobot-slm-backend/ansible"
_SCRIPTS = "autobot-infrastructure/shared/scripts"

BASELINE: dict[str, tuple[int, str, str]] = {
    # --- product code -------------------------------------------------------------------------
    # --- worker, infrastructure, shell --------------------------------------------------------
    "autobot-npu-worker/resources/windows-npu-worker/app/utils/redis_client.py": (
        2,
        EXCEPTION,
        "Windows NPU worker bundle cannot import autobot_shared (#5438, ARCHITECTURE_EXCEPTIONS.md)",
    ),
    f"{_ANSIBLE_ROOT}/inventory/dynamic/generate_inventory.py": (
        1,
        EXCEPTION,
        "Ansible dynamic inventory runs standalone, outside the app (#1086)",
    ),
    f"{_ANSIBLE_ROOT}/deploy-hybrid.sh": (1, EXCEPTION, _SHELL),
    f"{_ANSIBLE_ROOT}/deploy-native.sh": (1, EXCEPTION, _SHELL),
    "autobot-backend/code_analysis/install.sh": (1, EXCEPTION, _SHELL),
    # --- autobot-infrastructure/shared/scripts ------------------------------------------------
    f"{_SCRIPTS}/analysis/redis_vector_analysis.py": (2, MIGRATE, _SCRIPT_A),
    f"{_SCRIPTS}/analysis/test_data_layer_debug.py": (5, MIGRATE, _SCRIPT_A),
    f"{_SCRIPTS}/analysis/test_redis_connection.py": (1, MIGRATE, _SCRIPT_A),
    f"{_SCRIPTS}/metrics_collector.py": (1, MIGRATE, _SCRIPT_A),
    f"{_SCRIPTS}/utilities/migrate_codebase_to_chromadb.py": (1, MIGRATE, _SCRIPT_A),
    f"{_SCRIPTS}/analysis/analyze_redis_db0.py": (1, MIGRATE, _SCRIPT_B),
    f"{_SCRIPTS}/analysis/check_all_redis_dbs.py": (1, MIGRATE, _SCRIPT_B),
    f"{_SCRIPTS}/analysis/check_redis_db.py": (1, MIGRATE, _SCRIPT_B),
    f"{_SCRIPTS}/migrate_redis_databases.py": (1, MIGRATE, _SCRIPT_B),
    f"{_SCRIPTS}/utilities/init_memory_graph_redis.py": (1, MIGRATE, _SCRIPT_B),
    f"{_SCRIPTS}/migrations/migrate_category_indexes.py": (
        1,
        EXCEPTION,
        "standalone one-off migration script, decode_responses=False with explicit credentials (#1086)",
    ),
    f"{_SCRIPTS}/security/mtls-migrate.py": (
        4,
        EXCEPTION,
        "probes the plain and the TLS port during the mTLS migration; the canonical client cannot pick a port or cert",
    ),
    f"{_SCRIPTS}/validate-native-deployment.py": (
        2,
        EXCEPTION,
        "validates a deployment from outside the app and must stay independent of the code under test (#16626)",
    ),
}

#: Sum of the site counts above. It may only go DOWN.
FROZEN_TOTAL = 28
