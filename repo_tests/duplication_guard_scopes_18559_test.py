# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The duplication guard's scopes, and the job that lowers their pins (#18559, #18461, #16324).

The guard is only as wide as the paths its steps name. Dropping one (or a whole step) turns a
tree back into one nothing scans, and every other test still passes, so the scope list is held
here as a contract: each step, the trees it scans, its pin variable and its log. The fork
ratchet's roots are held the same way, because #18559 widened them for the same reason.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

from autobot_shared.symbol_forks import FORK_ROOTS
from tools.lint._scan_helpers import tracked_paths

WORKFLOW = Path(".github/workflows/duplication-guard.yml")

#: step id -> (trees jscpd scans, pin variable, log the step tees)
EXPECTED_SCOPES = {
    "main_scope": (("autobot-backend", "autobot-frontend/src"), "MAX_DUP_LINES", "main-dup.log"),
    "slm_scope": (
        ("autobot_shared", "autobot-slm-backend", "autobot-slm-frontend/src"),
        "SLM_MAX_DUP_LINES",
        "slm-gate.log",
    ),
    "tooling_scope": (("scripts", "tools", "pipeline-scripts"), "TOOLING_MAX_DUP_LINES", "tooling-gate.log"),
    "cross_gui_scope": (
        ("autobot-frontend/src", "autobot-slm-frontend/src", "autobot-plugins", "libs/autobot-ui"),
        "CROSS_GUI_MAX_DUP_LINES",
        "cross-gui-gate.log",
    ),
    "cross_backend_scope": (
        ("autobot-backend", "autobot-slm-backend", "autobot_shared", "plugins"),
        "CROSS_BACKEND_MAX_DUP_LINES",
        "cross-backend-gate.log",
    ),
}

#: Roots #18559 added to the symbol-fork ratchet; it must keep reading all of them.
REQUIRED_FORK_ROOTS = (
    "autobot-backend",
    "autobot-slm-backend",
    "autobot_shared",
    "autobot-npu-worker",
    "autobot-tts-worker",
    "autobot-browser-worker",
    "autobot-infrastructure",
    "scripts",
    "tools",
    "pipeline-scripts",
)

_SPEC = importlib.util.spec_from_file_location(
    "duplication_pin_lowering", repo_root() / "scripts" / "duplication_pin_lowering.py"
)
lowering = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = lowering
_SPEC.loader.exec_module(lowering)


def _document() -> dict:
    return yaml.safe_load((repo_root() / WORKFLOW).read_text(encoding="utf-8"))


def _steps() -> dict[str, dict]:
    job = _document()["jobs"]["duplication-guard"]
    return {step["id"]: step for step in job["steps"] if "id" in step}


def _scanned_trees(run: str) -> tuple[str, ...]:
    """The positional paths between ``jscpd@...`` and the first flag."""
    head = run.split('"jscpd@${JSCPD_VERSION}"', 1)[1].split(" -k ", 1)[0]
    return tuple(head.replace("\\", " ").split())


def _flags(run: str) -> str:
    return run.split(" -k ", 1)[1].split("|", 1)[0]


def test_every_scope_scans_exactly_its_trees_and_is_gated_on_its_pin() -> None:
    steps = _steps()
    for step_id, (trees, pin_var, log) in EXPECTED_SCOPES.items():
        assert step_id in steps, f"scope step {step_id} is gone from {WORKFLOW}"
        run = steps[step_id]["run"]
        assert _scanned_trees(run) == trees, f"{step_id} no longer scans {trees}"
        assert f"tee /tmp/{log}" in run, f"{step_id} no longer tees /tmp/{log}"
        assert f'duplication_gate.py /tmp/{log} "${{{pin_var}}}"' in run, f"{step_id} is not gated on {pin_var}"


def test_no_scope_step_is_added_without_joining_the_contract() -> None:
    gating = {sid for sid, step in _steps().items() if "duplication_gate.py" in step.get("run", "")}
    assert gating == set(EXPECTED_SCOPES), sorted(gating ^ set(EXPECTED_SCOPES))


def test_every_scope_uses_the_same_jscpd_flags() -> None:
    """A scope measured with other flags is a different number under the same name."""
    steps = _steps()
    reference = _flags(steps["main_scope"]["run"])
    for step_id in EXPECTED_SCOPES:
        assert _flags(steps[step_id]["run"]) == reference, f"{step_id} has different jscpd flags"


PINS = Path(".github/duplication-pins.json")


