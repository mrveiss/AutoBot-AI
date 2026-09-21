# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The placeholder run id has one definition (#13614).

A guard over the adapters package, moved out of ``test_heartbeat_scheduler.py``:
it tests no scheduler behaviour, and that file is over its size ceiling (#14236).
"""

import pathlib


class TestThePlaceholderRunIdHasOneDefinition:
    """#13614 came from two places deriving the same id. Keep it at one."""

    def test_no_adapter_rebuilds_the_placeholder_by_hand(self):
        # Assembled from fragments so this guard does not match itself.
        banned = '= f"' + "0/{session_id}" + '"'
        adapters = pathlib.Path(__file__).resolve().parents[1] / "adapters"
        assert adapters.is_dir(), f"adapters dir not found at {adapters}"
        scanned = sorted(adapters.glob("*.py"))
        assert scanned, "scanned no adapter files — this guard would pass on an empty set"
        offenders = [p.name for p in scanned if banned in p.read_text(encoding="utf-8")]
        assert offenders == [], (
            f"{offenders} rebuild the placeholder run id by hand; import "
            "placeholder_run_id from subprocess_base so there is one definition"
        )
