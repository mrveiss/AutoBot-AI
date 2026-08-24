# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for check_baseline_no_growth.sh (#14371).

The baseline suppresses findings, so anything that can append to it can silence
the detector. `--audit-baseline` only ever checked that no entry had been
STRANDED; nothing checked that none had been ADDED, and that was a one-line
bypass of the whole gate: hardcode a value, append its key in the same change,
and the detector's correct finding is suppressed under a green check.

Every test below MUTATES a real two-commit repository and asserts the verdict.
Both directions are covered on purpose: a guard that blocks growth but also
blocks shrinkage would make the baseline unmaintainable, and removals are how a
fixed violation leaves.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD_REL = "pipeline-scripts/check_baseline_no_growth.sh"
BASELINE_REL = "pipeline-scripts/hardcoded_values_baseline.txt"
LIBS = ("scripts/lib/git-scope.sh", "scripts/lib/hardcoded-value-rules.sh")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


SETTLED_REL = "autobot-backend/settled.py"
SETTLED_VALUE = "172.16.168.99"
SETTLED_KEY = f"ssot|{SETTLED_REL}|{SETTLED_VALUE}"
MARKER = "# reviewed: #14919 vendored fixture; the value is correct where it is"


@pytest.fixture()
def repo(tmp_path: Path) -> tuple[Path, str]:
    """A two-commit repo whose base commit holds the real baseline.

    It also carries one SETTLED source file: a tracked file the change under
    test leaves alone. Without a real file in the tree there is no way to tell
    the two kinds of baseline addition apart, and every test would exercise the
    same "file is not there" refusal.
    """
    root = tmp_path / "repo"
    for rel in (GUARD_REL, BASELINE_REL, *LIBS):
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / rel, dest)
    (root / GUARD_REL).chmod(0o755)
    settled = root / SETTLED_REL
    settled.parent.mkdir(parents=True, exist_ok=True)
    settled.write_text(f'HOST = "{SETTLED_VALUE}"\n', encoding="utf-8")
    _git(root.parent, "init", "--quiet", "-b", "main", str(root))
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "--quiet", "-m", "base")
    return root, _git(root, "rev-parse", "HEAD").stdout.strip()


def _run(repo_and_base: tuple[Path, str]) -> subprocess.CompletedProcess:
    root, base = repo_and_base
    return subprocess.run(
        ["bash", str(root / GUARD_REL)],
        cwd=root,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(root), "BASE_SHA": base},
    )


def _baseline(root: Path) -> Path:
    return root / BASELINE_REL


