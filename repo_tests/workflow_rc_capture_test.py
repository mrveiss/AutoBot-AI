# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An exit code captured under ``bash -e`` must be reachable on the failing path (#16237).

A workflow step with no ``shell:`` key runs as ``bash -e {0}``, and ``shell: bash``
runs as ``bash --noprofile --norc -eo pipefail {0}``. Both carry errexit, and
``set -uo pipefail`` does not clear it -- it sets two other options. So this shape
never records a failure::

    python3 tool.py >out.log 2>&1
    rc=$?

errexit aborts the step on the failing command and the capture never runs. On the
passing path it works, which is the only path most of these steps had exercised --
that is how four steps came to carry it, each under a comment claiming the opposite.
Two correct shapes were already in the tree: ``set +e`` before the command and
``set -e`` after the capture, or ``cmd || rc=$?`` on one line.

Three layers, because a guard nobody has seen fail is decoration:

* a static sweep of every ``run:`` block under an errexit shell, discovered by glob
  and bound to a reach floor;
* a self-test on synthetic workflows proving the sweep flags both broken shapes and
  passes both correct ones;
* the three steps #16237 fixed, extracted from their workflows and RUN under GitHub's
  own shell with the interpreter replaced by a planted failure, beside controls that
  prove the same harness never reaches the capture in the pre-fix shape.

Not covered by the third layer: the parked-branch merger's capture, which sits inside
a loop over live git state. The static sweep covers it.

Out of scope: ``shell: sh`` also starts with ``-e``, and is skipped because no
workflow here uses it and it has no PIPESTATUS. Widen ``carries_errexit`` when one does.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # nosec B404  # running a step's script under bash -e IS the subject
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_REPO_ROOT = repo_root()

#: Discovered, never listed, so a workflow is swept the day it lands. Both
#: extensions, because GitHub loads both.
_WORKFLOW_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml")

#: An assignment from an exit status: `rc=$?`, `status="$?"`, `rc=${PIPESTATUS[0]}`,
#: `codes=("${PIPESTATUS[@]}")`. Any name, not only `rc` -- a first sweep keyed on
#: `rc=` found half of the captures in the tree (#16237).
_CAPTURE = re.compile(r"(?<![\w$])[A-Za-z_]\w*=\(?\"?\$(?:\?|\{\?\}|\{PIPESTATUS\b)")
#: A shell comment: `#` at the start of a line or after whitespace, so `${#arr[@]}` survives.
_COMMENT = re.compile(r"(?:^|\s)#.*$")
_SET_FLAGS = re.compile(r"[-+][A-Za-z]+")
_ERREXIT_FLAG = re.compile(r"-[A-Za-z]*e[A-Za-z]*")
#: `python` or `python3` in command position: the program a pinned step guards.
_INTERPRETER = re.compile(r"(?:^|[\s;&|(])(python3?)(?=\s)")
#: An event term of a reader gate, evaluated by `_evaluate`.
_EVENT_TERM = re.compile(r"github\.event_name (!=|==) '([\w-]+)'")
#: The term keeping a reader's issue steps out of pull-request runs (#16221).
_OFF_PULL_REQUEST = "github.event_name != 'pull_request'"


@dataclass(frozen=True)
class RunBlock:
    """One step's ``run:`` script, and what GitHub starts it with."""

    workflow: str
    job: str
    step: str
    shell: str | None
    script: str
    env: tuple[str, ...] = ()

    def where(self) -> str:
        return f"{self.workflow} job={self.job} step={self.step!r}"


def _defaults_shell(node: dict[str, Any]) -> str | None:
    run = (node.get("defaults") or {}).get("run") or {}
    return run.get("shell") if isinstance(run, dict) else None


