#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Follow-up to ssot_config_defaults_13264_batch2_test.py (#13264): the
9-field environment/GC/Postgres/tracing/logging batch.

Each value below was re-verified against ``git show 122793bbf``'s pre-image
rather than carried over from the issue's table, the same way batch 2 was:

    os.getenv("AUTOBOT_ENV", "development")
    os.getenv("AUTOBOT_GC_THRESHOLD_0", "700")
    os.getenv("AUTOBOT_GC_THRESHOLD_1", "10")
    os.getenv("AUTOBOT_GC_THRESHOLD_2", "10")
    os.getenv("AUTOBOT_POSTGRES_DB", "autobot")
    os.getenv("AUTOBOT_POSTGRES_PORT", "5432")
    os.getenv("AUTOBOT_POSTGRES_USER", "autobot")
    os.getenv("AUTOBOT_TRACE_SAMPLE_RATE", "1.0")
    os.environ.get("LOG_LEVEL", "INFO")

Why these nine and not the other 43 still outstanding: each is one where the
shipped falsy value is not merely wrong but *inoperable*, so restoring it
cannot plausibly regress a deployment that was relying on the migrated value.

* ``gc_threshold_0 = 0`` disables automatic generational collection outright —
  CPython treats a zero gen-0 threshold as "never collect automatically", so
  nothing is collected until something calls ``gc.collect()`` by hand.
* ``postgres_port = 0`` with an empty database name and user cannot form a
  valid DSN at all.
* ``trace_sample_rate = 0.0`` samples nothing, so tracing was off by default
  while every dashboard and config page reported it as configured.
* ``log_level = ""`` and ``env = ""`` are not a level and not an environment
  name.

Deliberately excluded from this batch, both needing a decision rather than a
restoration:

* ``MiscConfig.redis_port`` (``REDIS_PORT`` -> 0). The repo already has
  ``port.redis`` (``AUTOBOT_REDIS_PORT``) correctly defaulted to 6379, and
  consumers read *that* one. Restoring 6379 here would create a second
  source of truth for the same value rather than fix one — the question is
  whether this field should exist.
* ``redis_node_id`` (``REDIS_NODE_ID`` -> ""). Its pre-#7437 default was a
  specific node identifier; shipping that as a default hardcodes one
  deployment's topology.

The remaining 43 are recorded on #13264 with their pre-migration values.

No comment lines were added to ``ssot_config.py``: its size ratchet entry is
down-only, so the rationale lives here instead.
"""

import os
from unittest.mock import patch


class TestEnvGcPostgresTracingDefaultsRestored13264:
    """#13264 batch 3: 9 more defaults the #7437 migration silently dropped."""

    def test_environment_name_is_not_empty(self) -> None:
        from autobot_shared.ssot_config import MiscConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = MiscConfig(_env_file=None)
            assert cfg.env == "development"

    def test_gc_thresholds_do_not_disable_collection(self) -> None:
        """A gen-0 threshold of 0 means CPython never collects automatically."""
        from autobot_shared.ssot_config import MiscConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = MiscConfig(_env_file=None)
            assert cfg.gc_threshold_0 == 700
            assert cfg.gc_threshold_1 == 10
            assert cfg.gc_threshold_2 == 10
            assert cfg.gc_threshold_0 > 0, "a zero gen-0 threshold disables automatic GC"

    def test_postgres_defaults_can_form_a_dsn(self) -> None:
        from autobot_shared.ssot_config import MiscConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = MiscConfig(_env_file=None)
            assert cfg.postgres_db == "autobot"
            assert cfg.postgres_port == 5432
            assert cfg.postgres_user == "autobot"
            assert all([cfg.postgres_db, cfg.postgres_port, cfg.postgres_user]), (
                "an empty name/user or a port of 0 cannot form a valid DSN"
            )

    def test_tracing_is_not_sampled_out(self) -> None:
        from autobot_shared.ssot_config import MiscConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = MiscConfig(_env_file=None)
            assert cfg.trace_sample_rate == 1.0
            assert cfg.trace_sample_rate > 0.0, "a rate of 0.0 disables tracing entirely"

    def test_log_level_is_a_level(self) -> None:
        from autobot_shared.ssot_config import MiscConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = MiscConfig(_env_file=None)
            assert cfg.log_level == "INFO"

    def test_the_environment_still_wins_over_the_restored_default(self) -> None:
        """Restoring a default must not make the field ignore its env var."""
        from autobot_shared.ssot_config import MiscConfig

        with patch.dict(
            os.environ,
            {"LOG_LEVEL": "DEBUG", "AUTOBOT_POSTGRES_PORT": "6543", "AUTOBOT_TRACE_SAMPLE_RATE": "0.25"},
            clear=True,
        ):
            cfg = MiscConfig(_env_file=None)
            assert cfg.log_level == "DEBUG"
            assert cfg.postgres_port == 6543
            assert cfg.trace_sample_rate == 0.25
