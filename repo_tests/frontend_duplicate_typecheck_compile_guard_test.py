# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No CI job may compile the same vue-tsc project more than once (#14481).

`frontend-test.yml`'s `unit-tests` job used to run `vue-tsc --noEmit -p
tsconfig.app.json` twice: once directly (`npm run type-check`) and once more
inside `check-ts-delta.sh` (`npm run check-ts-delta`). The first compile took
215s; the second, running while the runner was busy, exceeded its 600s budget
and was killed — reddening the required "Unit & Integration Tests" context
with no failing test and no error output (#14481).

This guard scans every job in every workflow for *unconditional* vue-tsc
compile invocations, resolving one hop of `npm run <script>` indirection
through the relevant `package.json` and, where a resolved command shells out
to a repo-local `*.sh` file, reading that file too — because the duplicate
compile in #14481 was one hop removed from the workflow YAML itself (behind
`npm run check-ts-delta` -> `scripts/check-ts-delta.sh`), so a check that only
looked at the workflow text would have missed it entirely, exactly as it did
before this guard existed.

A compile invocation found inside `check-ts-delta.sh`'s documented reuse
fallback (the `else` branch guarded on `TSC_OUTPUT_FILE`/`TSC_STATUS_FILE`
being pre-supplied) does not count: that branch only runs when no prior step
in the job captured a compile for it to reuse, which is a *different* compile
site, not a second one. The discriminator is structural (an `else` following
a mention of the reuse marker), not the literal step names — a rename of
"type-check" or "check-ts-delta" must not blind this guard.

Discrimination this guard must show: `test_no_job_compiles_...` PASSES
against the workflow and script as they stand now (one compile site in
`unit-tests`: `type-check`'s direct call — `check-ts-delta`'s own compile
line only exists inside the guarded fallback). `test_the_pre_fix_shape_...`
proves the counting primitive itself FAILS the pre-#14481 shape — the same
two call sites the issue names (frontend-test.yml:132 and
check-ts-delta.sh's then-unconditional compile block) — so a future edit
that quietly removes the discrimination cannot pass unnoticed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflows")

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# Matches a line that actually RUNS the compiler against a tsconfig project —
# either the literal `vue-tsc` command, or the resolved-binary-path idiom this
# repo uses instead of `npx` (`"$TSC_BIN"` / `"${TSC_BIN}"`, see
# autobot-frontend/scripts/check-ts-delta.sh). A bare assignment such as
# `TSC_BIN=".../vue-tsc"` has neither `--noEmit` nor `-p <tsconfig>` on the
# same line, so it is not a match — this only fires on an actual invocation.
COMPILE_PATTERN = re.compile(
    r'(?:\bvue-tsc\b|"\$\{?TSC_BIN\}?")[^\n]*--noEmit[^\n]*-p\s+\S*tsconfig'
)

# The marker two cooperating steps use to hand off a captured compile instead
# of running a second one (the #14481 fix's reuse contract). A compile line
# reachable only through the `else` of a conditional guarded on this name is
# the documented "no prior capture available" fallback, not a second,
# unconditional compile.
REUSE_MARKER = "TSC_OUTPUT_FILE"

NPM_RUN_RE = re.compile(r"npm run(?:-script)?\s+([\w:.-]+)")
SH_PATH_RE = re.compile(r"[\w./-]+\.sh\b")


def _load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


def _package_scripts(working_directory: str) -> dict:
    pkg_path = (REPO_ROOT / working_directory / "package.json").resolve()
    if not pkg_path.is_file():
        return {}
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data.get("scripts") or {}


def _working_directory_for(job: dict, step: dict) -> str:
    if step.get("working-directory"):
        return step["working-directory"]
    defaults = (job.get("defaults") or {}).get("run") or {}
    return defaults.get("working-directory") or "."


def _executable_lines(text: str) -> str:
    """Drop lines that only PRINT a command name, never run it.

    Several workflows tell the operator what to run locally inside an `echo`
    (e.g. frontend-typecheck-regression.yml prints "Run `npm run type-check`
    ... to inspect") — a real command word inside a string literal, not an
    invocation. Without this, resolving `npm run <script>` against such a
    line would credit that job with a compile it never runs, hiding a real
    duplicate under a false one.
    """
    return "\n".join(
        line
        for line in text.splitlines()
        if not line.strip().startswith(("echo", "printf"))
    )


def _unguarded_compile_count(text: str) -> int:
    """Count compile-pattern matches not reached only via the reuse fallback."""
    reuse_idx = text.find(REUSE_MARKER)
    guard_start = text.find("else", reuse_idx) if reuse_idx != -1 else -1
    count = 0
    for match in COMPILE_PATTERN.finditer(text):
        if guard_start != -1 and match.start() > guard_start:
            continue
        count += 1
    return count


def _texts_for_step(job: dict, step: dict) -> list[str]:
    """The step's own script plus anything it delegates to, one hop deep."""
    run_text = step.get("run")
    if not isinstance(run_text, str):
        return []

    working_directory = _working_directory_for(job, step)
    scripts = _package_scripts(working_directory)

    texts = [run_text]
    for script_name in NPM_RUN_RE.findall(_executable_lines(run_text)):
        script_value = scripts.get(script_name)
        if script_value:
            texts.append(script_value)

    sh_paths: set[str] = set()
    for text in texts:
        sh_paths.update(SH_PATH_RE.findall(text))
    for rel_path in sh_paths:
        sh_file = (REPO_ROOT / working_directory / rel_path).resolve()
        if sh_file.is_file():
            try:
                texts.append(sh_file.read_text(encoding="utf-8"))
            except OSError:
                pass

    return texts


def _compile_site_count(job: dict) -> int:
    total = 0
    for step in job.get("steps") or []:
        for text in _texts_for_step(job, step):
            total += _unguarded_compile_count(text)
    return total


def _all_jobs() -> list[tuple[str, str, dict]]:
    """(workflow filename, job key, job dict) for every job in every workflow."""
    found = []
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        doc = _load_yaml(path)
        for job_key, job in (doc.get("jobs") or {}).items():
            if isinstance(job, dict):
                found.append((path.name, job_key, job))
    return found


def _unit_tests_job() -> dict:
    for workflow_name, job_key, job in _all_jobs():
        if workflow_name == "frontend-test.yml" and job_key == "unit-tests":
            return job
    raise AssertionError("frontend-test.yml no longer has a job keyed 'unit-tests'")


def test_the_scan_actually_finds_jobs():
    """An empty scan would make every assertion below vacuous."""
    jobs = _all_jobs()
    assert len(jobs) >= 10, f"only {len(jobs)} job(s) found — the scan is broken"


def test_the_scan_actually_resolves_the_check_ts_delta_script():
    """Prove the one-hop npm-script + .sh-file resolution really fires.

    Without this, a path or regex typo could make `_texts_for_step` silently
    return only the step's own `run:` text forever, and every assertion below
    would still "pass" without ever having looked at check-ts-delta.sh.
    """
    job = _unit_tests_job()
    delta_step = next(
        s for s in job["steps"] if s.get("name") == "Check TypeScript error delta"
    )
    texts = _texts_for_step(job, delta_step)
    assert len(texts) >= 2, (
        "resolving 'npm run check-ts-delta' should yield the step's own run text "
        "plus the resolved package.json script value at minimum"
    )
    combined = "\n".join(texts)
    assert "vue-tsc" in combined, (
        "the resolved texts never reached scripts/check-ts-delta.sh's own "
        "content — the .sh-file hop is not firing, so this guard cannot see "
        "the duplicate compile it exists to catch"
    )
    assert REUSE_MARKER in combined, (
        f"scripts/check-ts-delta.sh no longer mentions {REUSE_MARKER} — either "
        "the #14481 reuse contract was removed (reintroducing the duplicate "
        "compile) or renamed without updating this guard's REUSE_MARKER"
    )


def test_no_job_compiles_the_same_vue_tsc_project_more_than_once():
    violations = {}
    for workflow_name, job_key, job in _all_jobs():
        count = _compile_site_count(job)
        if count > 1:
            violations[f"{workflow_name}:{job_key}"] = count

    assert not violations, (
        f"job(s) compile the same vue-tsc project more than once per run: "
        f"{violations}. Each extra compile is redundant, expensive work that "
        f"can time out under runner load while producing no new signal "
        f"(#14481) — share one compile's output between steps instead of "
        f"invoking vue-tsc again."
    )


# Verbatim shape of scripts/check-ts-delta.sh's compile block as it stood
# before #14481 (see git blame / issue #14481 for the original file): always
# ran the compiler, with no reuse marker anywhere in the script.
_PRE_FIX_CHECK_TS_DELTA_SH = """
TSC_BIN="${FRONTEND_DIR}/node_modules/.bin/vue-tsc"
if [[ ! -x "${TSC_BIN}" ]]; then
  echo "ERROR: vue-tsc not found at ${TSC_BIN}" >&2
  exit 1
fi

echo "Running vue-tsc (baseline: ${BASELINE} errors)..."
TSC_OUTPUT="$(mktemp)"
trap 'rm -f "${TSC_OUTPUT}"' EXIT

TSC_STATUS=0
(
  cd "${FRONTEND_DIR}"
  "${TSC_BIN}" --noEmit -p tsconfig.app.json
) >"${TSC_OUTPUT}" 2>&1 </dev/null || TSC_STATUS=$?
"""

# Verbatim shape of frontend-test.yml's `type-check` step before #14481
# (find it by that step name -- the line moved to :156-162 while this said
# :132, which is now an unrelated `env:` block): `npm run type-check`,
# resolving through
# package.json to this — unchanged by the fix, since `type-check` was never
# the redundant half.
_PRE_FIX_TYPE_CHECK_RESOLVED = "vue-tsc --noEmit -p tsconfig.app.json"


def test_the_pre_fix_shape_fails_the_same_guard():
    """Discrimination check: the counting primitive must catch the #14481 bug.

    Feeds the exact pre-fix shapes of both call sites the issue names —
    `type-check`'s resolved command and check-ts-delta.sh's then-unconditional
    compile block, which had no TSC_OUTPUT_FILE reuse marker at all — through
    the identical `_unguarded_compile_count` primitive the guard above uses.
    If this ever reports <= 1, the primitive has stopped discriminating and
    `test_no_job_compiles_the_same_vue_tsc_project_more_than_once` would pass
    a real regression.
    """
    assert REUSE_MARKER not in _PRE_FIX_CHECK_TS_DELTA_SH, (
        "the fixture claiming to be the PRE-fix script accidentally contains "
        "the reuse marker — it would no longer exercise the unguarded path"
    )

    count = _unguarded_compile_count(
        _PRE_FIX_TYPE_CHECK_RESOLVED
    ) + _unguarded_compile_count(_PRE_FIX_CHECK_TS_DELTA_SH)

    assert count > 1, (
        f"expected the pre-#14481 shape to register more than one unguarded "
        f"compile site (it ran vue-tsc twice, unconditionally); got {count}. "
        f"The discriminator no longer catches the bug it was written for."
    )
