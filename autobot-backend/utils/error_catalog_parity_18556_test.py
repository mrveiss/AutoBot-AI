# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The built-in fallback catalog must equal the one tracked YAML (#18556).

``error_catalog._BUILTIN_FALLBACK_ERRORS`` is the last resort when the YAML cannot be found. It
claims to mirror ``static/error_messages.yaml`` exactly; this makes the claim a failing test, so a
catalog edit that skips either side cannot ship.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from utils.error_catalog import _BUILTIN_FALLBACK_ERRORS, _METADATA_FIELDS

_YAML = Path(__file__).resolve().parent.parent / "static" / "error_messages.yaml"


def _flatten(raw: dict) -> dict:
    flat: dict = {}
    for key, section in raw.items():
        if key not in _METADATA_FIELDS:
            flat.update(section)
    return flat


def test_builtin_fallback_equals_the_tracked_yaml() -> None:
    flat = _flatten(yaml.safe_load(_YAML.read_text(encoding="utf-8")))
    assert len(flat) >= 40, "the YAML parsed to almost nothing; the comparison would be vacuous"
    assert set(_BUILTIN_FALLBACK_ERRORS) == set(flat), set(_BUILTIN_FALLBACK_ERRORS) ^ set(flat)
    drifted = sorted(code for code in flat if _BUILTIN_FALLBACK_ERRORS[code] != flat[code])
    assert not drifted, f"fallback differs from the YAML for {drifted}"


def test_contrast_a_drifted_entry_is_detected() -> None:
    flat = _flatten(yaml.safe_load(_YAML.read_text(encoding="utf-8")))
    code = next(iter(flat))
    changed = {**_BUILTIN_FALLBACK_ERRORS, code: {**_BUILTIN_FALLBACK_ERRORS[code], "message": "drifted"}}
    assert changed[code] != flat[code]
