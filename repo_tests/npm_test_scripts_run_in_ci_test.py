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
from typing import NamedTuple

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
}

#: DOWN-ONLY ceiling on packages whose EVERY runner is allowlisted -- a whole
#: app gated by nothing, which is exactly the #15667 shape. Was 5 on the first
#: measurement (.mcp, autobot-browser-worker, vscode-autobot,
#: mcp-structured-thinking, libs/autobot-sdk-ts); npm-package-tests.yml gates
#: .mcp (#15674), libs/autobot-sdk-ts (#15676) and mcp-structured-thinking
#: (#15677), leaving two. NEVER raise this to make a new app pass; wire the app
#: in, or this guard has become the thing it replaced.
MAX_WHOLLY_UNGATED_PACKAGES = 2

#: Floors, so a regex that stops matching turns this module red instead of green
#: (the #15018 lesson: a guard that enumerates nothing passes comfortably).
#: Measured on Dev_new_gui: 7 packages declaring 13 runners between them, and
#: 15 npm script invocations resolved to a tracked package directory. The floors
#: sit below those so a package removal does not fail the guard, while a
#: scanner that has stopped reaching the tree still does.
MIN_YAML_SOURCES = 20
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


def declared_scripts(root: Path) -> dict[str, dict[str, str]]:
    """`<package dir>` -> every script it declares, whatever its shape."""
    declared: dict[str, dict[str, str]] = {}
    for path in tracked_package_files(root):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        scripts = {n: b for n, b in (manifest.get("scripts") or {}).items() if isinstance(b, str)}
        declared[path.parent.relative_to(root).as_posix()] = scripts
    return declared


