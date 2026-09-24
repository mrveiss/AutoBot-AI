# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The provenance marker must not outlive the installation it describes (#17332).

`venv_provenance.py` writes `AUTOBOT_PROVENANCE` inside a distribution's own
`dist-info` directory, and its design rests on one claim: a reinstall replaces
that directory and erases the marker. pip removes the paths its `RECORD` lists
and then the directory if nothing is left -- so an unrecorded extra file keeps
the directory alive. The marker was unrecorded. Every upgrade of a stamped
package therefore left a `dist-info` holding one file, Python reported a second
distribution for that name at version `None`, and the next pip run that had to
uninstall it aborted:

    error: uninstall-no-record-file
    x Cannot uninstall cachetools None
    '-> The package's contents are unknown: no RECORD file was found

Thirteen distributions across two venvs on one host were in that state, found
during a provisioning failure. pip stops at the first, so each failed deploy
revealed one. Counted as twelve at first, from `autobot-backend/venv` alone --
a one-venv measurement reported as "on one host". The thirteenth is
`psycopg2_binary` in `autobot-slm-backend/venv`.

How the uninstall is modelled here: `_uninstall_like_pip` deletes exactly the
paths `RECORD` names and then removes the directory if it is empty. That is
pip's own behaviour, read from its source rather than assumed --
`req_uninstall.uninstallation_paths` yields `dist.iter_declared_entries()`,
i.e. the RECORD entries and nothing else, and raises `UninstallMissingRecord`
(`exceptions.py`, reference `uninstall-no-record-file`) when RECORD is absent.

`test_the_old_unrecorded_marker_reproduces_the_husk` exists to keep that model
honest: it asserts the simulation DOES produce a husk when the marker is not
recorded. Without it, the passing tests below would be equally consistent with
a simulation that never removes anything.
"""

from __future__ import annotations

import builtins
import contextlib
import importlib.util
import os
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PROVENANCE_SRC = _BACKEND_ROOT / "venv_provenance.py"


def _load_provenance():
    spec = importlib.util.spec_from_file_location("_venv_provenance_17332", _PROVENANCE_SRC)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


prov = _load_provenance()


def _install(site_packages: Path, name: str, version: str) -> Path:
    """A distribution as an installer leaves it: files plus a RECORD naming them."""
    dist_info = site_packages / f"{name}-{version}.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(f"Name: {name}\nVersion: {version}\n", encoding="utf-8")
    (dist_info / "INSTALLER").write_text("pip\n", encoding="utf-8")
    entries = [f"{dist_info.name}/METADATA", f"{dist_info.name}/INSTALLER", f"{dist_info.name}/RECORD"]
    (dist_info / "RECORD").write_text("".join(f"{e},,\n" for e in entries), encoding="utf-8")
    return dist_info


def _uninstall_like_pip(site_packages: Path, dist_info: Path) -> None:
    """Delete what RECORD names; drop the directory only if nothing is left."""
    record = dist_info / "RECORD"
    entries = [line.split(",", 1)[0] for line in record.read_text(encoding="utf-8").splitlines() if line]
    for entry in entries:
        target = site_packages / entry
        if target.is_file():
            target.unlink()
    if dist_info.is_dir() and not any(dist_info.iterdir()):
        dist_info.rmdir()


@pytest.fixture()
def site_packages(tmp_path: Path) -> Path:
    path = tmp_path / "venv" / "lib" / "python3.14" / "site-packages"
    path.mkdir(parents=True)
    return path


@contextlib.contextmanager
def _record_update_refused():
    """Refuse the RECORD update at the seam where it actually happens.

    These tests used to patch `Path.write_text` filtered on a file named
    RECORD. #17371 made the update atomic -- it writes
    `RECORD.autobot-provenance-tmp` through builtin `open` and `os.replace`s it
    into place -- so that patch stopped firing. One test failed loudly. The
    other went on passing while reproducing nothing at all, which is the
    dangerous half: a test that no longer injects the fault it names still
    reports green, and its green is indistinguishable from a working fix.

    Two defences against a repeat. The suffix comes from the module under test
    (`prov.RECORD_TMP_SUFFIX`) rather than being spelled here, and the injector
    asserts on exit that it actually fired -- so if the write moves again this
    fails instead of quietly passing.

    What it models: with an atomic replace, a read-only RECORD *file* is no
    longer the failure case (the replace only needs the directory). "RECORD
    cannot be updated" now means a dist-info directory this process cannot
    write into.
    """
    real_open = builtins.open
    fired = {"count": 0}

    def refuse_temp(file, *args, **kwargs):
        if str(file).endswith(prov.RECORD_TMP_SUFFIX):
            fired["count"] += 1
            raise PermissionError(13, "Permission denied")
        return real_open(file, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(builtins, "open", refuse_temp)
        yield

    assert fired["count"] > 0, (
        "the fault was never injected -- the RECORD write has moved again and this test "
        "is asserting against an ordinary successful stamp"
    )


def test_the_old_unrecorded_marker_reproduces_the_husk(site_packages: Path) -> None:
    """The contrast case: without this, the fix's tests prove nothing.

    Writes the marker the way the module used to -- file only, no RECORD entry
    -- and asserts the modelled uninstall leaves exactly the husk seen in
    production.
    """
    dist_info = _install(site_packages, "cachetools", "7.1.8")
    (dist_info / prov.PROVENANCE_MARKER_FILENAME).write_text("{}\n", encoding="utf-8")

    _uninstall_like_pip(site_packages, dist_info)

    assert dist_info.is_dir(), "the unrecorded marker should have kept the directory alive"
    assert [entry.name for entry in dist_info.iterdir()] == [prov.PROVENANCE_MARKER_FILENAME]
    assert prov.is_provenance_husk(dist_info)


def test_a_stamped_install_leaves_no_husk_when_it_is_upgraded(site_packages: Path) -> None:
    """The sequence that produced #17332: install, stamp, upgrade."""
    dist_info = _install(site_packages, "cachetools", "7.1.8")
    prov.write_provenance_marker(dist_info, "autobot-backend")

    _uninstall_like_pip(site_packages, dist_info)

    assert not dist_info.exists(), (
        "the marker must be removed with the distribution, or the directory "
        "survives as a husk that blocks every later pip run"
    )


