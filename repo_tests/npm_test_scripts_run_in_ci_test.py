# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every declared npm test runner must be invoked by some workflow (#15667).

`autobot-slm-frontend` declared `"test:unit": "vitest run"` and carried 53
vitest files. `slm-frontend-check.yml` ran type-check, lint and build; every
`vitest` / `test:unit` reference in the other workflows belonged to
`autobot-frontend`, a different app. An entire app's unit suite had been inert
since it was written, and the outside view was a green check.

That is the third occurrence of one shape in this repository:

* #15051 — `pytest.ini` testpaths: 17 test functions ran in no workflow.
* #15619 — the background-task ratchet: 3,914 files, the larger of two backends.
* #15667 — the SLM frontend workflow: 53 vitest files, an entire app.

Each time the check reported on what it *reached*, and nothing checked its
reach. `hook_suites_run_in_ci_test.py` and `collection_coverage_test.py` close
that class on the Python side; this module is its JavaScript half.

Every test-shaped script in a tracked `package.json` must be invoked by a
workflow or a composite action, or be listed in ``UNINVOKED_TEST_SCRIPTS`` with
a reason and the issue number that expires the entry. Two kinds of script are
excluded by their *command*, not by their name, so the classification survives
a rename:

* **interactive modes** — watchers, `--ui`, `--headed`, `show-report`,
  `--update-snapshots`, `cypress open`, `vite dev`. These must not run in CI.
* **pure delegation** — `run-s a b c`, `npm run a && npm run b`. They declare no
  suite of their own; every suite they name is checked on its own row.
* **npm-init placeholders** — `echo "Error: no test specified" && exit 1`.

The allowlist records the status quo as measured; a reason string is not an
endorsement. A package whose every runner is allowlisted is a whole app gated by
nothing — the #15667 shape — so those are counted separately against a
DOWN-ONLY ceiling.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from autobot_shared.paths import GitRepoRootUnavailable, git_repo_root, scrubbed_git_env

#: A script name this repository treats as a test runner: `test` or `test:*`.
TEST_SCRIPT_NAME = re.compile(r"^test(?::|$)")

#: Command shapes that are developer-only modes. `vitest` without `run` is the
#: watcher, which is why the first alternative is a negative lookahead rather
#: than a name check: `test`, `test:unit:watch` and `test:coverage:ui` all spell
#: the same watcher and only one of them says so in its name.
#: The `vitest` alternative deliberately refuses to match inside a filename:
#: `vitest run --config vitest.integration.config.ts` names the watcher twice,
#: and matching the second occurrence classified the integration suite -- which
#: CI does run -- as a developer-only mode.
INTERACTIVE_BODY = re.compile(
    r"(?<![\w./-])vitest(?![\w./-])(?![^&|;]*\brun\b)"
    r"|--watch\b|--ui\b|--headed\b|--update-snapshots\b"
    r"|\bshow-report\b|\bcypress\s+open\b|\bvite\s+dev\b"
)

#: `npm run X`, `pnpm run X`, `yarn X`, and the npm-run-all spellings.
DELEGATION = re.compile(
    r"(?:npm|pnpm|yarn|bun)\s+run\s+([A-Za-z0-9_.:@/-]+)" r"|(?:^|\s)(?:run-s|run-p|npm-run-all)\s+([^&|;]+)"
)

#: The npm-init stub. Not a suite, and gating it would only ever fail.
PLACEHOLDER_BODY = re.compile(r"^echo\s+[\"']?Error: no test specified")

#: An npm/yarn/pnpm script invocation inside a workflow `run:` block.
SCRIPT_CALL = re.compile(r"(?<![\w./-])(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?([A-Za-z0-9_.:@/-]+)")

#: Subcommands that are package management, not script invocation.
NOT_A_SCRIPT = frozenset(
    {
        "install",
        "ci",
        "exec",
        "install-deps",
        "cache",
        "config",
        "set",
        "audit",
        "pkg",
        "version",
        "list",
        "ls",
        "add",
        "remove",
        "link",
        "--",
    }
)

