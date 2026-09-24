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

import importlib.util
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


def test_a_distribution_without_a_record_is_still_stamped(site_packages: Path) -> None:
    """Best-effort: a missing RECORD must not make the stamp itself fail."""
    dist_info = site_packages / "odd-1.0.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text("Name: odd\n", encoding="utf-8")

    prov.write_provenance_marker(dist_info, "autobot-backend")

    assert (dist_info / prov.PROVENANCE_MARKER_FILENAME).is_file()


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