def test_the_marker_is_listed_in_record(site_packages: Path) -> None:
    dist_info = _install(site_packages, "pypdf", "6.18.1")

    prov.write_provenance_marker(dist_info, "autobot-backend")

    entries = [
        line.split(",", 1)[0] for line in (dist_info / "RECORD").read_text(encoding="utf-8").splitlines() if line
    ]
    assert f"{dist_info.name}/{prov.PROVENANCE_MARKER_FILENAME}" in entries


def test_re_stamping_does_not_duplicate_the_record_entry(site_packages: Path) -> None:
    """The reconciler re-stamps every declared package on every run."""
    dist_info = _install(site_packages, "pypdf", "6.18.1")

    for _ in range(3):
        prov.write_provenance_marker(dist_info, "autobot-backend")

    body = (dist_info / "RECORD").read_text(encoding="utf-8")
    assert body.count(prov.PROVENANCE_MARKER_FILENAME) == 1


def test_a_distribution_without_a_record_is_left_unstamped(site_packages: Path) -> None:
    """#17357 reverses the answer this test used to assert, so the reasoning lives here.

    It read: "Best-effort: a missing RECORD must not make the stamp itself
    fail" -- true about the stamp, wrong about the outcome. With no RECORD to
    list it in, the marker IS the unrecorded extra file of #17332. Stamping
    anyway seeds the husk this module exists to prevent, one package at a time,
    from the repair itself.

    Unstamped is not a failure state. `has_tool_provenance` returns False, the
    package reads as unverified, and removing it then needs the operator opt-in
    (`AUTOBOT_VENV_RECONCILE_ALLOW_UNVERIFIED_REMOVAL`). That is a state this
    module already knows how to handle; a husk is one that breaks pip for every
    package after it. The trade is provenance for one package against pip for
    the whole venv.
    """
    dist_info = site_packages / "odd-1.0.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text("Name: odd\n", encoding="utf-8")

    prov.write_provenance_marker(dist_info, "autobot-backend")

    assert not (dist_info / prov.PROVENANCE_MARKER_FILENAME).exists(), (
        "a marker no RECORD lists is a husk seed, not provenance -- it survives the "
        "next uninstall and keeps the dist-info alive (#17332)"
    )
    assert not prov.has_tool_provenance(dist_info), "and the package must read as unverified instead"


def test_a_record_that_cannot_be_written_leaves_no_marker(site_packages: Path) -> None:
    """The path with no coverage before #17357: RECORD present, but unwritable.

    #17338's `except OSError` wrapped BOTH the marker write and the RECORD
    append, so a failure in the second arrived with the marker already on disk
    and was logged as "could not write marker" -- a message describing the
    write that actually succeeded. Absent-RECORD and unwritable-RECORD reach
    the same end state by different routes, and only the first had a test.

    Monkeypatched rather than chmod-ed: as root the permission bits do not
    refuse the write, so a chmod test would pass by not reproducing anything --
    the same way this test itself silently stopped reproducing anything when
    #17371 moved the write. See `_record_update_refused`.
    """
    dist_info = _install(site_packages, "pypdf", "6.18.1")

    with _record_update_refused():
        prov.write_provenance_marker(dist_info, "autobot-backend")

    assert not (dist_info / prov.PROVENANCE_MARKER_FILENAME).exists(), (
        "the marker write succeeded and only the RECORD append failed -- the marker "
        "must not be left behind unrecorded"
    )
    assert not prov.has_tool_provenance(dist_info)


