# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the hardcoded-value detector's shell-script blind spot (#14316).

``detect-hardcoded-values.sh`` used to scan only ``*.py``/``*.ts``/``*.vue``,
so no shell script was ever scanned and ``autobot-infrastructure`` was not
even in its ``SCAN_DIRS``. That is how ``User=kali``, ``chown kali:kali`` and
bare ``kali ALL=(ALL) NOPASSWD:`` sudoers lines sat in
``autobot-infrastructure/shared/scripts/utilities/fix-vnc-desktop.sh``,
``fix-vnc-wsl.sh`` and ``setup/system/setup_passwordless_sudo.sh`` while the
detector reported clean.

Every test below builds a throwaway tree under ``tmp_path`` and runs a COPY
of the real script against it -- ``REPO_ROOT`` inside the script is derived
from its own location (``dirname BASH_SOURCE/..``), so copying it to
``<tmp>/pipeline-scripts/`` makes ``<tmp>`` the resolved repo root, fully
isolated from the real checkout's own violation backlog.

Fixture strings are assembled from fragments rather than written as literal
text, so this file cannot itself be mistaken for a hardcoded credential or
fleet IP by an unrelated scanner walking test sources.
"""

from __future__ import annotations

import json
import shutil
import stat
import subprocess  # nosec B404  # fixed argv, no shell
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).with_name("detect-hardcoded-values.sh")
# #14371: the entry point is thin now — the rules live in the shared library and
# the known backlog lives in the baseline, so a hermetic tree needs both. The
# real baseline is copied verbatim rather than stubbed empty: its keys name
# paths in the real checkout, so none of them match anything under tmp_path and
# the fixtures below are judged on the rules alone, while the entry point still
# exercises the same load-and-partition path CI runs.
_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib" / "hardcoded-value-rules.sh"
_BASELINE = Path(__file__).with_name("hardcoded_values_baseline.txt")
# Kept in step with SCAN_DIRS in detect-hardcoded-values.sh; the guard below
# asserts the two lists have not drifted, so a new scan directory cannot make
# every hermetic test start refusing without anyone noticing why.
_SCAN_DIRS = (
    "autobot-backend",
    "autobot-frontend/src",
    "autobot_shared",
    "autobot-slm-backend",
    "autobot-slm-frontend/src",
    "autobot-infrastructure",
)

_BAD_ACCOUNT = "ka" + "li"
_FLEET_IP = ".".join(("172", "16", "168", "77"))


def _hermetic_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    scripts_dir = root / "pipeline-scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    target = scripts_dir / "detect-hardcoded-values.sh"
    shutil.copy(_SCRIPT, target)
    target.chmod(target.stat().st_mode | stat.S_IEXEC)
    lib_dir = root / "scripts" / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(_LIB, lib_dir / "hardcoded-value-rules.sh")
    shutil.copy(_BASELINE, scripts_dir / "hardcoded_values_baseline.txt")
    # Every SCAN_DIRS entry must exist, or the script now refuses to scan a
    # partial tree (#14912 review). The fixture creates them all empty; tests
    # that care about content write into the ones they need.
    for scan_dir in _SCAN_DIRS:
        (root / scan_dir).mkdir(parents=True, exist_ok=True)
    return root


def test_a_missing_rule_library_is_fatal_not_clean(tmp_path):
    """#14371: the shared rules are a hard dependency, not a nice-to-have.

    Removing them must stop the scan, not degrade it into a run that applies no
    rules and reports a clean tree — which is what an entry point that tolerated
    a failed `source` would do, and is the failure shape every rule in the
    library exists to catch.
    """
    root = _hermetic_repo(tmp_path)
    (root / "scripts" / "lib" / "hardcoded-value-rules.sh").unlink()
    result = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["bash", str(root / "pipeline-scripts" / "detect-hardcoded-values.sh"), "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "refusing to report clean" in result.stderr


def test_a_missing_baseline_is_fatal_not_clean(tmp_path):
    """An unread exemption set and an empty one look identical to every caller."""
    root = _hermetic_repo(tmp_path)
    (root / "pipeline-scripts" / "hardcoded_values_baseline.txt").unlink()
    result = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["bash", str(root / "pipeline-scripts" / "detect-hardcoded-values.sh"), "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "baseline" in result.stderr


def _run(root: Path) -> dict:
    result = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["bash", str(root / "pipeline-scripts" / "detect-hardcoded-values.sh"), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_a_sudoers_line_in_a_shell_script_is_now_flagged(tmp_path):
    """The exact shape from #14316: a bare ``kali ALL=(ALL) NOPASSWD: ...`` line."""
    root = _hermetic_repo(tmp_path)
    infra = root / "autobot-infrastructure" / "shared" / "scripts" / "setup"
    infra.mkdir(parents=True, exist_ok=True)
    (infra / "setup_passwordless_sudo.sh").write_text(
        f"#!/bin/bash\n{_BAD_ACCOUNT} ALL=(ALL) NOPASSWD: /usr/bin/lsof\n",
        encoding="utf-8",
    )

    report = _run(root)

    assert report["other_violations"] >= 1
    assert report["status"] == "pass", "an account violation alone must not block the SSOT gate"


