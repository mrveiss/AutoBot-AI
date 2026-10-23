# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One env var, one fallback; one SSOT constant, one definition (#18094).

The live-tree test proves the sweep found something (reach floor over the fallback reads it
collected) and then that nothing forks. The contrast tests rebuild the shapes #18094 found in a
synthetic tree -- the doctor's ``'8080'`` against the worker's ``8081``, and a feature module's
``DEFAULT_EMBEDDING_MODEL`` shadowing the SSOT one -- and require the guard to fail on each, so a
"none found" on the live tree cannot come from a detector that lost its teeth.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint import check_getenv_ssot_drift  # noqa: F401 -- puts tools/lint on sys.path for the sibling import

from tools.lint import _env_fork_scan as scan_mod  # isort: skip

_ROOT = repo_root()


def _live_scan(root: Path, registry: dict | None = None) -> scan_mod.ScanResult:
    return scan_mod.sweep_env_forks(root, registry or {})


def _read_sites(root: Path) -> list[str]:
    """Every literal-fallback env read the sweep collects; ``[]`` on a tree without the SSOT modules."""
    try:
        return _live_scan(root).sites
    except (RuntimeError, FileNotFoundError):
        return []


#: ONE population (``scan_mod.sweep_env_forks`` over tracked Python) and ONE floor (``scan_mod.FORK_READ_FLOOR``, which
#: ``check_env_forks`` enforces); ``verify_floor`` proves that number against the live population, so the hook cannot
#: drift to a second one.
READS = declare(
    "env-fallback-read-sites-18094",
    discover=_read_sites,
    floor=scan_mod.FORK_READ_FLOOR,
    growth=40,
    what="literal-fallback env read call sites",
    roots=scan_mod.SCAN_ROOTS,
)


def test_no_env_var_forks_and_no_ssot_constant_is_shadowed() -> None:
    result = _live_scan(_ROOT, scan_mod.registry_defaults())
    assert len(READS.examined(_ROOT)) >= READS.floor, "the sweep collected fewer reads than its floor"
    assert result.findings() == [], result.summary()
    assert "none found" in result.summary() and f"checked {result.env_reads}" in result.summary()


# --- contrast: the guard must fail on a reintroduced fork -------------------------------------------


def _tree(tmp_path: Path, files: dict[str, str]) -> tuple[Path, list[Path]]:
    base = {
        "autobot_shared/ssot_config.py": 'DEFAULT_EMBEDDING_MODEL = "nomic-embed-text:latest"\n',
        "autobot_shared/ssot_constants.py": "",
        "autobot_shared/ssot_tls.py": "",
    }
    paths = []
    for rel, text in {**base, **files}.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return tmp_path, paths


def _scan(tmp_path: Path, files: dict[str, str], registry: dict | None = None) -> scan_mod.ScanResult:
    root, paths = _tree(tmp_path, files)
    return scan_mod.scan(root, paths, registry or {})


def test_the_npu_port_fork_is_flagged(tmp_path: Path) -> None:
    result = _scan(
        tmp_path,
        {
            "autobot-backend/cli/doctor.py": 'import os\nP = os.environ.get("NPU_WORKER_PORT", "8080")\n',
            "autobot-infrastructure/worker.py": 'import os\nP = int(os.getenv("NPU_WORKER_PORT", 8081))\n',
        },
    )
    assert "NPU_WORKER_PORT" in result.forks
    assert any("NPU_WORKER_PORT" in line for line in result.findings())


def test_a_read_that_disagrees_with_the_registry_default_is_flagged(tmp_path: Path) -> None:
    files = {"autobot-backend/a.py": 'import os\nP = os.getenv("NPU_WORKER_PORT", "8080")\n'}
    assert "NPU_WORKER_PORT" in _scan(tmp_path, files, {"NPU_WORKER_PORT": 8081}).forks


def test_spelling_differences_are_not_forks(tmp_path: Path) -> None:
    result = _scan(
        tmp_path,
        {
            "autobot-backend/a.py": 'import os\nP = os.getenv("NPU_WORKER_PORT", "8081")\n',
            "autobot-backend/b.py": 'import os\nP = os.getenv("NPU_WORKER_PORT", 8081)\n',
        },
        {"NPU_WORKER_PORT": 8081},
    )
    assert result.forks == {}


def test_the_exempt_marker_is_honoured(tmp_path: Path) -> None:
    files = {
        "autobot-backend/a.py": 'import os\nP = os.getenv("X_MODE", "a")\n',
        "autobot-backend/b.py": 'import os\nP = os.getenv("X_MODE", "b")  # ssot-config-exempt: deliberate\n',
    }
    assert _scan(tmp_path, files).forks == {}


def test_a_module_constant_shadowing_the_ssot_one_is_flagged(tmp_path: Path) -> None:
    files = {"autobot-backend/code_intelligence/x.py": 'DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"\n'}
    result = _scan(tmp_path, files)
    assert len(result.shadows) == 1 and "DEFAULT_EMBEDDING_MODEL" in result.shadows[0]
    assert result.shadows[0] in result.findings()


def test_an_unrelated_constant_is_not_a_shadow(tmp_path: Path) -> None:
    assert _scan(tmp_path, {"autobot-backend/x.py": "MAX_ROWS = 10\n"}).shadows == []