def test_an_unrecordable_stamp_does_not_leave_a_husk(site_packages: Path) -> None:
    """The payoff, run through the #17332 sequence that produced the outage.

    The two tests above assert the marker is absent. This one asserts what that
    absence BUYS, which is the only reason to want it: the dist-info goes away
    with its own uninstall instead of surviving as debris. Without this, "no
    marker" is just a missing file, and nothing distinguishes the fix from
    stamping having quietly stopped working everywhere.
    """
    dist_info = _install(site_packages, "cachetools", "7.1.8")

    with _record_update_refused():
        prov.write_provenance_marker(dist_info, "autobot-backend")

    _uninstall_like_pip(site_packages, dist_info)

    assert not dist_info.exists(), (
        "an unrecordable stamp must not cost the package its uninstall -- this is the "
        "husk of #17332, reintroduced by the code written to repair it"
    )


def test_clearing_removes_every_husk_in_one_pass(site_packages: Path) -> None:
    """pip stops at the first, so one failed deploy per husk is the alternative."""
    names = []
    for name, version in (("cachetools", "7.1.8"), ("pypdf", "6.18.1"), ("boto3", "1.43.93")):
        dist_info = _install(site_packages, name, version)
        (dist_info / prov.PROVENANCE_MARKER_FILENAME).write_text("{}\n", encoding="utf-8")
        _uninstall_like_pip(site_packages, dist_info)
        names.append(dist_info.name)
    steps: list[str] = []

    removed = prov.clear_provenance_husks(site_packages, steps)

    assert sorted(removed) == sorted(names)
    assert list(site_packages.iterdir()) == []
    assert steps and "3 husk" in steps[0]


def test_a_real_installation_is_never_cleared(site_packages: Path) -> None:
    """The remedy is a deletion, so its reach is the thing to pin down."""
    dist_info = _install(site_packages, "cachetools", "7.2.0")
    prov.write_provenance_marker(dist_info, "autobot-backend")

    assert prov.clear_provenance_husks(site_packages) == []
    assert (dist_info / "METADATA").is_file()


def test_a_directory_holding_anything_else_is_left_alone(site_packages: Path) -> None:
    """Not ours to classify: only a lone marker proves this module wrote it."""
    dist_info = site_packages / "mystery-1.0.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / prov.PROVENANCE_MARKER_FILENAME).write_text("{}\n", encoding="utf-8")
    (dist_info / "SOMETHING_ELSE").write_text("x\n", encoding="utf-8")

    assert prov.is_provenance_husk(dist_info) is False
    assert prov.clear_provenance_husks(site_packages) == []
    assert dist_info.is_dir()


def test_has_tool_provenance_is_false_for_a_husk(site_packages: Path) -> None:
    """A husk would otherwise authorise a removal with the debris of an earlier one."""
    dist_info = _install(site_packages, "cachetools", "7.1.8")
    (dist_info / prov.PROVENANCE_MARKER_FILENAME).write_text("{}\n", encoding="utf-8")
    _uninstall_like_pip(site_packages, dist_info)

    assert prov.has_tool_provenance(dist_info) is False


