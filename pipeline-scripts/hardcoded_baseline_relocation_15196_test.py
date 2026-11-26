# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15196 -- the path-keyed hardcoded-value baseline, both directions of a move.

Moving a baselined value INTO a file that already carries an entry for it is not free:
the count is part of the key, so the extra occurrence is a new finding (mutation a).
Moving it OUT to a new path reads as a new violation there; the report now says the
baseline records the value under another file that no longer has it (mutation b).

The fixtures come from ``detect_hardcoded_values_audit_test.py`` (a sibling file, loaded
without registering it in ``sys.modules``) so the throwaway tree is built one way.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "_hv_audit_fixtures_15196", _HERE / "detect_hardcoded_values_audit_test.py"
)
_FIXTURES = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_FIXTURES)

_MOVED_NOTE = "relocated?"


def test_a_new_occurrence_in_an_already_baselined_file_is_a_new_violation(tmp_path):
    """(a) svc.py is baselined for two; a third occurrence must fail the gate, not inherit."""
    root = _FIXTURES._repo_claiming_two(tmp_path, 3)

    result = _FIXTURES._run(root, "--report")

    assert "New violations:   1" in result.stdout, result.stdout
    assert _FIXTURES._FLEET_IP in result.stdout


def test_a_value_moved_to_a_new_path_is_reported_as_relocated_not_new(tmp_path):
    """(b) the two occurrences leave svc.py for moved.py; the report names svc.py as the origin."""
    root = _FIXTURES._repo_claiming_two(tmp_path, 0)
    (root / "autobot-backend" / "moved.py").write_text(
        "".join(f'HOST_{i} = "{_FIXTURES._FLEET_IP}"\n' for i in range(2)), encoding="utf-8"
    )

    result = _FIXTURES._run(root, "--report")

    assert "New violations:   2" in result.stdout, result.stdout
    assert result.stdout.count(_MOVED_NOTE) == 2, result.stdout
    assert "under autobot-backend/svc.py" in result.stdout


def test_a_genuinely_new_value_carries_no_relocation_note(tmp_path):
    """A value the baseline never recorded must not be excused as moved."""
    root = _FIXTURES._repo_claiming_two(tmp_path, 2)
    other_ip = ".".join(("172", "16", "168", "99"))
    (root / "autobot-backend" / "fresh.py").write_text(f'HOST = "{other_ip}"\n', encoding="utf-8")

    result = _FIXTURES._run(root, "--report")

    assert "New violations:   1" in result.stdout, result.stdout
    assert _MOVED_NOTE not in result.stdout


def test_a_still_matched_entry_is_not_offered_as_an_origin(tmp_path):
    """If svc.py still holds all it claims, a same-valued finding elsewhere did not come from it."""
    root = _FIXTURES._repo_claiming_two(tmp_path, 2)
    (root / "autobot-backend" / "added.py").write_text(f'HOST = "{_FIXTURES._FLEET_IP}"\n', encoding="utf-8")

    result = _FIXTURES._run(root, "--report")

    assert "New violations:   1" in result.stdout, result.stdout
    assert _MOVED_NOTE not in result.stdout


def test_a_scoped_audit_does_not_call_an_unscanned_files_entry_the_origin(tmp_path):
    """A scoped audit never read svc.py, so its entry looks stranded; that is not evidence of a move."""
    root = _FIXTURES._repo_claiming_two(tmp_path, 2)
    (root / "autobot-backend" / "added.py").write_text(f'HOST = "{_FIXTURES._FLEET_IP}"\n', encoding="utf-8")

    result = _FIXTURES._scoped(root, "autobot-backend/added.py")

    assert result.returncode == 1, result.stdout
    assert "not in pipeline-scripts/hardcoded_values_baseline.txt" in result.stdout
    assert _MOVED_NOTE not in result.stdout