def _first_entry_index(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if line[:1].isdigit():
            return i
    raise AssertionError("no baseline entry found — the fixture is wrong, not the guard")


def test_an_unchanged_baseline_passes(repo) -> None:
    result = _run(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no key added and no count increased" in result.stdout


def test_a_fabricated_new_key_fails(repo) -> None:
    """The bypass itself: append a key for a violation introduced in the same change."""
    root, _ = repo
    with _baseline(root).open("a", encoding="utf-8") as handle:
        handle.write("1|ssot|autobot-backend/brand_new_file.py|172.16.168.77\n")
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "NEW-KEY" in result.stdout
    assert "brand_new_file.py" in result.stdout


def test_bumping_an_existing_count_fails(repo) -> None:
    root, _ = repo
    lines = _baseline(root).read_text(encoding="utf-8").splitlines(keepends=True)
    i = _first_entry_index(lines)
    count, _, rest = lines[i].partition("|")
    lines[i] = f"{int(count) + 1}|{rest}"
    _baseline(root).write_text("".join(lines), encoding="utf-8")
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "COUNT-UP" in result.stdout


def test_removing_an_entry_passes(repo) -> None:
    """Shrinking is how a fixed violation leaves; blocking it makes the file unmaintainable."""
    root, _ = repo
    lines = _baseline(root).read_text(encoding="utf-8").splitlines(keepends=True)
    del lines[_first_entry_index(lines)]
    _baseline(root).write_text("".join(lines), encoding="utf-8")
    result = _run(repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_decreasing_a_count_passes(repo) -> None:
    root, _ = repo
    lines = _baseline(root).read_text(encoding="utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):
        count, _, rest = line.partition("|")
        if count.isdigit() and int(count) > 1:
            lines[i] = f"{int(count) - 1}|{rest}"
            break
    else:
        pytest.skip("no multi-count entry in the baseline to decrease")
    _baseline(root).write_text("".join(lines), encoding="utf-8")
    result = _run(repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_an_unparseable_baseline_fails_rather_than_skipping(repo) -> None:
    root, _ = repo
    lines = _baseline(root).read_text(encoding="utf-8").splitlines(keepends=True)
    i = _first_entry_index(lines)
    lines[i] = "notanumber|" + lines[i].partition("|")[2]
    _baseline(root).write_text("".join(lines), encoding="utf-8")
    result = _run(repo)
    assert result.returncode != 0
    assert "refusing to report clean" in (result.stdout + result.stderr)


def test_a_missing_baseline_fails_rather_than_skipping(repo) -> None:
    root, _ = repo
    _baseline(root).unlink()
    result = _run(repo)
    assert result.returncode != 0
    assert "refusing to report clean" in (result.stdout + result.stderr)


def test_an_unresolvable_base_fails_rather_than_skipping(repo) -> None:
    """'Cannot determine' must never read as 'clean' — the class this PR fixes."""
    root, _ = repo
    absent = "0" * 40
    result = subprocess.run(
        ["bash", str(root / GUARD_REL)],
        cwd=root,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(root), "BASE_SHA": absent, "HEAD_SHA": absent},
    )
    assert result.returncode != 0
    assert "cannot resolve a base commit" in (result.stdout + result.stderr)


def test_an_absent_baseline_at_base_is_the_introduction_not_a_reset(repo) -> None:
    """A baseline that does not exist at the base ref is the commit adding it.

    Not a bypass route: deleting the file to reset it makes the detector itself
    fatal on its very next run, so a delete-and-regrow lands red first.
    """
    root, _ = repo
    _git(root, "rm", "--quiet", BASELINE_REL)
    _git(root, "commit", "--quiet", "-m", "remove baseline")
    empty_base = _git(root, "rev-parse", "HEAD").stdout.strip()
    shutil.copy(REPO_ROOT / BASELINE_REL, _baseline(root))
    result = subprocess.run(
        ["bash", str(root / GUARD_REL)],
        cwd=root,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(root), "BASE_SHA": empty_base},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "does not exist at" in result.stdout


# ── the reviewed-addition route (#14919) ─────────────────────────────────────
#
# The guard used to have no route at all while its failure text told the reader
# a reviewer could take the decision deliberately. These tests pin BOTH halves
# of the route that replaced that promise: the legitimate case goes green, and
# every way of reaching it without paying its price stays red.


def _append(root: Path, *lines: str) -> None:
    with _baseline(root).open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\n")


def test_a_justified_addition_in_an_untouched_file_is_allowed(repo) -> None:
    """The legitimate case: a detection rule now matches code already in the tree.

    The file is byte-identical to the base ref, so this change did not write the
    value — and the justification naming an issue is added by this same change.
    """
    root, _ = repo
    _append(root, MARKER, f"1|{SETTLED_KEY}")
    result = _run(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"ALLOWED  {SETTLED_KEY}" in result.stdout
    assert "1 reviewed addition(s)" in result.stdout
    # Loud, not merely permitted: the addition is annotated on the run.
    assert "::warning file=" in result.stdout


def test_the_same_addition_without_a_justification_fails(repo) -> None:
    """The route is not "an untouched file"; it is "an untouched file AND a reason"."""
    root, _ = repo
    _append(root, f"1|{SETTLED_KEY}")
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"REFUSED  {SETTLED_KEY}" in result.stdout
    assert "written justification" in result.stdout


def test_a_malformed_justification_fails(repo) -> None:
    """A comment that does not name an issue is a note, not a decision."""
    root, _ = repo
    _append(root, "# reviewed: because I say so", f"1|{SETTLED_KEY}")
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "written justification" in result.stdout


def test_a_justified_addition_in_a_file_this_change_touches_fails(repo) -> None:
    """The bypass itself, wearing the marker. No route opens for it — ever.

    This is the property the whole guard exists for: hardcode a value and append
    its key in the same change. Writing a justification above the entry must not
    buy it, or the route IS the bypass.
    """
    root, _ = repo
    (root / SETTLED_REL).write_text(
        f'HOST = "{SETTLED_VALUE}"\nOTHER = "10.0.0.1"\n', encoding="utf-8"
    )
    _append(root, MARKER, f"1|{SETTLED_KEY}")
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"REFUSED  {SETTLED_KEY}" in result.stdout
    assert "is modified by this change" in result.stdout


def test_a_justified_addition_in_a_file_this_change_creates_fails(repo) -> None:
    """A brand-new file cannot hold a pre-existing finding, marker or not."""
    root, _ = repo
    fresh = root / "autobot-backend/fresh.py"
    fresh.write_text('HOST = "10.0.0.2"\n', encoding="utf-8")
    _git(root, "add", "autobot-backend/fresh.py")
    _append(root, MARKER, "1|ssot|autobot-backend/fresh.py|10.0.0.2")
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "does not exist at" in result.stdout


def test_a_justification_that_predates_the_change_cannot_be_reused(repo) -> None:
    """A marker already in the file covers its own entry, not a later append.

    Otherwise the route degrades into "land one justified entry, then append
    freely underneath it" — a permission the file grants itself.
    """
    root, _ = repo
    _append(root, MARKER)
    _git(root, "add", BASELINE_REL)
    _git(root, "commit", "--quiet", "-m", "land a justification")
    base = _git(root, "rev-parse", "HEAD").stdout.strip()
    _append(root, f"1|{SETTLED_KEY}")
    result = subprocess.run(
        ["bash", str(root / GUARD_REL)],
        cwd=root,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(root), "BASE_SHA": base},
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "already in the baseline before this change" in result.stdout


def test_a_justified_count_increase_in_an_untouched_file_is_allowed(repo) -> None:
    """COUNT-UP takes the same route as NEW-KEY; a rule can match twice in one file."""
    root, _ = repo
    lines = _baseline(root).read_text(encoding="utf-8").splitlines()
    i = _first_entry_index(lines)
    count, _, rest = lines[i].partition("|")
    entry_file = rest.split("|", 1)[1].split("|", 1)[0]
    source = root / entry_file
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("pre-existing\n", encoding="utf-8")
    _git(root, "add", entry_file)
    _git(root, "commit", "--quiet", "-m", "settle the entry's file")
    base = _git(root, "rev-parse", "HEAD").stdout.strip()
    lines[i : i + 1] = [MARKER, f"{int(count) + 1}|{rest}"]
    _baseline(root).write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = subprocess.run(
        ["bash", str(root / GUARD_REL)],
        cwd=root,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(root), "BASE_SHA": base},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COUNT-UP" in result.stdout
    assert "ALLOWED" in result.stdout


def test_a_justification_under_a_blank_line_still_counts(repo) -> None:
    """Blank lines are layout, not a break in the association."""
    root, _ = repo
    _append(root, MARKER, "", f"1|{SETTLED_KEY}")
    result = _run(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALLOWED" in result.stdout


def test_a_mix_of_one_allowed_and_one_refused_addition_fails(repo) -> None:
    """A justified addition must never launder an unjustified one in the same change."""
    root, _ = repo
    _append(root, MARKER, f"1|{SETTLED_KEY}", "1|ssot|autobot-backend/absent.py|10.0.0.3")
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ALLOWED" in result.stdout
    assert "REFUSED" in result.stdout
    assert "1 of 2 addition(s)" in result.stdout


def test_an_entry_naming_an_absent_file_says_so(repo) -> None:
    """The fabricated-key refusal has to NAME the reason, not merely exit 1.

    A guard that refuses for an unstated reason gets "fixed" by whatever the
    next person guesses — here, by inventing a path that happens to exist.
    """
    root, _ = repo
    with _baseline(root).open("a", encoding="utf-8") as handle:
        handle.write(f"{MARKER}\n1|ssot|autobot-backend/never_existed.py|10.0.0.9\n")
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "does not exist in this tree" in result.stdout


def _stub_growth(root: Path, body: str) -> None:
    """Replace the rules library with one whose growth verdict is *body*.

    The guard reads its verdict from `hv_baseline_growth`. Nothing a real
    baseline can contain makes that function emit a line the adjudication loop
    skips, so the reconciliation that catches a dropped line is only provable
    from this side of the seam.
    """
    (root / "scripts/lib/hardcoded-value-rules.sh").write_text(
        "hv_baseline_growth() {\n" + body + "\n    return 1\n}\ntrue\n",
        encoding="utf-8",
    )


def test_a_growth_line_the_parser_drops_is_fatal_not_a_pass(repo) -> None:
    """The reconciliation backstop: adjudicated must equal emitted."""
    root, _ = repo
    # The blank line has to sit BETWEEN two entries: a trailing one is stripped
    # by command substitution before the guard ever sees it.
    _stub_growth(
        root,
        f"    printf 'NEW-KEY  (+1)  {SETTLED_KEY}\\n\\nNEW-KEY  (+1)  ssot|a/b.py|x\\n'",
    )
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "adjudicated" in (result.stdout + result.stderr)
    assert "refusing to report clean" in (result.stdout + result.stderr)


def test_a_growth_verdict_with_no_entries_is_fatal_not_a_pass(repo) -> None:
    """"The baseline grew" with nothing to show for it is unreadable, not clean."""
    root, _ = repo
    _stub_growth(root, "    :")
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "emitted no entries" in (result.stdout + result.stderr)


def test_a_key_with_an_extra_separator_is_refused_not_guessed_at(repo) -> None:
    """The bypass found in review, and the reason keys are validated before use.

    `|` is a legal byte in a Linux filename and nothing in this toolchain
    rejects one. For the key

        ssot|autobot-backend/settled.py|evil_new.py|<secret>

    the naive `<class>|<file>|<value>` split yields `autobot-backend/settled.py`
    — an untouched DECOY — while the finding really belongs to the brand-new
    `autobot-backend/settled.py|evil_new.py` this change just wrote. Every other
    check then validated the decoy and the guard reported ALLOWED, exit 0, over
    exactly the addition it exists to refuse.
    """
    root, _ = repo
    evil = root / f"{SETTLED_REL}|evil_new.py"
    evil.write_text('SECRET = "AKIA-EXFIL-1234567890"\n', encoding="utf-8")
    _append(root, MARKER, f"1|ssot|{SETTLED_REL}|evil_new.py|AKIA-EXFIL-1234567890")
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "not 2" in result.stdout
    assert "ALLOWED" not in result.stdout


def test_the_decoy_file_is_never_the_one_validated(repo) -> None:
    """The same key, with the decoy MODIFIED too — the refusal must not depend on it.

    If the ambiguity check were removed and the guard fell back to validating
    the decoy, this case would still be refused (the decoy changed) and would
    hide the bug. Asserting the *reason* is what makes the test bite.
    """
    root, _ = repo
    (root / SETTLED_REL).write_text('HOST = "x"\n', encoding="utf-8")
    (root / f"{SETTLED_REL}|evil_new.py").write_text('S = "v"\n', encoding="utf-8")
    _append(root, MARKER, f"1|ssot|{SETTLED_REL}|evil_new.py|v")
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "not 2" in result.stdout


def test_an_empty_file_field_is_refused(repo) -> None:
    root, _ = repo
    _append(root, MARKER, "1|ssot||somevalue")
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "file field is empty" in result.stdout


def test_an_entry_naming_a_symlink_is_refused(repo) -> None:
    """A symlink's blob is the target PATH, so 'unchanged' says nothing about content.

    Found in review, and reproduced before the check existed: base carries
    `alias.py -> settled.py`; the change rewrites `settled.py` to add a value
    and baselines `alias.py`. `git diff --quiet` is silent on the link object,
    so the byte-identical test passed on the wrong file and the guard exited 0.
    """
    root, _ = repo
    alias = root / "autobot-backend/alias.py"
    alias.symlink_to("settled.py")
    _git(root, "add", "autobot-backend/alias.py")
    _git(root, "commit", "--quiet", "-m", "add the symlink at base")
    base = _git(root, "rev-parse", "HEAD").stdout.strip()
    (root / SETTLED_REL).write_text('HOST = "10.0.0.7"\n', encoding="utf-8")
    _append(root, MARKER, "1|ssot|autobot-backend/alias.py|10.0.0.7")
    result = subprocess.run(
        ["bash", str(root / GUARD_REL)],
        cwd=root,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(root), "BASE_SHA": base},
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "is a symlink" in result.stdout
    assert "ALLOWED" not in result.stdout
