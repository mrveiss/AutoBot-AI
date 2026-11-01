# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20567: role manifests come from code_source, not the never-updated copy beside the install."""

from __future__ import annotations

from pathlib import Path


def test_the_default_reads_code_source() -> None:
    source = (Path(__file__).resolve().parents[2] / "services" / "manifest_loader.py").read_text(encoding="utf-8")
    assert '(_AUTOBOT_BASE / "code_source" / "autobot-infrastructure")' in source
    assert '(_AUTOBOT_BASE / "autobot-infrastructure")' not in source