def test_a_systemd_user_directive_in_a_shell_script_is_now_flagged(tmp_path):
    """The ``fix-vnc-desktop.sh`` shape: ``User=kali`` inside a heredoc unit file."""
    root = _hermetic_repo(tmp_path)
    infra = root / "autobot-infrastructure" / "shared" / "scripts" / "utilities"
    infra.mkdir(parents=True, exist_ok=True)
    (infra / "fix-vnc-desktop.sh").write_text(
        "#!/bin/bash\n"
        "cat > /etc/systemd/system/tigervnc.service << EOF\n"
        f"User={_BAD_ACCOUNT}\n"
        f"Group={_BAD_ACCOUNT}\n"
        "EOF\n",
        encoding="utf-8",
    )

    report = _run(root)

    assert report["other_violations"] >= 2  # one for User=, one for Group=


def test_the_fixed_variable_form_stays_clean(tmp_path):
    """The real post-#14036 fix: ``User=${VNC_USER}`` is indirection, not a
    literal, and must not become a new false positive."""
    root = _hermetic_repo(tmp_path)
    infra = root / "autobot-infrastructure" / "shared" / "scripts" / "utilities"
    infra.mkdir(parents=True, exist_ok=True)
    (infra / "fix-vnc-desktop.sh").write_text(
        "#!/bin/bash\n"
        'VNC_USER="${AUTOBOT_VNC_USER:-autobot}"\n'
        "cat > /etc/systemd/system/tigervnc.service << EOF\n"
        "User=${VNC_USER}\n"
        "Group=${VNC_USER}\n"
        "EOF\n",
        encoding="utf-8",
    )

    report = _run(root)

    assert report["total_violations"] == 0


def test_a_hardcoded_fleet_ip_in_a_shell_script_is_now_flagged(tmp_path):
    """The IP scan has the same blind spot -- shell/ansible were never included."""
    root = _hermetic_repo(tmp_path)
    shared = root / "autobot_shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "deploy.sh").write_text(f"HOST={_FLEET_IP}\n", encoding="utf-8")

    report = _run(root)

    assert report["ssot_violations"] >= 1
    assert report["status"] == "fail", "a hardcoded fleet IP must still block the gate"


def test_a_hardcoded_fleet_ip_in_an_ansible_yaml_file_is_now_flagged(tmp_path):
    root = _hermetic_repo(tmp_path)
    ansible_dir = root / "autobot-slm-backend" / "ansible"
    ansible_dir.mkdir(parents=True, exist_ok=True)
    (ansible_dir / "inventory.yml").write_text(f"host: {_FLEET_IP}\n", encoding="utf-8")

    report = _run(root)

    assert report["ssot_violations"] >= 1