#: `<package dir>::<script>` -> the DECISION taken, and the issue that expires
#: the entry. Every reason must name an issue number: "nothing runs it" is a
#: description of the defect, not a decision about it.
UNINVOKED_TEST_SCRIPTS = {
    ".mcp::test": (
        "#15674 -- WIRE IN. `node --test autobot-mcp-server.test.js`, invoked by " "no workflow and no composite action"
    ),
    "autobot-browser-worker::test": (
        "#15675 -- WIRE IN, after browser provisioning. `npx playwright test` "
        "needs `playwright install --with-deps` on the runner; visual-regression.yml "
        "already carries that pattern to mirror"
    ),
    "autobot-frontend::test:unit": (
        "#10365 -- COVERED ELSEWHERE. frontend-test.yml runs `test:coverage`, which "
        "is `vitest run --coverage` over the same default config, so a separate "
        "`test:unit` step would run every unit test twice. The suite IS gated; only "
        "this spelling of it is not"
    ),
    "autobot-frontend::test:e2e": (
        "#15679 -- DECISION OUTSTANDING. `cypress run --e2e` behind "
        "start-server-and-test, invoked by nothing; whether cypress is superseded by "
        "the playwright suites is the open question, not a wiring fix"
    ),
    "autobot-frontend::test:playwright": (
        "#15679 -- WIRE IN. `playwright test`, invoked by nothing, while "
        "visual-regression.yml proves the playwright runner already works here"
    ),
    "autobot-infrastructure/shared/ide-extensions/vscode-autobot::test": (
        "#15678 -- WIRE IN, after harness provisioning. `node ./out/test/runTest.js` "
        "downloads VS Code and needs a virtual display, so it is a job rather than a step"
    ),
    "autobot-infrastructure/shared/mcp/tools/mcp-structured-thinking::test": (
        "#15677 -- WIRE IN. jest under --experimental-vm-modules, invoked by nothing; "
        "the Python half of this same tree is #15178"
    ),
    "autobot-infrastructure/shared/mcp/tools/mcp-structured-thinking::test:integration": (
        "#15677 -- WIRE IN. The integration half of the same jest suite"
    ),
    "libs/autobot-sdk-ts::test": (
        "#15676 -- WIRE IN. jest, invoked by nothing. marker-tests.yml reaches `libs` "
        "for its PYTHON marker-selected suite only; the TypeScript SDK's own suite "
        "has no runner"
    ),
}

#: DOWN-ONLY ceiling on packages whose EVERY runner is allowlisted -- a whole
#: app gated by nothing, which is exactly the #15667 shape. Measured on
#: Dev_new_gui: .mcp, autobot-browser-worker, vscode-autobot,
#: mcp-structured-thinking, libs/autobot-sdk-ts. NEVER raise this to make a new
#: app pass; wire the app in, or this guard has become the thing it replaced.
MAX_WHOLLY_UNGATED_PACKAGES = 5

#: Floors, so a regex that stops matching turns this module red instead of green
#: (the #15018 lesson: a guard that enumerates nothing passes comfortably).
#: Measured on Dev_new_gui: 7 packages declaring 13 runners between them, and
#: 15 npm script invocations resolved to a tracked package directory. The floors
#: sit below those so a package removal does not fail the guard, while a
#: scanner that has stopped reaching the tree still does.
MIN_PACKAGES_WITH_TEST_SCRIPTS = 6
MIN_RUNNER_SCRIPTS = 10
MIN_WORKFLOW_INVOCATIONS = 3

#: Invocations that must be visible to the scanner, covering both spellings this
#: repository uses: `working-directory:` and an in-line `cd`.
REQUIRED_DETECTIONS = (
    "autobot-frontend::test:coverage",
    "autobot-frontend::test:integration",
    "autobot-frontend::test:visual",
    "autobot-slm-frontend::test:unit",
)


def repo_root() -> Path:
    """Repository root via git, or a skip when this is not a git checkout."""
    try:
        return git_repo_root(Path(__file__).resolve().parent)
    except GitRepoRootUnavailable:
        pytest.skip("not a git checkout -- this check enumerates tracked files")


def tracked_package_files(root: Path) -> list[Path]:
    """Tracked `package.json` files, vendored trees excluded."""
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "*package.json"],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout.split()
    return [root / rel for rel in out if "node_modules" not in rel]