def effective_shell(doc: dict[str, Any], job: dict[str, Any], step: dict[str, Any]) -> str | None:
    """The shell GitHub resolves: the step's, then the job's, then the workflow's default.

    ``None`` is GitHub's own default, ``bash -e {0}`` on Linux and macOS. On Windows
    that default is ``pwsh``, returned by name so it is not mistaken for bash.
    """
    for shell in (step.get("shell"), _defaults_shell(job), _defaults_shell(doc)):
        if shell:
            return str(shell)
    if "windows" in str(job.get("runs-on", "")).lower():
        return "pwsh"
    return None


def carries_errexit(shell: str | None) -> bool:
    """Whether GitHub starts *shell* with errexit on.

    The default and ``bash`` both do. A custom ``bash ... {0}`` template does only if
    it passes ``-e``. Everything else -- ``pwsh``, ``python``, ``sh`` -- is skipped.
    """
    if shell is None or shell == "bash":
        return True
    words = shell.split()
    return bool(words) and Path(words[0]).name == "bash" and any(_ERREXIT_FLAG.fullmatch(w) for w in words[1:])


def _env_keys(*scopes: dict[str, Any]) -> tuple[str, ...]:
    """Every env name the workflow, job and step declare; `set -u` needs them bound."""
    names = {str(key) for scope in scopes if isinstance(scope.get("env"), dict) for key in scope["env"]}
    return tuple(sorted(names))


def blocks_in(doc: dict[str, Any], workflow: str) -> list[RunBlock]:
    """Every step ``run:`` script in one parsed workflow."""
    found: list[RunBlock] = []
    for job_id, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for index, step in enumerate(job.get("steps") or []):
            if not (isinstance(step, dict) and isinstance(step.get("run"), str)):
                continue
            found.append(
                RunBlock(
                    workflow=workflow,
                    job=str(job_id),
                    step=str(step.get("id") or step.get("name") or index),
                    shell=effective_shell(doc, job, step),
                    script=step["run"],
                    env=_env_keys(doc, job, step),
                )
            )
    return found