def test_an_unrelated_extension_is_still_ignored(tmp_path):
    """Scope check: the fix targets sh/yml/yaml, not every file in the tree."""
    root = _hermetic_repo(tmp_path)
    shared = root / "autobot_shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "notes.txt").write_text(f"{_BAD_ACCOUNT} ALL=(ALL) NOPASSWD: x\n{_FLEET_IP}\n", encoding="utf-8")

    report = _run(root)

    assert report["total_violations"] == 0


def test_the_real_repository_has_no_new_blocking_ssot_violations():
    """End-to-end against the real tree.

    Enabling ``*.sh``/``*.yml``/``*.yaml`` scanning must surface an
    ``other_violations`` backlog (expected, per #14316) without turning up a
    NEW ``ssot_violations`` hit -- that category blocks the CI gate
    (ssot-coverage.yml's job-status step), so a real fleet IP reachable only
    once shell/yaml scanning was enabled would silently redden every future
    PR touching an unrelated file that happens to share this workflow.
    """
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["bash", str(_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)

    assert report["ssot_violations"] == 0, (
        "a real fleet IP is now reachable through *.sh/*.yml/*.yaml scanning and must be "
        f"fixed at the source (or noqa'd if a documented example), not allow-listed: {report}"
    )


# ── #14912: --prune-baseline, and the audit message that sends you to it ─────


def _write_baseline(root, lines: list[str]) -> None:
    """Replace the baseline body, keeping its header (which carries the rules)."""
    path = root / "pipeline-scripts" / "hardcoded_values_baseline.txt"
    header = [ln for ln in path.read_text(encoding="utf-8").splitlines(keepends=True) if ln.startswith("#")]
    path.write_text("".join(header) + "".join(f"{ln}\n" for ln in lines), encoding="utf-8")


def _baseline_keys(root) -> set:
    path = root / "pipeline-scripts" / "hardcoded_values_baseline.txt"
    return {
        ln.split("|", 1)[1]
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln[:1].isdigit()
    }


def _run_flag(root, flag: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603  # fixed argv, no shell
        ["bash", str(root / "pipeline-scripts" / "detect-hardcoded-values.sh"), flag],
        capture_output=True,
        text=True,
    )


def test_prune_refuses_when_the_scan_found_nothing(tmp_path):
    """An empty scan and a broken detector are indistinguishable, and this path WRITES.

    A rules file that failed to load, or scan directories that moved, would take
    every baselined entry with it — and the no-growth guard would not object,
    because shrinking is allowed by design.
    """
    root = _hermetic_repo(tmp_path)  # no scan directories exist here
    before = (root / "pipeline-scripts" / "hardcoded_values_baseline.txt").read_bytes()
    result = _run_flag(root, "--prune-baseline")
    assert result.returncode != 0
    assert "refusing to rewrite the baseline" in result.stderr
    assert (root / "pipeline-scripts" / "hardcoded_values_baseline.txt").read_bytes() == before


def test_prune_removes_a_stranded_entry_and_the_audit_then_passes(tmp_path):
    """The recovery loop the audit message now names."""
    root = _hermetic_repo(tmp_path)
    scanned = root / "autobot-backend"
    scanned.mkdir(parents=True, exist_ok=True)
    (scanned / "svc.py").write_text(f'HOST = "{_FLEET_IP}"\n', encoding="utf-8")
    _write_baseline(
        root,
        [
            f"1|ssot|autobot-backend/svc.py|{_FLEET_IP}",
            "1|ssot|autobot-backend/gone.py|" + _FLEET_IP,
        ],
    )
    assert _run_flag(root, "--audit-baseline").returncode == 1
    assert _run_flag(root, "--prune-baseline").returncode == 0
    assert _baseline_keys(root) == {f"ssot|autobot-backend/svc.py|{_FLEET_IP}"}
    assert _run_flag(root, "--audit-baseline").returncode == 0


def test_prune_cannot_add_a_key(tmp_path):
    """The property that stops prune becoming the bypass the no-growth guard prevents."""
    root = _hermetic_repo(tmp_path)
    scanned = root / "autobot-backend"
    scanned.mkdir(parents=True, exist_ok=True)
    (scanned / "known.py").write_text(f'HOST = "{_FLEET_IP}"\n', encoding="utf-8")
    # A violation that is NOT baselined — prune must leave it a violation.
    (scanned / "brand_new.py").write_text('HOST = "' + ".".join(("172", "16", "168", "91")) + '"\n', encoding="utf-8")
    _write_baseline(root, [f"1|ssot|autobot-backend/known.py|{_FLEET_IP}"])

    assert _run_flag(root, "--prune-baseline").returncode == 0
    keys = _baseline_keys(root)
    assert not any("brand_new.py" in k for k in keys), f"prune ADDED a key: {sorted(keys)}"
    assert json.loads(_run_flag(root, "--json").stdout)["ssot_violations"] >= 1, (
        "prune silenced a finding it was never allowed to absorb"
    )


def test_prune_cannot_raise_a_count(tmp_path):
    """min(baseline, found): a key baselined at 1 and found twice stays at 1."""
    root = _hermetic_repo(tmp_path)
    scanned = root / "autobot-backend"
    scanned.mkdir(parents=True, exist_ok=True)
    (scanned / "svc.py").write_text(f'A = "{_FLEET_IP}"\nB = "{_FLEET_IP}"\n', encoding="utf-8")
    _write_baseline(root, [f"1|ssot|autobot-backend/svc.py|{_FLEET_IP}"])

    assert _run_flag(root, "--prune-baseline").returncode == 0
    body = (root / "pipeline-scripts" / "hardcoded_values_baseline.txt").read_text(encoding="utf-8")
    entry = [ln for ln in body.splitlines() if ln[:1].isdigit()]
    assert entry == [f"1|ssot|autobot-backend/svc.py|{_FLEET_IP}"], entry


def test_prune_preserves_the_header(tmp_path):
    """The header carries the rules governing the file, including 'only shrinks'."""
    root = _hermetic_repo(tmp_path)
    scanned = root / "autobot-backend"
    scanned.mkdir(parents=True, exist_ok=True)
    (scanned / "svc.py").write_text(f'HOST = "{_FLEET_IP}"\n', encoding="utf-8")
    _write_baseline(root, [f"1|ssot|autobot-backend/svc.py|{_FLEET_IP}"])
    assert _run_flag(root, "--prune-baseline").returncode == 0
    text = (root / "pipeline-scripts" / "hardcoded_values_baseline.txt").read_text(encoding="utf-8")
    assert text.startswith("#")
    assert "only ever shrinks" in text.lower() or "only ever shrink" in text.lower()


def test_the_audit_failure_names_the_recovery_command(tmp_path):
    """#14912: most of this guard's cost was discoverability, not the rule."""
    root = _hermetic_repo(tmp_path)
    (root / "autobot-backend").mkdir(parents=True, exist_ok=True)
    _write_baseline(root, [f"1|ssot|autobot-backend/gone.py|{_FLEET_IP}"])
    result = _run_flag(root, "--audit-baseline")
    assert result.returncode == 1
    assert "--prune-baseline" in result.stdout, "the failure does not say how to recover"
    assert "gone.py" in result.stdout, "the failure does not name the entries"


def test_a_noop_prune_leaves_the_file_byte_identical(tmp_path):
    """#14912 review: the PR claimed this property with no committed test.

    A no-op prune is the common case — most runs find nothing stale — so a
    regression in the sort order, the collation, or the header `awk` would
    turn every such run into a whole-file diff, and nothing would have caught
    it. Asserted on bytes, not on entry counts, because that is the claim.
    """
    root = _hermetic_repo(tmp_path)
    scanned = root / "autobot-backend"
    (scanned / "svc.py").write_text(f'A = "{_FLEET_IP}"\nB = "{_FLEET_IP}"\n', encoding="utf-8")
    _write_baseline(root, [f"2|ssot|autobot-backend/svc.py|{_FLEET_IP}"])

    baseline = root / "pipeline-scripts" / "hardcoded_values_baseline.txt"
    before = baseline.read_bytes()
    result = _run_flag(root, "--prune-baseline")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 removed" in result.stdout, result.stdout
    assert baseline.read_bytes() == before, "a no-op prune rewrote the file"


def test_a_second_noop_prune_is_also_byte_identical(tmp_path):
    """Idempotence: running it twice must not drift the file either."""
    root = _hermetic_repo(tmp_path)
    (root / "autobot-backend" / "svc.py").write_text(f'A = "{_FLEET_IP}"\n', encoding="utf-8")
    _write_baseline(root, [f"1|ssot|autobot-backend/svc.py|{_FLEET_IP}"])
    baseline = root / "pipeline-scripts" / "hardcoded_values_baseline.txt"

    assert _run_flag(root, "--prune-baseline").returncode == 0
    once = baseline.read_bytes()
    assert _run_flag(root, "--prune-baseline").returncode == 0
    assert baseline.read_bytes() == once


@pytest.mark.parametrize("missing", _SCAN_DIRS)
def test_a_missing_scan_dir_refuses_instead_of_pruning(tmp_path, missing):
    """#14912 review, HIGH: a PARTIAL scan silently gutted the baseline.

    ``hv_scan_tree`` treats a missing root as a no-op, so one moved directory
    yields nothing while the others still yield plenty. The total stays
    non-zero, the empty-scan refusal never fires, and every baseline key under
    the unreached directory is dropped by ``min(kept, 0)`` — exit 0, in the
    same voice a one-entry cleanup uses.

    Parametrized over every entry so the guard cannot cover five of six.
    """
    root = _hermetic_repo(tmp_path)
    (root / "autobot-backend" / "svc.py").write_text(f'A = "{_FLEET_IP}"\n', encoding="utf-8")
    _write_baseline(
        root,
        [
            f"1|ssot|autobot-backend/svc.py|{_FLEET_IP}",
            f"1|ssot|{missing}/deep/thing.py|{_FLEET_IP}",
        ],
    )
    baseline = root / "pipeline-scripts" / "hardcoded_values_baseline.txt"
    before = baseline.read_bytes()

    shutil.rmtree(root / missing)

    result = _run_flag(root, "--prune-baseline")
    assert result.returncode != 0, result.stdout
    assert missing in result.stderr
    assert baseline.read_bytes() == before, "the baseline was rewritten from a partial scan"


@pytest.mark.parametrize("missing", _SCAN_DIRS)
def test_a_missing_scan_dir_also_refuses_to_report_or_audit(tmp_path, missing):
    """A partial scan corrupts every mode, not just prune.

    --json under-reports the counts ssot-coverage.yml decides pass/fail from,
    and --audit-baseline calls the unreached directory's entries STALE, which
    is a false accusation that sends an author to prune away real records.
    """
    root = _hermetic_repo(tmp_path)
    shutil.rmtree(root / missing)
    for flag in ("--json", "--audit-baseline"):
        result = _run_flag(root, flag)
        assert result.returncode != 0, f"{flag} reported on a partial tree: {result.stdout}"
        assert "does not exist" in result.stderr


def test_the_tests_scan_dir_list_matches_the_script(tmp_path):
    """The fixture duplicates SCAN_DIRS; assert it has not drifted.

    A new entry in the script and not here would leave every hermetic test
    refusing, with a failure that points at the fixture rather than the cause.
    """
    text = _SCRIPT.read_text(encoding="utf-8")
    block = text.split("SCAN_DIRS=(", 1)[1].split(")", 1)[0]
    in_script = tuple(
        line.strip().strip('"')
        for line in block.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    assert in_script == _SCAN_DIRS, (
        f"SCAN_DIRS drifted — script has {in_script}, this file has {_SCAN_DIRS}"
    )