def delegates(body: str) -> set[str]:
    """Sibling script names a script body chains to."""
    found: set[str] = set()
    for match in DELEGATION.finditer(body):
        if match.group(1):
            found.add(match.group(1))
        elif match.group(2):
            found.update(match.group(2).split())
    return {name for name in found if not name.startswith("-")}


#: Tokens that carry no suite of their own, so a body made only of these plus
#: sibling script names is a wrapper rather than a runner.
_DELEGATION_NOISE = frozenset({"run-s", "run-p", "npm-run-all", "npm", "pnpm", "yarn", "bun", "run", "&&"})


def is_pure_delegation(body: str) -> bool:
    """True when a script only chains sibling scripts (`run-s a b c`)."""
    targets = delegates(body)
    return bool(targets) and (set(body.split()) - _DELEGATION_NOISE) <= targets


def is_runner(name: str, body: str) -> bool:
    """True when a script declares a suite CI is expected to gate."""
    if not TEST_SCRIPT_NAME.match(name):
        return False
    if PLACEHOLDER_BODY.match(body.strip()) or INTERACTIVE_BODY.search(body):
        return False
    # Pure delegation declares no suite of its own; its targets carry their own
    # rows, so gating the wrapper would double-count them.
    return not is_pure_delegation(body)


def declared_runners(root: Path) -> dict[str, dict[str, str]]:
    """`<package dir>` -> `{script: body}` for every runner it declares."""
    declared: dict[str, dict[str, str]] = {}
    for path in tracked_package_files(root):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        scripts = manifest.get("scripts") or {}
        runners = {n: b for n, b in scripts.items() if isinstance(b, str) and is_runner(n, b)}
        if runners:
            declared[path.parent.relative_to(root).as_posix()] = runners
    return declared


def yaml_sources(root: Path) -> list[Path]:
    """Every file that could invoke an npm script in CI."""
    roots = (root / ".github" / "workflows", root / ".github" / "actions")
    return sorted(
        path
        for base in roots
        if base.is_dir()
        for path in base.rglob("*")
        if path.suffix in (".yml", ".yaml") and path.is_file()
    )


def _run_steps(document: object) -> list[tuple[str | None, dict]]:
    """`(job working-directory, step)` pairs from a workflow or composite action."""
    if not isinstance(document, dict):
        return []
    pairs: list[tuple[str | None, dict]] = []
    for job in (document.get("jobs") or {}).values():
        if not isinstance(job, dict):
            continue
        default = ((job.get("defaults") or {}).get("run") or {}).get("working-directory")
        pairs += [(default, s) for s in (job.get("steps") or []) if isinstance(s, dict)]
    runs = document.get("runs")
    if isinstance(runs, dict):
        pairs += [(None, s) for s in (runs.get("steps") or []) if isinstance(s, dict)]
    return pairs


def _normalise(directory: str | None) -> str:
    return "." if directory in (None, "", ".") else Path(directory).as_posix().strip("/")


def _resolve_cd(current: str, target: str) -> str:
    if target.startswith("/") or "${{" in target:
        return _normalise(target)
    return _normalise(target if current == "." else str(Path(current) / target))


def _calls_in_step(working_directory: str, run: str) -> set[str]:
    """`<dir>::<script>` keys a single `run:` block invokes."""
    current, found = working_directory, set()
    for line in run.splitlines():
        line = line.strip()
        change = re.match(r"cd\s+([^\s;&|]+)", line)
        if change:
            current = _resolve_cd(current, change.group(1))
            continue
        found |= {f"{current}::{m.group(1)}" for m in SCRIPT_CALL.finditer(line) if m.group(1) not in NOT_A_SCRIPT}
    return found


def workflow_invocations(root: Path) -> set[str]:
    """`<dir>::<script>` keys invoked by any workflow or composite action."""
    invoked: set[str] = set()
    for path in yaml_sources(root):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:  # a malformed workflow is its own failure
            pytest.fail(f"{path.relative_to(root)} is not parseable YAML: {exc}")
        for default_directory, step in _run_steps(document):
            run = step.get("run")
            if isinstance(run, str):
                directory = _normalise(step.get("working-directory") or default_directory)
                invoked |= _calls_in_step(directory, run)
    return invoked