def _load(path: Path) -> dict[str, Any]:
    """Parse a workflow. One that will not parse raises: a skip would read as clean."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def errexit_blocks(root: Path) -> list[RunBlock]:
    """The reach population: every run block under *root* whose shell carries errexit."""
    blocks: list[RunBlock] = []
    for path in sorted(p for pattern in _WORKFLOW_GLOBS for p in root.glob(pattern)):
        blocks.extend(blocks_in(_load(path), path.relative_to(root).as_posix()))
    return [block for block in blocks if carries_errexit(block.shell)]


#: MEASURED at e70d989a4 by parsing, not by grep: 335 run blocks in .github/workflows,
#: all 335 under an errexit shell (no workflow sets a non-bash `shell:`). The same count
#: was 265 on 2026-08-11 and 309 on 2026-08-26 -- about 70 a month -- so ordinary work
#: moves it, and `growth` covers roughly a month before the floor must be raised.
REACH = declare(
    "workflow-rc-capture",
    discover=errexit_blocks,
    floor=330,
    what="workflow run blocks under an errexit shell",
    growth=70,
)


def _errexit_after(segment: str, errexit: bool) -> bool:
    """errexit after one `;`-separated command, if that command is a `set`."""
    words = segment.split()
    if not words or words[0] != "set":
        return errexit
    rest = iter(words[1:])
    for word in rest:
        if word in ("-o", "+o"):
            if next(rest, "") == "errexit":
                errexit = word == "-o"
        elif _SET_FLAGS.fullmatch(word) and "e" in word:
            errexit = word.startswith("-")
    return errexit


def unguarded_captures(script: str) -> list[tuple[int, str]]:
    """``(line, text)`` of each exit-code capture errexit would abort before reaching.

    Guarded means errexit is off at that point -- a ``set +e`` earlier in the block
    with no ``set -e`` since -- or the capture is the right side of ``||`` on its own
    line, ``cmd || rc=$?``. Every other capture is flagged. The block is assumed to
    start with errexit on, which is what `carries_errexit` selected it for.
    """
    errexit = True
    found: list[tuple[int, str]] = []
    for number, line in enumerate(script.splitlines(), start=1):
        for segment in _COMMENT.sub("", line).split(";"):
            errexit = _errexit_after(segment.strip(), errexit)
            capture = _CAPTURE.search(segment)
            if capture and errexit and "||" not in segment[: capture.start()]:
                found.append((number, line.strip()))
    return found


def test_no_errexit_block_captures_an_exit_code_it_cannot_reach() -> None:
    """The property, over every run block in the tree."""
    blocks = REACH.examined(_REPO_ROOT)
    offenders = [
        f"{block.where()}, script line {number}: {text}"
        for block in blocks
        for number, text in unguarded_captures(block.script)
    ]
    REACH.completed(blocks)
    assert not offenders, (
        "these steps run under an errexit shell (no `shell:` key means `bash -e`, and "
        "`set -uo pipefail` does not clear -e), so a failing command before each capture "
        "aborts the step and the capture never runs:\n  "
        + "\n  ".join(offenders)
        + "\nCapture on the same line -- `rc=0`, then `cmd || rc=$?` -- or, around a pipeline "
        "whose PIPESTATUS you need, `set +e` before it and `set -e` after the capture. Not "
        "`|| true`: that runs `true` as a new pipeline and resets PIPESTATUS (#16237)."
    )


# --------------------------------------------------------------- the sweep can fail

_SHAPES_FIXTURE = """
jobs:
  linux:
    runs-on: ubuntu-latest
    steps:
      - id: bare
        run: |
          set -uo pipefail
          python3 tool.py >out.log 2>&1
          rc=$?
      - id: piped
        run: |
          set -uo pipefail
          python -m tool 2>&1 | tee out.txt
          rc=${PIPESTATUS[0]}
      - id: re-enabled
        shell: bash
        run: |
          set +e
          python -m tool 2>&1 | tee out.txt
          set -euo pipefail
          rc=${PIPESTATUS[0]}
      - id: lifted
        shell: bash
        run: |
          set -uo pipefail
          set +e
          python -m tool 2>&1 | tee out.txt
          rc=${PIPESTATUS[0]}
          set -e
      - id: or-capture
        run: |
          rc=0
          python3 tool.py >out.log 2>&1 || rc=$?
      - id: python-shell
        shell: python
        run: |
          rc=$?
  windows:
    runs-on: windows-latest
    steps:
      - id: pwsh-default
        run: |
          rc=$?
"""

_DEFAULTS_FIXTURE = """
defaults:
  run:
    shell: pwsh
jobs:
  inherits:
    runs-on: ubuntu-latest
    steps:
      - run: echo inherited
  overrides:
    runs-on: ubuntu-latest
    defaults:
      run:
        shell: bash
    steps:
      - run: echo overridden
"""


def test_the_sweep_flags_both_broken_shapes_and_passes_both_correct_ones() -> None:
    """The mutation proof: the sweep is shown each shape and must tell them apart."""
    blocks = {block.step: block for block in blocks_in(yaml.safe_load(_SHAPES_FIXTURE), "fixture.yml")}
    examined = {name for name, block in blocks.items() if carries_errexit(block.shell)}
    flagged = {name for name in examined if unguarded_captures(blocks[name].script)}
    assert examined == {"bare", "piped", "re-enabled", "lifted", "or-capture"}, examined
    # `re-enabled` restores errexit before its capture, so it is the bare shape again.
    assert flagged == {"bare", "piped", "re-enabled"}, flagged


def test_the_shell_is_resolved_the_way_github_resolves_it() -> None:
    shells = {block.job: block.shell for block in blocks_in(yaml.safe_load(_DEFAULTS_FIXTURE), "fixture.yml")}
    assert shells == {"inherits": "pwsh", "overrides": "bash"}, shells
    assert carries_errexit(None) and carries_errexit("bash") and carries_errexit("bash -e {0}")
    assert not carries_errexit("bash {0}") and not carries_errexit("pwsh") and not carries_errexit("python")


# ------------------------------------------------- the fixed steps, on their failing path


@dataclass(frozen=True)
class StepRun:
    exit_code: int
    output: str
    summary: str


def _planted(script: str, rc: int) -> str:
    """*script* with its one interpreter call shadowed by a function failing with *rc*.

    Shadowing, not rewriting the command line: the redirections, the pipeline, the
    continuation lines and the capture stay byte-for-byte what ships, and only the
    program's exit status is planted. Exactly one call is required, so the planted
    failure cannot land on a different command than the one the step guards.
    """
    code = "\n".join(_COMMENT.sub("", line) for line in script.splitlines())
    calls = _INTERPRETER.findall(code)
    assert len(calls) == 1, f"expected exactly one interpreter call to plant a failure on, found {calls}"
    return f"{calls[0]}() {{ echo planted-output; return {rc}; }}\n{script}"


def _bash_argv(shell: str | None, script_path: Path) -> list[str]:
    """GitHub's invocation: `bash -e {0}` by default, the `bash` template otherwise."""
    bash = shutil.which("bash")
    assert bash, "bash is not on PATH, so the failing-path proof cannot run"
    flags = ["-e"] if shell is None else ["--noprofile", "--norc", "-eo", "pipefail"]
    return [bash, *flags, str(script_path)]