def test_a_listed_fork_is_suppressed_and_a_fixed_one_goes_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forking = {
        "autobot-backend/a.py": 'import os\nP = os.getenv("OLD_FORK", "a")\n',
        "autobot-backend/b.py": 'import os\nP = os.getenv("OLD_FORK", "b")\n',
    }
    monkeypatch.setitem(scan_mod.KNOWN_ENV_FORKS, "OLD_FORK", "#1")
    assert not any(line.startswith("OLD_FORK") for line in _scan(tmp_path / "forking", forking).findings())
    fixed = _scan(tmp_path / "fixed", {"autobot-backend/a.py": 'import os\nP = os.getenv("OLD_FORK", "a")\n'})
    assert any(line.startswith("OLD_FORK") and "no longer forks" in line for line in fixed.findings())


def test_the_summary_distinguishes_checked_from_found() -> None:
    quiet = scan_mod.ScanResult(env_reads=3, env_vars=2)
    quiet.forks = dict.fromkeys(scan_mod.KNOWN_ENV_FORKS, ["x"])
    assert "checked 3" in quiet.summary() and "none found" in quiet.summary()
    quiet.shadows.append("a.py:1: X shadows the SSOT constant in b.py")
    assert "1 finding(s)" in quiet.summary()


# --- contrast: constant defaults, `from os import getenv`, and a None registry default ---------------


def test_a_module_constant_default_is_resolved_and_forks(tmp_path: Path) -> None:
    result = _scan(
        tmp_path,
        {
            "autobot-backend/a.py": 'import os\nDEFAULT_PORT = "8080"\nP = os.getenv("NPU_WORKER_PORT", DEFAULT_PORT)\n',
            "autobot-backend/b.py": 'import os\nP = os.getenv("NPU_WORKER_PORT", 8081)\n',
        },
    )
    assert "NPU_WORKER_PORT" in result.forks and result.unresolved == 0


def test_a_constant_default_equal_to_the_other_reader_is_no_fork(tmp_path: Path) -> None:
    files = {
        "autobot-backend/a.py": 'import os\nDEFAULT_PORT = 8081\nP = os.getenv("NPU_WORKER_PORT", DEFAULT_PORT)\n',
        "autobot-backend/b.py": 'import os\nP = os.getenv("NPU_WORKER_PORT", "8081")\n',
    }
    assert _scan(tmp_path, files).forks == {}


def test_an_unresolvable_default_is_skipped_and_counted(tmp_path: Path) -> None:
    files = {
        "autobot-backend/a.py": (
            "import os\nfrom elsewhere import OTHER\n"
            'A = os.getenv("X_A", OTHER)\nB = os.getenv("X_B", compute())\nC = os.getenv("X_C", None)\n'
        ),
        "autobot-backend/b.py": 'import os\nA = os.getenv("X_A", "1")\n',
    }
    result = _scan(tmp_path, files)
    assert result.unresolved == 2 and result.forks == {} and result.env_reads == 1
    assert "2 non-literal defaults skipped" in result.summary()


def test_from_os_import_getenv_and_environ_are_read(tmp_path: Path) -> None:
    result = _scan(
        tmp_path,
        {
            "autobot-backend/a.py": 'from os import getenv\nP = getenv("NPU_WORKER_PORT", "8080")\n',
            "autobot-backend/b.py": 'from os import environ as env\nP = env.get("NPU_WORKER_PORT", "8081")\n',
        },
    )
    assert result.env_reads == 2 and "NPU_WORKER_PORT" in result.forks


def test_a_bare_getenv_without_the_os_import_is_not_an_env_read(tmp_path: Path) -> None:
    files = {"autobot-backend/a.py": 'def getenv(a, b):\n    return b\n\nP = getenv("X_LOCAL", "a")\n'}
    assert _scan(tmp_path, files).env_reads == 0


def test_a_none_registry_default_compares_readers_only(tmp_path: Path) -> None:
    agree = {
        "autobot-backend/a.py": 'import os\nP = os.getenv("X_OPT", "8080")\n',
        "autobot-backend/b.py": 'import os\nP = os.getenv("X_OPT", 8080)\n',
    }
    assert _scan(tmp_path / "agree", agree, {"X_OPT": None}).forks == {}
    disagree = {**agree, "autobot-backend/b.py": 'import os\nP = os.getenv("X_OPT", 9090)\n'}
    forks = _scan(tmp_path / "disagree", disagree, {"X_OPT": None}).forks
    assert "X_OPT" in forks and not any("registry declares" in line for line in forks["X_OPT"])


# --- the sweep's own entrypoint (#19215): refusals are exit 2, never a traceback ---------------------


def test_a_missing_ssot_source_is_a_vacuous_refusal_not_a_traceback(tmp_path: Path) -> None:
    root, paths = _tree(tmp_path, {"autobot-backend/a.py": 'import os\nP = os.getenv("X_A", "1")\n'})
    (root / "autobot_shared" / "ssot_constants.py").unlink()
    with pytest.raises(scan_mod.VacuousScan, match="ssot_constants.py is not in"):
        scan_mod.scan(root, paths, {})


def test_the_summary_names_all_three_finding_kinds() -> None:
    text = scan_mod.summary(3)
    assert "differing fallbacks" in text and "registry default" in text and "shadowing an SSOT constant" in text


def test_the_entrypoint_exits_two_on_a_tree_without_the_ssot_sources(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from _check_harness import run_check

    from autobot_shared.isolated_git import git, make_repo

    root, _ = _tree(tmp_path, {"autobot-backend/a.py": 'import os\nP = os.getenv("X_A", "1")\n'})
    (root / "autobot_shared" / "ssot_tls.py").unlink()
    make_repo(root)
    git(root, "add", "-A")
    code = run_check(scan_mod.HOOK_ID, scan_mod.collect_env_forks, [], root=root, summary=scan_mod.summary)
    assert code == 2 and "ssot_tls.py is not in" in caplog.text