def test_site_packages_are_found_by_glob_not_by_version(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    (venv / "lib" / "python3.99" / "site-packages").mkdir(parents=True)

    found = prov.site_packages_dirs(venv)

    assert [p.parent.name for p in found] == ["python3.99"]


# ---------------------------------------------------------------------------
# The deletion must not reach out of the directory it is clearing (#17362)
# ---------------------------------------------------------------------------


def test_a_symlinked_dist_info_is_not_a_husk(site_packages: Path, tmp_path: Path) -> None:
    """`is_dir` and `iterdir` follow links, so the predicate could be aimed outside.

    A `*.dist-info` symlink whose target directory holds one file named
    `AUTOBOT_PROVENANCE` matched every clause of the husk test, and the removal
    then reached THROUGH the link and unlinked that file in the target -- a
    directory that need not be inside `site-packages` at all. The predicate's
    docstring promises it "cannot reach a real installation, an operator's
    files, or another tool's"; through a link it could.

    Theoretical when written, and it stays theoretical: nothing here creates
    such a link. What changed is the blast radius -- #17339 runs this as root,
    unconditionally, on every provisioned host, in three venvs. The assertion
    that matters is the last one: the file in the TARGET survives.
    """
    outside = tmp_path / "not-site-packages"
    outside.mkdir()
    bystander = outside / prov.PROVENANCE_MARKER_FILENAME
    bystander.write_text("{}\n", encoding="utf-8")

    link = site_packages / "borrowed-1.0.dist-info"
    link.symlink_to(outside, target_is_directory=True)

    assert not prov.is_provenance_husk(link), "a symlink is not a husk, whatever it points at"
    assert prov.clear_provenance_husks(site_packages) == []
    assert (
        bystander.is_file()
    ), "the husk clearer deleted a file through a symlink, outside the directory it was clearing"
    assert link.is_symlink(), "and the link itself is left alone rather than half-removed"


def test_the_marker_unlink_refuses_a_directory_that_is_a_link(tmp_path: Path) -> None:
    """The removal enforces it too, not only the predicate that gates it.

    Defence in depth against a link planted between the check and the
    deletion: `_unlink_marker_within` opens with `O_NOFOLLOW | O_DIRECTORY`, so
    it raises rather than acting through a link that `is_provenance_husk`
    never saw.
    """
    real = tmp_path / "real"
    real.mkdir()
    (real / prov.PROVENANCE_MARKER_FILENAME).write_text("{}\n", encoding="utf-8")
    link = tmp_path / "link-1.0.dist-info"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(OSError):
        prov._unlink_marker_within(link)

    assert (real / prov.PROVENANCE_MARKER_FILENAME).is_file()


# ---------------------------------------------------------------------------
# RECORD is a manifest, and a half-written one is worse than a husk (#17371)
# ---------------------------------------------------------------------------


def test_an_interrupted_record_rewrite_leaves_the_original_intact(site_packages: Path) -> None:
    """The atomicity claim, proved rather than asserted.

    A happy-path content check cannot tell an atomic write from a truncating
    one -- both end with the right bytes -- so this fails the replace after the
    temp file is written and asserts the ORIGINAL is still complete. Against
    the old `Path.write_text`, which opens with `"w"`, the manifest would
    already have been truncated before this point.

    RECORD is what pip uses to know what a package owns. A husk is annoying and
    locally repairable; a truncated manifest breaks pip's management of a
    package that was working fine, picked by whatever happened to be mid-write.
    """
    dist_info = _install(site_packages, "pypdf", "6.18.1")
    record = dist_info / "RECORD"
    before = record.read_text(encoding="utf-8")

    def no_space(src: object, dst: object) -> None:
        raise OSError(28, "No space left on device")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(os, "replace", no_space)
        prov.write_provenance_marker(dist_info, "autobot-backend")

    assert record.read_text(encoding="utf-8") == before, "the manifest was damaged by a failed stamp"
    assert [
        entry.name for entry in dist_info.iterdir() if entry.name.startswith("RECORD.")
    ] == [], "a failed replace left temp litter beside the manifest -- a husk in a different costume"
    assert not (
        dist_info / prov.PROVENANCE_MARKER_FILENAME
    ).exists(), "and the unrecordable marker is still taken back (#17357)"


def test_the_record_keeps_its_mode_across_the_replace(site_packages: Path) -> None:
    """`os.replace` installs the TEMP file's mode, not the target's.

    Since #17339 this runs as root on every provisioned host, which is exactly
    where the temp file's identity differs from the manifest's. A RECORD that
    comes back `0600` or root-owned breaks pip for the venv's own user -- the
    failure this whole module exists to prevent, arriving by another route.
    """
    dist_info = _install(site_packages, "pypdf", "6.18.1")
    record = dist_info / "RECORD"
    record.chmod(0o640)

    prov.write_provenance_marker(dist_info, "autobot-backend")

    assert record.stat().st_mode & 0o777 == 0o640
    assert prov.PROVENANCE_MARKER_FILENAME in record.read_text(
        encoding="utf-8"
    ), "premise: the replace actually happened, so the mode check is not vacuous"


def test_a_non_utf8_record_does_not_abort_the_run(site_packages: Path) -> None:
    """`UnicodeDecodeError` is a ValueError, so `except OSError` never caught it.

    The caller promises "best-effort, never fatal to the surrounding install",
    and this path was fatal: it propagated out through `mark_current_set`'s
    loop and abandoned every package after this one. Low probability -- pip
    writes UTF-8 -- but the cost is not proportional to the probability.
    """
    dist_info = _install(site_packages, "pypdf", "6.18.1")
    (dist_info / "RECORD").write_bytes(b"pypdf-6.18.1.dist-info/METADATA,,\n\xff\xfe not utf-8\n")

    prov.write_provenance_marker(dist_info, "autobot-backend")

    assert not (
        dist_info / prov.PROVENANCE_MARKER_FILENAME
    ).exists(), "an unreadable RECORD is unrecordable, so the package reads as unverified"