def _run_under_errexit(script: str, shell: str | None, env_keys: tuple[str, ...], tmp: Path) -> StepRun:
    """Run *script* as GitHub would, with its runner files pointed into *tmp*."""
    output, summary, runner_temp = tmp / "github_output", tmp / "step_summary", tmp / "runner_temp"
    output.touch()
    summary.touch()
    runner_temp.mkdir()
    env = {key: "planted" for key in env_keys}
    env.update(PATH=os.environ.get("PATH", ""), HOME=str(tmp), RUNNER_TEMP=str(runner_temp))
    env.update(GITHUB_OUTPUT=str(output), GITHUB_STEP_SUMMARY=str(summary))
    script_path = tmp / "step.sh"
    script_path.write_text(script, encoding="utf-8")
    done = subprocess.run(  # nosec B603  # fixed interpreter, a script this test wrote
        _bash_argv(shell, script_path),
        cwd=tmp,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    return StepRun(done.returncode, output.read_text(encoding="utf-8"), summary.read_text(encoding="utf-8"))


#: `(workflow, text the step's command contains, planted exit code, where rc surfaces)`.
#: Selected by what the step RUNS, so a rename still finds it. "output": the step
#: records rc for a reader step and itself succeeds. "exit": the step reports rc in
#: its summary and exits with it. The watchdog plants 2 because that is the code its
#: classifier reserves as un-suppressible -- the one the abort was hiding.
_PINNED_STEPS = (
    (".github/workflows/import-hermeticity-sweep.yml", "repo_tests/import_hermeticity_test.py", 3, "output"),
    (".github/workflows/ratchet-base-guard.yml", "--audit-ceilings", 3, "output"),
    (".github/workflows/ci-dispatch-watchdog.yml", "pipeline-scripts/ci_red_cause.py", 2, "exit"),
)


def _pinned(workflow: str, marker: str) -> RunBlock:
    """The one run step in *workflow* whose script contains *marker*."""
    matches = [block for block in blocks_in(_load(_REPO_ROOT / workflow), workflow) if marker in block.script]
    assert len(matches) == 1, f"{workflow}: expected one run step containing {marker!r}, found {len(matches)}"
    assert matches[0].shell in (None, "bash"), f"{matches[0].where()} runs under {matches[0].shell!r}"
    return matches[0]


def _steps(doc: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = [job for job in (doc.get("jobs") or {}).values() if isinstance(job, dict)]
    return [step for job in jobs for step in (job.get("steps") or []) if isinstance(step, dict)]


def _terms(step: dict[str, Any]) -> list[str]:
    """The `&&` terms of a step's `if:`."""
    return [term.strip() for term in str(step.get("if", "")).split("&&")]


def _script(step: dict[str, Any]) -> str:
    return str((step.get("with") or {}).get("script", ""))


def _evaluate(term: str, step_id: str, rc: str, event: str) -> bool:
    """One `if:` term, for an *event* run whose step *step_id* succeeded and wrote *rc*.

    Only the terms the reader gates use are understood. Any other fails the test
    rather than being guessed at.
    """
    if term == "success()":
        return True
    rc_term = re.fullmatch(rf"steps\.{re.escape(step_id)}\.outputs\.rc (!=|==) '0'", term)
    if rc_term:
        return (rc != "0") is (rc_term.group(1) == "!=")
    event_term = _EVENT_TERM.fullmatch(term)
    assert event_term, f"cannot evaluate the gate term {term!r}; extend _evaluate rather than guess"
    return (event != event_term.group(2)) is (event_term.group(1) == "!=")


def _assert_the_reader_fires(workflow: str, step_id: str, rc: str, event: str = "schedule") -> None:
    """Evaluate the rc-gated issue steps for a step that succeeded and wrote *rc*.

    *event* is any trigger but pull_request -- the only runs whose issue steps act.
    The violation reader must fire and the clean-path closer must not.
    """
    fired: dict[str, bool] = {}
    for step in _steps(_load(_REPO_ROOT / workflow)):
        if f"steps.{step_id}.outputs.rc" in str(step.get("if", "")) and "github-script" in str(step.get("uses", "")):
            fired[str(step.get("name"))] = all(_evaluate(term, step_id, rc, event) for term in _terms(step))
    assert True in fired.values(), f"{workflow}: no reader step fires on rc={rc}: {fired}"
    assert False in fired.values(), f"{workflow}: no issue step is gated on the clean path: {fired}"


@pytest.mark.parametrize(
    ("workflow", "marker", "planted", "surface"),
    [pytest.param(*row, id=Path(row[0]).stem) for row in _PINNED_STEPS],
)
def test_a_fixed_step_surfaces_its_exit_code_on_the_failing_path(
    workflow: str, marker: str, planted: int, surface: str, tmp_path: Path
) -> None:
    """The shipped script, its program failing, under GitHub's own shell."""
    block = _pinned(workflow, marker)
    run = _run_under_errexit(_planted(block.script, planted), block.shell, block.env, tmp_path)
    if surface == "exit":
        # The exit code alone proves nothing: errexit also exits with it. The summary
        # line is written only if the capture ran.
        assert run.exit_code == planted, f"{block.where()} exited {run.exit_code}, not {planted}"
        assert f"exit={planted}" in run.summary and "planted-output" in run.summary, run.summary
        return
    assert run.exit_code == 0, f"{block.where()} aborted with {run.exit_code}, so its readers are skipped"
    assert f"rc={planted}" in run.output.splitlines(), f"{block.where()} never wrote rc: {run.output!r}"
    assert "planted-output" in run.output, "the report handed to the reader lost the command's output"
    _assert_the_reader_fires(workflow, block.step, str(planted))


#: Synthetic, so the harness is proved on shapes whose answer is known:
#: `(script, reaches its capture when the command fails)`.
_CONTROL_SHAPES = {
    "bare-then-capture": ("set -uo pipefail\npython3 tool.py >out.log 2>&1\nrc=$?\n", False),
    "pipeline-then-pipestatus": (
        "set -uo pipefail\npython -m tool 2>&1 | tee out.txt\nrc=${PIPESTATUS[0]}\n",
        False,
    ),
    "errexit-lifted": (
        "set -uo pipefail\nset +e\npython -m tool 2>&1 | tee out.txt\nrc=${PIPESTATUS[0]}\nset -e\n",
        True,
    ),
    "or-capture": ("set -uo pipefail\nrc=0\npython3 tool.py >out.log 2>&1 || rc=$?\n", True),
}
_RECORD_RC = 'echo "rc=${rc}" >>"$GITHUB_OUTPUT"\n'


@pytest.mark.parametrize("shape", sorted(_CONTROL_SHAPES))
def test_the_harness_separates_the_pre_fix_shape_from_the_fixed_ones(shape: str, tmp_path: Path) -> None:
    """The control: the pre-fix shape must NOT reach its capture in the same harness.

    Without it, a harness that silently disabled errexit would pass every fixed step
    above for the wrong reason. The static sweep is held to bash's verdict here too.
    """
    script, reaches = _CONTROL_SHAPES[shape]
    run = _run_under_errexit(_planted(script + _RECORD_RC, 3), None, (), tmp_path)
    assert ("rc=3" in run.output.splitlines()) is reaches, (shape, run)
    assert run.exit_code == (0 if reaches else 3), (shape, run.exit_code)
    assert bool(unguarded_captures(script)) is (not reaches), f"{shape}: the static sweep disagrees with bash"


# --------------------------------------------------------- the readers select on rc

#: `(workflow, id of the step that captures rc)` for the two workflows whose issue
#: steps are the only reader of a failure.
_READERS = (
    (".github/workflows/import-hermeticity-sweep.yml", "sweep"),
    (".github/workflows/ratchet-base-guard.yml", "audit"),
)


@pytest.mark.parametrize(("workflow", "step_id"), _READERS, ids=[Path(w).stem for w, _ in _READERS])
def test_each_reader_selects_on_rc_and_a_failure_still_reaches_one(workflow: str, step_id: str) -> None:
    """Offenders to one issue, a guard that never finished to another (#16237).

    The `failure()` reader must come BEFORE the step that fails the run on purpose,
    or it would fire on every real violation too and file it as "could not run".
    """
    steps = _steps(_load(_REPO_ROOT / workflow))
    rc_ref = f"steps.{step_id}.outputs.rc"
    files_issue = ["issues.create({" in _script(step) for step in steps]
    readers = [i for i, step in enumerate(steps) if f"{rc_ref} != '0'" in _terms(step) and files_issue[i]]
    closers = [step for step in steps if f"{rc_ref} == '0'" in _terms(step)]
    fallback = [i for i, step in enumerate(steps) if "failure()" in _terms(step) and files_issue[i]]
    fail_run = [
        i for i, step in enumerate(steps) if f"{rc_ref} != '0'" in _terms(step) and "exit 1" in str(step.get("run"))
    ]
    assert readers, f"{workflow}: no issue step is gated on {rc_ref} != '0'"
    assert closers, f"{workflow}: nothing closes the issue on {rc_ref} == '0'"
    assert fallback, f"{workflow}: no `if: failure()` issue step, so a step that aborts reaches no reader"
    assert fail_run and max(fallback) < min(
        fail_run
    ), f"{workflow}: the failure() reader must come before the step that fails the run on purpose"


def test_a_pull_request_sweep_reports_through_its_check_never_through_an_issue() -> None:
    """The sweep also runs on pull_request, because a schedule runs the DEFAULT branch's
    copy of a workflow and that copy does not carry this one (#16221). A PR run must
    leave the issues alone -- they describe the base, not a diff that may never merge --
    and must still fail its own check on offenders.
    """
    workflow = ".github/workflows/import-hermeticity-sweep.yml"
    doc = _load(_REPO_ROOT / workflow)
    assert "pull_request" in (doc.get(True) or doc.get("on") or {}), f"{workflow} no longer runs on pull_request"
    steps = _steps(doc)
    touches_issues = [step for step in steps if "github.rest.issues." in _script(step)]
    fail_run = [
        step for step in steps if "exit 1" in str(step.get("run")) and "steps.sweep.outputs.rc != '0'" in _terms(step)
    ]
    assert touches_issues, f"{workflow}: no issue step found, so there is nothing to keep off pull_request"
    leaking = [str(step.get("name")) for step in touches_issues if _OFF_PULL_REQUEST not in _terms(step)]
    assert not leaking, f"{workflow}: these steps can touch an issue from a pull-request run: {leaking}"
    assert fail_run and all(
        _OFF_PULL_REQUEST not in _terms(step) for step in fail_run
    ), f"{workflow}: the step failing the run on offenders must still fire on pull_request"