def test_every_pin_is_a_measured_count_in_the_data_file() -> None:
    pins = json.loads((repo_root() / PINS).read_text(encoding="utf-8"))
    assert set(pins) == {pin for _t, pin, _l in EXPECTED_SCOPES.values()}
    for var, value in pins.items():
        assert isinstance(value, int) and not isinstance(value, bool) and value >= 0, f"{var}={value!r}"


def test_no_numeric_pin_is_restated_in_the_workflow() -> None:
    """One home: the data file. A pin back in the yml is a second source that can disagree."""
    text = (repo_root() / WORKFLOW).read_text(encoding="utf-8")
    assert not re.search(r"^\s*[A-Z_]*MAX_DUP_LINES:\s*['\"]?[0-9]+", text, re.MULTILINE)
    env = _document()["jobs"]["duplication-guard"].get("env", {})
    assert not [k for k in env if k.endswith("MAX_DUP_LINES")], "a pin is declared in the job env"


def test_the_workflow_loads_the_pins_before_the_first_gate() -> None:
    steps = _document()["jobs"]["duplication-guard"]["steps"]
    names = [s.get("name") for s in steps]
    load = names.index("Load the pins")
    assert "duplication-pins.json" in steps[load]["run"] and "GITHUB_ENV" in steps[load]["run"]
    assert load < next(i for i, s in enumerate(steps) if s.get("id") == "main_scope")


_SCANNED = {"py", "ts", "js", "vue"}
#: What the scopes' `-i` list excludes, as path regexes (the workflow's list, kept in step by hand).
_IGNORED = re.compile(
    r"(node_modules|__pycache__|/tests/|/__tests__/|/generated/|/migrations/|/mocks/|/i18n/)"
    r"|/test_[^/]*$|_test\.py$|\.test\.ts$|\.stories\."
)


def _glob_matches(pattern: str, path: str) -> bool:
    regex = re.escape(pattern).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.fullmatch(regex, path) is not None


def _tracked(tree: str) -> list[str]:
    """Through the canonical enumerator, never a direct `git ls-files` (#15926)."""
    paths = tracked_paths(repo_root(), tree)
    return [f for f in paths if f.rsplit(".", 1)[-1] in _SCANNED and not _IGNORED.search("/" + f)]


def _uncovered(paths: list[str], trigger_paths: list[str]) -> list[str]:
    return [f for f in paths if not any(_glob_matches(g, f) for g in trigger_paths)]


def test_every_file_a_scope_scans_is_covered_by_a_trigger_glob() -> None:
    """Per scanned extension, not per tree: a tree can be scanned for .ts yet only trigger on .py."""
    on = _document()[True]
    for event in ("pull_request", "push"):
        for _id, (trees, _pin, _log) in EXPECTED_SCOPES.items():
            for tree in trees:
                missing = _uncovered(_tracked(tree), on[event]["paths"])
                assert not missing, f"{event}: {tree} has scanned files no trigger covers, e.g. {missing[:3]}"


def test_the_coverage_check_fails_when_a_glob_is_removed() -> None:
    """Negative control: the check above must be able to fail."""
    on = _document()[True]
    trimmed = [g for g in on["pull_request"]["paths"] if not (g.startswith("autobot-plugins/") and g.endswith(".ts"))]
    assert _uncovered(_tracked("autobot-plugins"), trimmed), "removing a glob went unnoticed"


def test_the_lowering_table_matches_the_workflow() -> None:
    table = {(scope.pin_var, scope.log_name) for scope in lowering.SCOPES}
    assert table == {(pin, log) for _t, pin, log in EXPECTED_SCOPES.values()}


def test_the_fork_ratchet_still_reads_every_widened_root() -> None:
    assert set(REQUIRED_FORK_ROOTS) <= set(FORK_ROOTS), sorted(set(REQUIRED_FORK_ROOTS) - set(FORK_ROOTS))


@pytest.mark.parametrize("root", REQUIRED_FORK_ROOTS)
def test_the_roots_contract_fails_for_any_single_root_removed(root: str) -> None:
    """Negative control: FORK_ROOTS minus one required root must be rejected by the contract."""
    reduced = tuple(r for r in FORK_ROOTS if r != root)
    assert not set(REQUIRED_FORK_ROOTS) <= set(reduced)


def test_the_stale_deferral_comment_is_gone() -> None:
    text = (repo_root() / WORKFLOW).read_text(encoding="utf-8")
    assert "deferred" not in text.split("name: duplication-guard", 1)[0]
    assert "#9856 and #9859, named here before, are closed" in text


# --- the pin-lowering job (#16324) ---------------------------------------------------------