def declared_runners(scripts: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """`<package dir>` -> `{script: body}` for every runner a manifest declares."""
    declared: dict[str, dict[str, str]] = {}
    for directory, entries in scripts.items():
        runners = {n: b for n, b in entries.items() if is_runner(n, b)}
        if runners:
            declared[directory] = runners
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


#: Shell separators, longest first so `||` is never split as two pipes.
SHELL_SEGMENT = re.compile(r"(&&|\|\||;|\|)")


def _normalise(directory: str | None) -> str:
    return "." if directory in (None, "", ".") else Path(directory).as_posix().strip("/")


def _resolve_cd(current: str, target: str) -> str:
    if target.startswith("/") or "${{" in target:
        return _normalise(target)
    return _normalise(target if current == "." else str(Path(current) / target))


def _keys_in_segment(directory: str, segment: str) -> set[str]:
    return {f"{directory}::{m.group(1)}" for m in SCRIPT_CALL.finditer(segment) if m.group(1) not in NOT_A_SCRIPT}


def _calls_in_line(current: str, line: str) -> tuple[str, set[str]]:
    """Scan one shell line left to right, returning the directory it leaves behind.

    `cd autobot-slm-frontend && npm run test:unit` is one of the two spellings
    this repository uses, so the `cd` must change the directory for what FOLLOWS
    it on the same line rather than ending the scan -- treating it as a stop
    reported a gated runner as ungated, which is a wrong measurement in the one
    module whose job is measuring reach honestly.

    A `cd` guarded by `||` is the failure branch: `cd missing || npm run test`
    runs the script in the directory the `cd` did NOT leave, so the pending
    change is dropped rather than applied.
    """
    parts, directory, found, pending = SHELL_SEGMENT.split(line), current, set(), None
    for index, part in enumerate(parts):
        if index % 2:  # a separator: && || ; |
            directory = directory if (pending is None or part == "||") else pending
            pending = None
            continue
        segment = part.strip().lstrip("(").rstrip(")").strip()
        change = re.match(r"cd\s+([^\s;&|]+)\s*$", segment)
        pending = _resolve_cd(directory, change.group(1)) if change else None
        if not change:
            found |= _keys_in_segment(directory, segment)
    if "(" in line:
        # `( cd app && npm run x ) || true` -- resolved above so the call is
        # scoped correctly, but a subshell's `cd` dies with the subshell, so it
        # must not carry to the next line. Guessing wide here would manufacture
        # a gated runner, which is the one error this module must never make.
        return current, found
    return (pending if pending is not None else directory), found


def _calls_in_step(working_directory: str, run: str) -> set[str]:
    """`<dir>::<script>` keys a single `run:` block invokes."""
    current, found = working_directory, set()
    for line in run.splitlines():
        current, keys = _calls_in_line(current, line.strip())
        found |= keys
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


def covered_scripts(scripts: dict[str, dict[str, str]], invoked: set[str]) -> set[str]:
    """Invoked keys, closed transitively over delegation.

    Walks the COMPLETE script map, not the runner map: a wrapper is classified
    out of the runner population because it declares no suite of its own, but a
    workflow can still invoke it, and dropping it would lose the edge that gates
    what it chains to. The same edge exists for a non-test entry point --
    `"ci": "npm run lint && npm run test:unit"` gates `test:unit` -- which a
    test-shaped-only graph could not see either.

    Measured on Dev_new_gui: one such edge exists (`autobot-frontend::test:all`
    -> test:unit, test:integration, test:playwright) and no workflow invokes it,
    so this closure changes no number today. It is here so the guard's verdict
    does not depend on that staying true.
    """
    covered = {key for key in invoked if key.split("::", 1)[0] in scripts}
    frontier = set(covered)
    while frontier:
        following = set()
        for key in frontier:
            directory, name = key.split("::", 1)
            body = scripts.get(directory, {}).get(name)
            if body is not None:
                following |= {f"{directory}::{d}" for d in delegates(body)} - covered
        covered |= following
        frontier = following
    return covered


class Measurement(NamedTuple):
    """One sweep of the checkout: what is declared, and what CI invokes."""

    scripts: dict[str, dict[str, str]]
    runners: dict[str, dict[str, str]]
    invoked: set[str]
    sources: int

    @property
    def covered(self) -> set[str]:
        return covered_scripts(self.scripts, self.invoked)


@pytest.fixture(scope="module")
def measurement() -> Measurement:
    root = repo_root()
    scripts = declared_scripts(root)
    return Measurement(scripts, declared_runners(scripts), workflow_invocations(root), len(yaml_sources(root)))


def test_enumeration_is_not_vacuous(measurement: Measurement) -> None:
    """Floors bind to the sweep's REACH, never to a count of findings (#15018).

    Files parsed, manifests reached, runners classified, invocations resolved --
    each is a number that only a broken scanner can drive down, so fixing a real
    finding never trips one.
    """
    assert (
        measurement.sources >= MIN_YAML_SOURCES
    ), f"only {measurement.sources} workflow/action YAML files reached; yaml_sources has stopped walking the tree"
    assert len(measurement.runners) >= MIN_PACKAGES_WITH_TEST_SCRIPTS, (
        f"only {len(measurement.runners)} tracked package.json files declare a test runner; "
        "the enumerator has stopped reaching them"
    )
    declared = sum(len(entries) for entries in measurement.runners.values())
    assert declared >= MIN_RUNNER_SCRIPTS, (
        f"only {declared} test runner scripts found across those manifests; "
        "TEST_SCRIPT_NAME or is_runner has stopped classifying them"
    )
    assert len(measurement.invoked) >= MIN_WORKFLOW_INVOCATIONS, (
        f"only {len(measurement.invoked)} npm script invocations found across the workflow tree; "
        "SCRIPT_CALL or the YAML walk has stopped matching"
    )


def test_known_invocations_are_detected(measurement: Measurement) -> None:
    """The scanner sees both spellings of a scoped invocation this repo uses."""
    missing = sorted(k for k in REQUIRED_DETECTIONS if k not in measurement.covered)
    assert not missing, (
        "these invocations exist in the workflow tree but the scanner no longer sees "
        f"them, so its verdict is worthless: {missing}"
    )


def test_every_test_script_is_invoked_by_a_workflow(measurement: Measurement) -> None:
    """The #15667 assertion: a declared runner that nothing runs is a defect."""
    covered = measurement.covered
    unaccounted = sorted(
        key
        for directory, entries in measurement.runners.items()
        for key in (f"{directory}::{n}" for n in entries)
        if key not in covered and key not in UNINVOKED_TEST_SCRIPTS
    )
    assert not unaccounted, (
        "these package.json test runners are invoked by no workflow and no composite "
        "action -- wire them into CI, or record the decision (with an issue number) in "
        f"UNINVOKED_TEST_SCRIPTS: {unaccounted}"
    )


def test_allowlist_entries_are_live_and_carry_an_issue(measurement: Measurement) -> None:
    """An entry that no longer describes a gap must be deleted, not left to rot."""
    covered = measurement.covered
    declared = {f"{d}::{n}" for d, entries in measurement.runners.items() for n in entries}
    stale = sorted(k for k in UNINVOKED_TEST_SCRIPTS if k not in declared or k in covered)
    assert not stale, f"UNINVOKED_TEST_SCRIPTS entries no longer describe an ungated runner: {stale}"
    unreferenced = sorted(k for k, r in UNINVOKED_TEST_SCRIPTS.items() if not re.search(r"#\d+", r))
    assert not unreferenced, f"allowlist reasons must name the issue that expires them: {unreferenced}"


def test_no_new_package_is_gated_by_nothing(measurement: Measurement) -> None:
    """The class statement: a whole app whose every runner is ungated (#15667)."""
    covered = measurement.covered
    wholly_ungated = sorted(
        directory
        for directory, entries in measurement.runners.items()
        if not any(f"{directory}::{n}" in covered for n in entries)
    )
    assert len(wholly_ungated) <= MAX_WHOLLY_UNGATED_PACKAGES, (
        f"{len(wholly_ungated)} packages have no gated test runner at all "
        f"(ceiling {MAX_WHOLLY_UNGATED_PACKAGES}): {wholly_ungated}. This is the "
        "#15667 shape -- an entire app's suite running nowhere. Wire it in; the "
        "ceiling is DOWN-ONLY."
    )


# --------------------------------------------------------------------------
# Contrast fixtures. Every detector above gets a pair: an input that SHOULD
# trip it and a near miss that should not. The assertions on the checkout only
# say what today's tree looks like -- a classifier that matched everything, or
# nothing, would satisfy them just as comfortably, and both failures are silent.
# The near misses are drawn from real bodies in this repository, including the
# one that already bit: `vitest run --config vitest.integration.config.ts`
# names the watcher twice and was classified as a developer-only mode.
# --------------------------------------------------------------------------

INTERACTIVE_CONTRASTS = (
    ("vitest", True),
    ("vitest --coverage", True),
    ("vitest --coverage --ui", True),
    ("playwright test --headed", True),
    ("playwright show-report", True),
    ("playwright test --config playwright.visual.config.ts --update-snapshots", True),
    ("start-server-and-test 'vite dev --port 5173' http://localhost:5173 'cypress open --e2e'", True),
    ("jest --watch", True),
    ("vitest run", False),
    ("vitest run --coverage", False),
    ("vitest run --config vitest.integration.config.ts", False),
    ("playwright test", False),
    ("playwright test --config playwright.visual.config.ts", False),
    ("start-server-and-test preview http://localhost:5173 'cypress run --e2e'", False),
    ("node --test autobot-mcp-server.test.js", False),
    ("node --experimental-vm-modules node_modules/.bin/jest", False),
)

DELEGATION_CONTRASTS = (
    ("run-s test:unit test:integration test:playwright", True),
    ("npm run lint && npm run test:unit", True),
    ("vitest run --config vitest.integration.config.ts", False),
    ("playwright test", False),
    ("node --test autobot-mcp-server.test.js", False),
    ("npm run build && vitest run", False),
)

PLACEHOLDER_CONTRASTS = (
    ('echo "Error: no test specified" && exit 1', True),
    ("echo 'Error: no test specified' && exit 1", True),
    ('echo "running the suite" && vitest run', False),
    ("vitest run", False),
)

NAME_CONTRASTS = (
    ("test", True),
    ("test:unit", True),
    ("test:e2e:dev", True),
    ("pretest", False),
    ("lint", False),
    ("build:check", False),
    ("check:i18n", False),
)

#: `(working-directory, run block)` -> the keys the scanner must find, exactly.
CALL_CONTRASTS = (
    ("autobot-slm-frontend", "npm run test:unit", {"autobot-slm-frontend::test:unit"}),
    (".", "cd autobot-slm-frontend && npm run test:unit", {"autobot-slm-frontend::test:unit"}),
    (".", "cd autobot-frontend\nnpm run test:coverage", {"autobot-frontend::test:coverage"}),
    (".", "cd libs/autobot-sdk-ts && npm ci && npm test", {"libs/autobot-sdk-ts::test"}),
    # A `cd` on the failure branch never happened: the script runs where we were.
    (".", "cd missing || npm run test", {".::test"}),
    # A subshell resolves within the line; see _calls_in_line for why it may
    # not carry past it.
    (".", "( cd autobot-frontend && npm run test:playwright ) || true", {"autobot-frontend::test:playwright"}),
    (".", "( cd autobot-frontend && npm ci )\nnpm run test:unit", {".::test:unit"}),
    (".", "npm ci", set()),
    (".", "npx playwright install --with-deps chromium", set()),
    ("autobot-frontend", "rm -rf node_modules dist || true", set()),
)


@pytest.mark.parametrize(("body", "should_trip"), INTERACTIVE_CONTRASTS)
def test_interactive_body_discriminates(body: str, should_trip: bool) -> None:
    """INTERACTIVE_BODY separates a watcher from a one-shot run."""
    assert bool(INTERACTIVE_BODY.search(body)) is should_trip, body


@pytest.mark.parametrize(("body", "should_trip"), DELEGATION_CONTRASTS)
def test_pure_delegation_discriminates(body: str, should_trip: bool) -> None:
    """A wrapper chains sibling scripts; a runner names a command."""
    assert is_pure_delegation(body) is should_trip, body


@pytest.mark.parametrize(("body", "should_trip"), PLACEHOLDER_CONTRASTS)
def test_placeholder_body_discriminates(body: str, should_trip: bool) -> None:
    """The npm-init stub is not a suite; an `echo` before a real run is."""
    assert bool(PLACEHOLDER_BODY.match(body.strip())) is should_trip, body


@pytest.mark.parametrize(("name", "should_trip"), NAME_CONTRASTS)
def test_test_script_name_discriminates(name: str, should_trip: bool) -> None:
    """`test` and `test:*` only -- `pretest` is a hook, not a runner."""
    assert bool(TEST_SCRIPT_NAME.match(name)) is should_trip, name


@pytest.mark.parametrize(("directory", "run", "expected"), CALL_CONTRASTS)
def test_script_call_scanner_discriminates(directory: str, run: str, expected: set[str]) -> None:
    """Both scoping spellings resolve, and package management is not a script."""
    assert _calls_in_step(directory, run) == expected, run


def test_is_runner_agrees_with_its_parts() -> None:
    """End to end: the classification a manifest actually gets."""
    assert is_runner("test:unit", "vitest run")
    assert is_runner("test", "npx playwright test")
    assert not is_runner("test", "vitest")
    assert not is_runner("test:all", "run-s test:unit test:integration")
    assert not is_runner("test", 'echo "Error: no test specified" && exit 1')
    assert not is_runner("lint", "eslint .")


def test_delegation_closure_gates_what_a_wrapper_chains_to() -> None:
    """The edge CodeRabbit named: an invoked wrapper covers its targets."""
    scripts = {"app": {"test:all": "run-s test:unit", "test:unit": "vitest run", "ci": "npm run test:unit"}}

    assert covered_scripts(scripts, {"app::test:all"}) >= {"app::test:all", "app::test:unit"}
    # And the same edge from a non-test entry point.
    assert "app::test:unit" in covered_scripts(scripts, {"app::ci"})
    assert covered_scripts(scripts, {"app::test:unit"}) == {"app::test:unit"}
