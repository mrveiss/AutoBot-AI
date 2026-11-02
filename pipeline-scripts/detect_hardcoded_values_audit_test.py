# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16334 -- ``--audit-baseline`` tells an entry that matches nothing apart from
one that under-matches.

#16298 deleted ``2|other|…auth.py|"user"`` because the audit listed it under
"no longer match anything" while one occurrence was still there, which
un-baselined that occurrence. The right edit was count 1.

These tests run a COPY of the real entry point over a throwaway tree
(``REPO_ROOT`` is derived from the script's own location), as
``detect-hardcoded-values_test.py`` does. They live in their own file because
that one is at its recorded size ceiling (#14236).
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404  # fixed argv, no shell
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_FLEET_IP = ".".join(("172", "16", "168", "77"))
_KEY = f"ssot|autobot-backend/svc.py|{_FLEET_IP}"


def _scan_dirs() -> list[str]:
    """The scanned directories, taken from the definition both entry points read.

    #17329: the list moved to HV_SCAN_DIRS in scripts/lib/hardcoded-value-rules.sh
    so the repo-wide scan and the pre-commit hook could stop disagreeing about
    scope. detect-hardcoded-values.sh now spells it `SCAN_DIRS=("${HV_SCAN_DIRS[@]}")`,
    and the text parse that used to live here found exactly that literal.

    SOURCED rather than parsed, which is also why it could break: a text parse
    reads where a value is written, and the value moved. Asking bash for the
    array is the same question the script asks, so a future move cannot
    silently answer it wrong -- it fails to source instead.
    """
    lib = _HERE.parent / "scripts" / "lib" / "hardcoded-value-rules.sh"
    out = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["bash", "-c", f'source "{lib}"; printf "%s\\n" "${{HV_SCAN_DIRS[@]}}"'],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    dirs = [line for line in out.stdout.splitlines() if line]
    assert "autobot-backend" in dirs, f"HV_SCAN_DIRS resolved to {dirs!r} (stderr: {out.stderr[:200]})"
    return dirs


def _repo_claiming_two(tmp_path: Path, occurrences: int) -> Path:
    """A tree whose baseline claims the fleet IP twice in svc.py, with *occurrences* left."""
    root = tmp_path / "repo"
    for rel in ("pipeline-scripts/detect-hardcoded-values.sh", "scripts/lib/hardcoded-value-rules.sh"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(_HERE.parent / rel, root / rel)
    for scan_dir in _scan_dirs():
        (root / scan_dir).mkdir(parents=True, exist_ok=True)
    real = (_HERE / "hardcoded_values_baseline.txt").read_text(encoding="utf-8").splitlines()
    header = [line for line in real if line.startswith("#")]
    baseline = root / "pipeline-scripts" / "hardcoded_values_baseline.txt"
    baseline.write_text("\n".join([*header, f"2|{_KEY}", ""]), encoding="utf-8")
    body = "".join(f'HOST_{i} = "{_FLEET_IP}"\n' for i in range(occurrences))
    (root / "autobot-backend" / "svc.py").write_text(body, encoding="utf-8")
    return root


def _run(root: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603  # fixed argv, no shell
        ["bash", str(root / "pipeline-scripts" / "detect-hardcoded-values.sh"), *flags],
        capture_output=True,
        text=True,
    )


def _audit_line(result: subprocess.CompletedProcess) -> str:
    lines = [line for line in result.stdout.splitlines() if _KEY in line]
    assert len(lines) == 1, result.stdout + result.stderr
    return lines[0]


def test_an_under_matched_entry_shows_both_counts_and_says_lower_not_delete(tmp_path):
    result = _run(_repo_claiming_two(tmp_path, 1), "--audit-baseline")

    assert result.returncode == 1
    line = _audit_line(result)
    assert "matched 1 of 2" in line and "lower it to 1" in line, line
    assert "delete this entry" not in line
    assert "no longer match anything" not in result.stdout
    assert "match nothing" not in result.stdout


def test_a_zero_match_entry_is_still_reported_as_delete(tmp_path):
    result = _run(_repo_claiming_two(tmp_path, 0), "--audit-baseline")

    assert result.returncode == 1
    line = _audit_line(result)
    assert "matched 0 of 2" in line and "delete this entry" in line, line
    assert "1 match nothing any more:" in result.stdout


def test_a_fully_matched_entry_passes_the_audit(tmp_path):
    result = _run(_repo_claiming_two(tmp_path, 2), "--audit-baseline")

    assert result.returncode == 0, result.stdout
    assert "matches as many findings as it claims" in result.stdout


def test_the_prune_the_audit_names_lowers_an_under_matched_entry_and_keeps_it(tmp_path):
    root = _repo_claiming_two(tmp_path, 1)

    assert _run(root, "--prune-baseline").returncode == 0
    body = (root / "pipeline-scripts" / "hardcoded_values_baseline.txt").read_text(encoding="utf-8")
    assert [line for line in body.splitlines() if line[:1].isdigit()] == [f"1|{_KEY}"]
    assert _run(root, "--audit-baseline").returncode == 0


def _scoped(root: Path, *paths: str) -> subprocess.CompletedProcess:
    """A pre-push audit (#18808): only *paths* are scanned, only their entries audited."""
    listing = root / "changed.txt"
    listing.write_text("".join(f"{p}\n" for p in paths), encoding="utf-8")
    return _run(root, "--audit-baseline", f"--paths-from={listing}")


def test_a_scoped_audit_catches_the_over_claim_in_a_changed_file(tmp_path):
    result = _scoped(_repo_claiming_two(tmp_path, 1), "autobot-backend/svc.py")

    assert result.returncode == 1
    assert "matched 1 of 2" in _audit_line(result)


def test_a_scoped_audit_ignores_entries_for_files_it_did_not_scan(tmp_path):
    result = _scoped(_repo_claiming_two(tmp_path, 1), "autobot-backend/other.py")

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_scoped_audit_reports_a_deleted_files_entries_as_stale(tmp_path):
    root = _repo_claiming_two(tmp_path, 2)
    (root / "autobot-backend" / "svc.py").unlink()

    result = _scoped(root, "autobot-backend/svc.py")

    assert result.returncode == 1
    assert "matched 0 of 2" in _audit_line(result)


def test_only_the_audit_may_be_scoped(tmp_path):
    """A scoped --json would under-report the verdict; a scoped prune would delete every other entry."""
    root = _repo_claiming_two(tmp_path, 2)
    listing = root / "changed.txt"
    listing.write_text("autobot-backend/svc.py\n", encoding="utf-8")

    for flag in ("--json", "--prune-baseline"):
        result = _run(root, flag, f"--paths-from={listing}")
        assert result.returncode == 1 and "needs --audit-baseline" in result.stderr, flag


def test_a_scoped_audit_catches_a_new_value_in_a_changed_file(tmp_path):
    """#19312 review: three occurrences against a baseline of two is a NEW finding, not an over-claim."""
    result = _scoped(_repo_claiming_two(tmp_path, 3), "autobot-backend/svc.py")

    assert result.returncode == 1
    assert "not in pipeline-scripts/hardcoded_values_baseline.txt" in result.stdout
