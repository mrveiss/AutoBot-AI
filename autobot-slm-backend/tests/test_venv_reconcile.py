# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for api/venv_reconcile.py — the removal half of the update path (#15063).

Loaded by file path, not via ``import api.venv_reconcile`` — the ``api``
package's ``__init__.py`` imports every router (including ``code_sync``,
which needs the Pydantic-schema stand-in dance the ``tests/api`` modules do).
``venv_reconcile.py`` itself has no such dependency: its only non-stdlib
import is ``autobot_shared.time_utils``, so loading it standalone keeps these
tests independent of that machinery and — deliberately — outside
``tests/api``, whose conftest blocks every real ``asyncio.create_subprocess_exec``
call (#13312). The removal tests here need a REAL one, against a throwaway
venv built entirely under ``tmp_path`` — never against the codebase or
``/opt/autobot``.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_VENV_RECONCILE_SRC = _BACKEND_ROOT / "api" / "venv_reconcile.py"


def _load_venv_reconcile():
    spec = importlib.util.spec_from_file_location("_venv_reconcile_15063", _VENV_RECONCILE_SRC)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses needs cls.__module__ resolvable
    spec.loader.exec_module(module)
    return module


vr = _load_venv_reconcile()


# ---------------------------------------------------------------------------
# Real-venv fixture and dist-info builder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RealVenv:
    venv_dir: Path
    python_bin: Path
    pip_bin: Path
    site_packages: Path


@pytest.fixture(scope="module")
def real_venv(tmp_path_factory) -> _RealVenv:
    """A real, throwaway venv built once per module — offline, no network.

    Built with THIS test run's own interpreter (whatever `sys.executable` is),
    not the deployed platform's target Python — the mechanics under test
    (introspect via importlib.metadata, `pip uninstall`) do not depend on the
    interpreter version.
    """
    venv_dir = tmp_path_factory.mktemp("venv15063")
    subprocess.run(  # noqa: S603 — fixed argv, no shell, local interpreter only
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=True,
        timeout=60,
        capture_output=True,
    )
    python_bin = venv_dir / "bin" / "python"
    pip_bin = venv_dir / "bin" / "pip"
    site_out = subprocess.run(  # noqa: S603
        [str(python_bin), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        check=True,
        timeout=30,
        capture_output=True,
        text=True,
    )
    return _RealVenv(venv_dir, python_bin, pip_bin, Path(site_out.stdout.strip()))


def _record_line(rel_path: str, root: Path) -> str:
    data = (root / rel_path).read_bytes()
    digest = hashlib.sha256(data).digest()
    b64 = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return f"{rel_path},sha256={b64},{len(data)}"


def _write_dist_info(site_packages: Path, dist_name: str, module_name: str, version: str, requires: tuple = ()) -> None:
    """Hand-build a real, pip-uninstallable dist-info directory.

    Same on-disk shape `pip install` itself produces (METADATA + RECORD),
    without needing a build backend or network access — a single-file module
    plus its dist-info is enough for `importlib.metadata` to discover it and
    for `pip uninstall` to remove it, and both are exercised for real here.

    The dist-info directory name MUST be derived from *dist_name* (pip's own
    uninstall matches on the directory name, not the METADATA ``Name:``
    field) — *module_name* only names the importable ``.py`` stand-in, kept
    separate so several fixture packages can share a venv's site-packages
    without colliding on their module file.
    """
    dist_info_stem = dist_name.replace("-", "_")
    dist_info = site_packages / f"{dist_info_stem}-{version}.dist-info"
    dist_info.mkdir(parents=True)
    (site_packages / f"{module_name}.py").write_text(f'"""fake package {dist_name}"""\n', encoding="utf-8")
    metadata_lines = ["Metadata-Version: 2.1", f"Name: {dist_name}", f"Version: {version}"]
    metadata_lines += [f"Requires-Dist: {req}" for req in requires]
    (dist_info / "METADATA").write_text("\n".join(metadata_lines) + "\n", encoding="utf-8")
    (dist_info / "INSTALLER").write_text("test-fixture\n", encoding="utf-8")
    record_lines = [
        _record_line(f"{module_name}.py", site_packages),
        _record_line(f"{dist_info_stem}-{version}.dist-info/METADATA", site_packages),
        _record_line(f"{dist_info_stem}-{version}.dist-info/INSTALLER", site_packages),
        f"{dist_info_stem}-{version}.dist-info/RECORD,,",
    ]
    (dist_info / "RECORD").write_text("\n".join(record_lines) + "\n", encoding="utf-8")


def _installed_names(real_venv: _RealVenv) -> set:
    raw = subprocess.run(  # noqa: S603
        [
            str(real_venv.python_bin),
            "-c",
            "import importlib.metadata as m, json\n"
            "print(json.dumps([d.metadata['Name'] for d in m.distributions() if d.metadata.get('Name')]))",
        ],
        check=True,
        timeout=30,
        capture_output=True,
        text=True,
    )
    return {vr.normalize_name(n) for n in json.loads(raw.stdout)}


# ---------------------------------------------------------------------------
# The real update path — #15063 AC: drive it for real, assert removed AND kept
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_real_venv_removes_orphan_keeps_declared_and_transitive(
    real_venv: _RealVenv, tmp_path: Path
) -> None:
    """A package removed from requirements.txt is gone; a still-declared
    package and a transitive dependency of it are untouched (#15063)."""
    site = real_venv.site_packages
    _write_dist_info(site, "pkg-root", "pkg_root_15063", "1.0", requires=("pkg-trans",))
    _write_dist_info(site, "pkg-trans", "pkg_trans_15063", "1.0")
    _write_dist_info(site, "pkg-orphan", "pkg_orphan_15063", "1.0")

    req = tmp_path / "requirements.txt"
    req.write_text("pkg-root>=1.0\n", encoding="utf-8")  # noqa: async_blocking_io

    lock_path = real_venv.venv_dir / vr._DECLARED_LOCK_FILENAME
    # pkg-trans was previously declared DIRECTLY (like a pin later dropped in
    # favour of letting pkg-root pull it in transitively) — the reconcile must
    # keep it via the transitive-closure check, not because it is still declared.
    lock_path.write_text(  # noqa: async_blocking_io
        json.dumps({"declared": ["pkg-root", "pkg-trans", "pkg-orphan"]}), encoding="utf-8"
    )

    steps: list = []
    report = await vr.reconcile_component("test-comp", str(req), str(real_venv.pip_bin), steps)

    assert report.status == "ok"
    assert report.removed == ("pkg-orphan",)  # exact package, never len() > 0
    assert "pkg-trans" not in report.removed
    assert "pkg-root" not in report.removed
    assert "pkg-trans" in report.kept_transitive

    installed = _installed_names(real_venv)
    assert "pkg-orphan" not in installed
    assert "pkg-root" in installed
    assert "pkg-trans" in installed

    # AC: the removal set is reported BEFORE it happens, in the job's own steps.
    assert any("pkg-orphan" in s and "to remove" in s for s in steps)


@pytest.mark.asyncio
async def test_reconcile_removes_a_name_an_operator_reinstalled_after_it_was_declared(
    real_venv: _RealVenv, tmp_path: Path
) -> None:
    """KNOWN LIMITATION (module docstring): this is a name diff against the
    tool's OWN prior-declared history, with no install-provenance marker.
    A package this venv's history once declared, dropped from requirements,
    then reinstalled by an operator under that exact name before the next
    reconcile, is indistinguishable from tool debris and IS removed. Only a
    name never declared by this tool's history (e.g. `ipdb`) is safe — see
    test_reconcile_real_venv_removes_orphan_keeps_declared_and_transitive's
    pkg-root/pkg-trans, which the lock never lets become candidates at all,
    and the untouched `pip`/`setuptools` in every real-venv test here, which
    were never in any lock this tool wrote.
    """
    site = real_venv.site_packages
    _write_dist_info(site, "pkg-stale-collide", "pkg_stale_collide_15063", "1.0")

    req = tmp_path / "requirements.txt"
    req.write_text("\n", encoding="utf-8")  # noqa: async_blocking_io

    lock_path = real_venv.venv_dir / vr._DECLARED_LOCK_FILENAME
    lock_path.write_text(json.dumps({"declared": ["pkg-stale-collide"]}), encoding="utf-8")  # noqa: async_blocking_io

    steps: list = []
    report = await vr.reconcile_component("test-comp-collide", str(req), str(real_venv.pip_bin), steps)

    assert report.status == "ok"
    assert report.removed == ("pkg-stale-collide",)
    assert "pkg-stale-collide" not in _installed_names(real_venv)


@pytest.mark.asyncio
async def test_reconcile_never_attempts_to_remove_a_package_that_is_not_installed(
    real_venv: _RealVenv, tmp_path: Path
) -> None:
    """A previously-declared package that is already absent (removed by hand,
    or never actually landed) must not appear in the removal set — there is
    nothing to uninstall, and reporting it as removed would claim an action
    that never happened."""
    site = real_venv.site_packages
    _write_dist_info(site, "pkg-still-declared", "pkg_still_declared_15063", "1.0")

    req = tmp_path / "requirements.txt"
    req.write_text("pkg-still-declared>=1.0\n", encoding="utf-8")  # noqa: async_blocking_io

    lock_path = real_venv.venv_dir / vr._DECLARED_LOCK_FILENAME
    lock_path.write_text(  # noqa: async_blocking_io
        json.dumps({"declared": ["pkg-still-declared", "pkg-phantom-never-installed"]}), encoding="utf-8"
    )

    steps: list = []
    report = await vr.reconcile_component("test-comp-phantom", str(req), str(real_venv.pip_bin), steps)

    assert report.status == "ok"
    assert report.removed == ()
    assert report.failed == ()
    assert "pkg-phantom-never-installed" not in report.removed


@pytest.mark.asyncio
async def test_reconcile_first_run_records_baseline_and_removes_nothing(real_venv: _RealVenv, tmp_path: Path) -> None:
    """No prior snapshot means "cannot reconcile yet" — never "nothing declared
    means nothing to keep". Nothing is removed and a baseline is recorded."""
    site = real_venv.site_packages
    _write_dist_info(site, "pkg-baseline", "pkg_baseline_15063", "1.0")

    req = tmp_path / "requirements.txt"
    req.write_text("pkg-baseline>=1.0\n", encoding="utf-8")  # noqa: async_blocking_io

    lock_path = real_venv.venv_dir / vr._DECLARED_LOCK_FILENAME
    lock_path.unlink(missing_ok=True)  # simulate "no history yet" regardless of test order

    steps: list = []
    report = await vr.reconcile_component("test-comp-baseline", str(req), str(real_venv.pip_bin), steps)

    assert report.status == "baseline_recorded"
    assert report.removed == ()
    assert lock_path.exists()
    recorded = json.loads(lock_path.read_text(encoding="utf-8"))  # noqa: async_blocking_io
    assert "pkg-baseline" in recorded["declared"]
    assert "pkg-baseline" in _installed_names(real_venv)


# ---------------------------------------------------------------------------
# Fail closed — uncertain reconciliation refuses, never approximates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_refuses_when_an_include_cannot_be_resolved(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("-r missing-included.txt\npackage-a>=1.0\n", encoding="utf-8")  # noqa: async_blocking_io

    steps: list = []
    report = await vr.reconcile_component("test-comp-refuse", str(req), "/nonexistent/venv/bin/pip", steps)

    assert report.status == "refused"
    assert "missing-included.txt" in report.reason
    assert not any("to remove" in s for s in steps)


@pytest.mark.asyncio
async def test_reconcile_refuses_when_venv_cannot_be_introspected(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("package-a>=1.0\n", encoding="utf-8")  # noqa: async_blocking_io

    steps: list = []
    report = await vr.reconcile_component("test-comp-noventv", str(req), "/nonexistent/venv/bin/pip", steps)

    assert report.status == "refused"
    assert "introspect" in report.reason


def test_refuse_explicit_list_reports_not_silently_skips() -> None:
    """The three ansible-package-list workers get a REPORTED refusal, not a
    silent no-op (#15063 AC4)."""
    steps: list = []
    report = vr.refuse_explicit_list("autobot-npu-worker", steps)

    assert report.status == "refused"
    assert "autobot-npu-worker" in report.reason
    assert "ansible role" in report.reason
    assert steps and "autobot-npu-worker" in steps[0]


def test_explicit_list_components_are_exactly_the_three_ansible_list_workers() -> None:
    assert vr.EXPLICIT_LIST_COMPONENTS == frozenset(
        {"autobot-npu-worker", "autobot-browser-worker", "autobot-slm-agent"}
    )


# ---------------------------------------------------------------------------
# A failed removal is retried next run, not forgotten
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_removals_keeps_a_failed_uninstall_in_the_lock_for_retry(tmp_path: Path) -> None:
    pip_bin = tmp_path / "venv" / "bin" / "pip"
    pip_bin.parent.mkdir(parents=True)
    lock_path = pip_bin.parents[1] / vr._DECLARED_LOCK_FILENAME

    declared = {"pkg-a"}
    previous = {"pkg-a", "pkg-b"}
    graph = {"pkg-a": set(), "pkg-b": set()}

    async def _fake_uninstall(pip, names):
        return [], list(names)  # every removal attempt fails

    orig = vr.uninstall_packages
    vr.uninstall_packages = _fake_uninstall
    try:
        steps: list = []
        report = await vr._apply_removals("test-comp-retry", declared, previous, graph, lock_path, pip_bin, steps)
    finally:
        vr.uninstall_packages = orig

    assert report.failed == ("pkg-b",)
    assert report.removed == ()
    recorded = json.loads(lock_path.read_text(encoding="utf-8"))  # noqa: async_blocking_io
    assert set(recorded["declared"]) == {"pkg-a", "pkg-b"}  # retried next run, not forgotten


@pytest.mark.asyncio
async def test_uninstall_packages_is_an_async_callee_usable_with_asyncmock(tmp_path: Path) -> None:
    """Sanity check for the AsyncMock convention this suite relies on elsewhere."""
    mock = AsyncMock(return_value=(["pkg-x"], []))
    removed, failed = await mock(Path("/unused/pip"), ["pkg-x"])
    assert removed == ["pkg-x"]
    assert failed == []
    mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# Declared-set resolution: -r / -c / -e, mirroring the real repo layout
# ---------------------------------------------------------------------------


def test_resolve_declared_names_follows_r_and_e_ignores_c(tmp_path: Path) -> None:
    (tmp_path / "autobot_shared_pkg").mkdir()
    (tmp_path / "autobot_shared_pkg" / "pyproject.toml").write_text(
        '[project]\nname = "autobot_shared"\nversion = "0.1"\n', encoding="utf-8"
    )
    (tmp_path / "constraints").mkdir()
    (tmp_path / "constraints" / "shared.txt").write_text("numpy>=2.0\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("tenacity>=9.0\n", encoding="utf-8")

    backend = tmp_path / "autobot-backend"
    backend.mkdir()
    (backend / "requirements.txt").write_text(
        "-e ../autobot_shared_pkg\n"
        "-c ../constraints/shared.txt  # pins transitive numpy\n"
        "fastapi>=0.140.0\n"
        "\n"
        "-r ../requirements.txt\n",
        encoding="utf-8",
    )

    declared, warnings = vr.resolve_declared_names(backend / "requirements.txt")

    assert warnings == []
    assert declared == {"autobot-shared", "fastapi", "tenacity"}
    assert "numpy" not in declared  # a -c entry constrains a version, it never declares


def test_resolve_declared_names_warns_on_missing_constraints_file(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("-c missing_constraints.txt\npackage-a>=1.0\n", encoding="utf-8")

    declared, warnings = vr.resolve_declared_names(req)

    assert declared == {"package-a"}
    assert any("missing_constraints.txt" in w for w in warnings)


def test_resolve_declared_names_warns_on_missing_include(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("-r nowhere.txt\n", encoding="utf-8")

    declared, warnings = vr.resolve_declared_names(req)

    assert declared == set()
    assert any("nowhere.txt" in w for w in warnings)


# ---------------------------------------------------------------------------
# load_lock — fails closed (returns None -> refused/baseline), never raises
# ---------------------------------------------------------------------------


def test_load_lock_returns_none_when_declared_entries_are_not_strings(tmp_path: Path) -> None:
    """A hand-edited lock with non-string entries must refuse (None), never
    raise inside normalize_name's regex — the same fail-closed contract as
    a missing/truncated file, just a different malformed shape."""
    lock_path = tmp_path / vr._DECLARED_LOCK_FILENAME
    lock_path.write_text(json.dumps({"declared": [1, 2, 3]}), encoding="utf-8")
    assert vr.load_lock(lock_path) is None


def test_load_lock_returns_none_when_top_level_is_not_an_object(tmp_path: Path) -> None:
    lock_path = tmp_path / vr._DECLARED_LOCK_FILENAME
    lock_path.write_text(json.dumps([{"name": "x"}]), encoding="utf-8")
    assert vr.load_lock(lock_path) is None


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_transitive_closure_walks_multi_level_deps_and_stops_at_orphans() -> None:
    graph = {"a": {"b"}, "b": {"c"}, "c": set(), "orphan": set()}
    closure = vr.transitive_closure({"a"}, graph)
    assert closure == {"a", "b", "c"}
    assert "orphan" not in closure


def test_normalize_name_is_pep503() -> None:
    assert vr.normalize_name("Autobot_Shared") == "autobot-shared"
    assert vr.normalize_name("Foo..Bar__Baz") == "foo-bar-baz"


def test_extract_requirement_name_strips_specifiers_extras_markers() -> None:
    assert vr.extract_requirement_name("FastAPI[all]>=0.140,<1.0 ; python_version>='3.10'") == "fastapi"
    assert vr.extract_requirement_name("   ") is None


def test_build_dependency_graph_normalizes_names_on_both_sides() -> None:
    raw = {"Pkg-Root": ["Pkg_Trans>=1.0 ; extra == 'x'"], "Pkg_Trans": []}
    graph = vr.build_dependency_graph(raw)
    assert graph == {"pkg-root": {"pkg-trans"}, "pkg-trans": set()}