def covered_scripts(runners: dict[str, dict[str, str]], invoked: set[str]) -> set[str]:
    """Invoked keys, closed over delegation (`test:all` gates what it chains to)."""
    covered = {key for key in invoked if key.split("::", 1)[0] in runners}
    for directory, scripts in runners.items():
        for name, body in scripts.items():
            if f"{directory}::{name}" in invoked:
                covered |= {f"{directory}::{d}" for d in delegates(body)}
    return covered


@pytest.fixture(scope="module")
def measurement() -> tuple[dict[str, dict[str, str]], set[str]]:
    root = repo_root()
    return declared_runners(root), workflow_invocations(root)


def test_enumeration_is_not_vacuous(measurement) -> None:
    """A scanner that finds nothing must fail, not pass (#15018)."""
    runners, invoked = measurement
    assert len(runners) >= MIN_PACKAGES_WITH_TEST_SCRIPTS, (
        f"only {len(runners)} tracked package.json files declare a test runner; "
        "the enumerator has stopped reaching them"
    )
    declared = sum(len(scripts) for scripts in runners.values())
    assert declared >= MIN_RUNNER_SCRIPTS, (
        f"only {declared} test runner scripts found across those manifests; "
        "TEST_SCRIPT_NAME or is_runner has stopped classifying them"
    )
    assert len(invoked) >= MIN_WORKFLOW_INVOCATIONS, (
        f"only {len(invoked)} npm script invocations found across the workflow tree; "
        "SCRIPT_CALL or the YAML walk has stopped matching"
    )


def test_known_invocations_are_detected(measurement) -> None:
    """The scanner sees both spellings of a scoped invocation this repo uses."""
    runners, invoked = measurement
    missing = sorted(k for k in REQUIRED_DETECTIONS if k not in covered_scripts(runners, invoked))
    assert not missing, (
        "these invocations exist in the workflow tree but the scanner no longer sees "
        f"them, so its verdict is worthless: {missing}"
    )


def test_every_test_script_is_invoked_by_a_workflow(measurement) -> None:
    """The #15667 assertion: a declared runner that nothing runs is a defect."""
    runners, invoked = measurement
    covered = covered_scripts(runners, invoked)
    unaccounted = sorted(
        key
        for directory, scripts in runners.items()
        for key in (f"{directory}::{n}" for n in scripts)
        if key not in covered and key not in UNINVOKED_TEST_SCRIPTS
    )
    assert not unaccounted, (
        "these package.json test runners are invoked by no workflow and no composite "
        "action -- wire them into CI, or record the decision (with an issue number) in "
        f"UNINVOKED_TEST_SCRIPTS: {unaccounted}"
    )


def test_allowlist_entries_are_live_and_carry_an_issue(measurement) -> None:
    """An entry that no longer describes a gap must be deleted, not left to rot."""
    runners, invoked = measurement
    covered = covered_scripts(runners, invoked)
    declared = {f"{d}::{n}" for d, scripts in runners.items() for n in scripts}
    stale = sorted(k for k in UNINVOKED_TEST_SCRIPTS if k not in declared or k in covered)
    assert not stale, f"UNINVOKED_TEST_SCRIPTS entries no longer describe an ungated runner: {stale}"
    unreferenced = sorted(k for k, r in UNINVOKED_TEST_SCRIPTS.items() if not re.search(r"#\d+", r))
    assert not unreferenced, f"allowlist reasons must name the issue that expires them: {unreferenced}"


def test_no_new_package_is_gated_by_nothing(measurement) -> None:
    """The class statement: a whole app whose every runner is ungated (#15667)."""
    runners, invoked = measurement
    covered = covered_scripts(runners, invoked)
    wholly_ungated = sorted(
        directory for directory, scripts in runners.items() if not any(f"{directory}::{n}" in covered for n in scripts)
    )
    assert len(wholly_ungated) <= MAX_WHOLLY_UNGATED_PACKAGES, (
        f"{len(wholly_ungated)} packages have no gated test runner at all "
        f"(ceiling {MAX_WHOLLY_UNGATED_PACKAGES}): {wholly_ungated}. This is the "
        "#15667 shape -- an entire app's suite running nowhere. Wire it in; the "
        "ceiling is DOWN-ONLY."
    )