_ROW = "│ Total: │ 100 │ 5000 │ 40000 │ 7 │ {dup} (1%) │ 0 │"


def _lower_job() -> dict:
    return _document()["jobs"]["lower-pins"]


def test_the_job_runs_only_on_a_green_push_and_never_pushes_main() -> None:
    job = _lower_job()
    assert job["needs"] == "duplication-guard"
    assert "github.event_name == 'push'" in job["if"] and "result == 'success'" in job["if"]
    assert job["permissions"] == {"contents": "write", "pull-requests": "write"}
    run = "\n".join(step.get("run", "") for step in job["steps"])
    assert "git push --force-with-lease" in run
    assert not re.search(r"git push[^\n]*\bmain\b", run), "the job must open a PR, never push main"


def test_the_job_stages_only_the_pins_file_so_no_workflow_file_is_pushed() -> None:
    run = "\n".join(step.get("run", "") for step in _lower_job()["steps"])
    adds = re.findall(r"git add (\S+)", run)
    assert adds == ['"${PINS}"'], adds
    assert "PINS: .github/duplication-pins.json" in (repo_root() / WORKFLOW).read_text(encoding="utf-8")
    assert "git add -A" not in run and "git commit -a" not in run


def test_the_job_has_no_persisted_credentials_and_serialises_runs() -> None:
    job = _lower_job()
    checkout = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["persist-credentials"] is False
    assert job["concurrency"] == "duplication-pins"


def test_the_job_uses_the_pat_alone_and_fails_loudly_without_it() -> None:
    step = next(s for s in _lower_job()["steps"] if s.get("name", "").startswith("Open or update"))
    assert step["env"]["GH_TOKEN"] == "${{ secrets.AUTOBOT_PUSH_TOKEN }}", "no GITHUB_TOKEN fallback: its PR runs no CI"
    run = step["run"]
    assert "AUTOBOT_PUSH_TOKEN not set -- bot PR would never trigger CI" in run
    assert run.index("AUTOBOT_PUSH_TOKEN not set") < run.index("git push"), "the check must come before any push"


def test_a_pin_above_its_count_is_lowered_to_it() -> None:
    pins, changes = lowering.lower_pins({"A": 500, "B": 100}, {"A": 480, "B": 100})
    assert changes == [("A", 500, 480)] and pins == {"A": 480, "B": 100}


def test_a_pin_is_never_raised() -> None:
    pins, changes = lowering.lower_pins({"A": 500}, {"A": 501})
    assert changes == [] and pins == {"A": 500}


@pytest.mark.parametrize("pin", ["UNMEASURED", "12.5", "", True, None])
def test_a_pin_that_is_not_a_count_is_left_alone(pin: object) -> None:
    assert lowering.lower_pins({"A": pin}, {"A": 1}) == ({"A": pin}, [])


def _write_logs(directory: Path, dup: int) -> None:
    for scope in lowering.SCOPES:
        (directory / scope.log_name).write_text(_ROW.format(dup=dup), encoding="utf-8")


def _run_cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603  # fixed argv, no shell
        [sys.executable, "-I", str(repo_root() / "scripts" / "duplication_pin_lowering.py"), *argv],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_the_cli_lowers_the_real_pins_file_from_real_logs(tmp_path: Path) -> None:
    pins = tmp_path / "pins.json"
    pins.write_text((repo_root() / PINS).read_text(encoding="utf-8"), encoding="utf-8")
    _write_logs(tmp_path, 7)
    done = _run_cli(str(pins), str(tmp_path))
    assert done.returncode == 0, done.stderr
    assert len(done.stdout.splitlines()) == len(lowering.SCOPES)
    assert set(json.loads(pins.read_text(encoding="utf-8")).values()) == {7}


def test_export_prints_every_pin_for_github_env() -> None:
    done = _run_cli("--export", str(repo_root() / PINS))
    pins = json.loads((repo_root() / PINS).read_text(encoding="utf-8"))
    assert done.stdout.splitlines() == [f"{k}={v}" for k, v in pins.items()]


def test_an_unreadable_log_touches_no_pin(tmp_path: Path) -> None:
    pins = tmp_path / "pins.json"
    pins.write_text('{"MAX_DUP_LINES": 500}\n', encoding="utf-8")
    _write_logs(tmp_path, 1)
    (tmp_path / lowering.SCOPES[1].log_name).unlink()
    assert lowering.main([str(pins), str(tmp_path)]) == 2
    assert pins.read_text(encoding="utf-8") == '{"MAX_DUP_LINES": 500}\n'
