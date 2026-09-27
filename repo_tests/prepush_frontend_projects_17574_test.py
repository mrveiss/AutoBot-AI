#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-push frontend phase must run each project's own toolchain (#17574).

That phase named `autobot-frontend` as a literal while being reached by ANY
changed `.ts`/`.vue`. For a change in another tree -- `autobot-slm-frontend`,
`libs/autobot-ui`, `libs/autobot-sdk-ts`, the MCP tools -- it therefore:

  * type-checked `autobot-frontend`, a pass that says nothing about the change,
    and one where a real error could not even be attributed, because the triage
    strips only its own prefix before matching diagnostics; and
  * handed the foreign test path to a vitest rooted in `autobot-frontend`, whose
    config includes `src/**` only. The filter matched nothing, vitest exited
    non-zero, and the hook reported **`vitest failures`** for tests that had
    never run.

A false red naming specific files costs more than a false green: someone goes
and debugs tests that are fine, and the transcript records a defect that does
not exist. #16912's `could_not_run` branch could not catch it, being guarded on
node_modules being *absent* while `autobot-frontend`'s is present.

These tests run the hook's **own** expressions rather than a copy of them, for
the reason `prepush_splits_the_backends_16069_test.py` states: a
reimplementation here would agree with itself and prove nothing.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess

import pytest
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

REPO_ROOT = repo_root()
_HOOK = REPO_ROOT / "tools" / "git-hooks" / "pre-push"

#: `FRONTEND_PROJECTS="a b"` — the declared list the loop iterates.
_PROJECTS = re.compile(r'^\s*FRONTEND_PROJECTS="([^"]+)"\s*$', re.MULTILINE)

#: The per-project claim and the running remainder, as shipped.
_CLAIM = re.compile(
    r'^\s*project_changed=\$\(echo "\$frontend_changed" \| (?P<filter>grep -E "\^\$\{project\}/"[^)]*)\)\s*$',
    re.MULTILINE,
)
_UNCLAIM = re.compile(
    r'^\s*frontend_unclaimed=\$\(echo "\$frontend_unclaimed" \| (?P<filter>grep -vE "\^\$\{project\}/"[^)]*)\)\s*$',
    re.MULTILINE,
)

#: The traversability helper, extracted whole and executed.
_USABLE = re.compile(r"^node_modules_usable\(\) \{\n(?:.*\n)*?\}$", re.MULTILINE)

#: The `__tests__/` sibling selector, whose existence filter used to read an
#: unexported variable in a child shell (#17575).
_COMPOSABLE = re.compile(r"^\s*composable_tests=\$\((?P<filter>(?:.|\n)*?)\)\s*$", re.MULTILINE)


def _source() -> str:
    return _HOOK.read_text(encoding="utf-8")


def _declared_projects() -> list[str]:
    match = _PROJECTS.search(_source())
    assert match, "the hook no longer declares FRONTEND_PROJECTS — move this test with it, do not delete it"
    return match.group(1).split()


def _extract(pattern: re.Pattern[str], what: str) -> str:
    match = pattern.search(_source())
    assert match, f"the hook's {what} expression no longer matches — move this test with it, do not delete it"
    return match.group("filter")


def _filter(expr: str, project: str, paths: list[str]) -> list[str]:
    """Run one of the hook's shipped pipeline stages over *paths*.

    The list goes in on stdin rather than being interpolated: an earlier harness
    for the pytest split embedded a Python repr, bash received the two
    characters `\\n`, every case collapsed to one line, and the harness passed
    while testing nothing.
    """
    completed = subprocess.run(
        ["bash", "-c", f'project="{project}"; {expr} || true'],
        input="\n".join(paths),
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in completed.stdout.splitlines() if line.strip()]


def example_changeset() -> list:
    """Illustrative changeset paths, built HERE rather than bound at module level.

    Two guards read a module-level collection of repo-rooted path strings in
    opposite directions, and a fixture satisfies neither:

    * `python_filter_covers_its_guards_test` treats a quoted path that RESOLVES
      as a tree this guard depends on -- so a real path must not appear. That is
      what `autobot-frontend/src/App.vue` tripped.
    * `stranded_recorder_entries_test` discovers any module-level dict/set/list/
      tuple with >= 3 repo-rooted entries as a **ledger**, and an entry the tree
      does not hold is a stale record -- so a fictional path must not appear
      either. That is what the fix for the first one tripped.

    These strings are neither: they are sample input to a `grep`, and the hook's
    filter needs them repo-root-shaped (`^autobot-frontend/`) to exercise
    anything. `ledgers_in` inspects `ast.parse(source).body`, i.e. top-level
    bindings only, so a function-scoped fixture is outside the population by
    construction rather than by dilution -- padding the list with prose to fall
    under the 0.8 rooted share would be gaming a heuristic, and making the paths
    real would re-break the other guard.

    Which is exactly what happened: these were fictional when written, and #17616
    then created `autobot-slm-frontend/src/views/RolesView.test.ts` and
    `.../composables/usePerformanceMonitoring.test.ts` for real, so this file's
    own guard failed and the uncovered-reads record grew by two. Renamed to
    `ExampleOnly` names, the convention this file already uses -- a fictional path
    has to be one nobody would plausibly create later, not merely one that does
    not exist today.
    """
    return [
        "autobot-frontend/src/components/Chat.vue",
        "autobot-frontend/src/composables/useThing.ts",
        "autobot-slm-frontend/src/views/ExampleOnlyView.test.ts",
        "autobot-slm-frontend/src/composables/useExampleOnly.test.ts",
        "libs/autobot-ui/src/components/Button.vue",
        "libs/autobot-sdk-ts/src/resources/exampleOnly.ts",
    ]


def single_project_change() -> list:
    """One project, one file -- the no-remainder case. Fictional, as above."""
    return ["autobot-frontend/src/ExampleOnlyView.vue"]


class TestTheDeclaredProjectsMatchTheTree:
    """A third frontend must fail this, not fall into the first one."""

    def test_every_declared_project_has_the_script_the_hook_invokes(self) -> None:
        """The hook runs `npm run type-check`, so each project must declare it.

        Naming a tsconfig in the hook instead would be a second declaration that
        drifts: autobot-frontend uses tsconfig.app.json, autobot-slm-frontend
        uses tsconfig.json.
        """
        declaring = self._projects_declaring_type_check()
        for project in _declared_projects():
            assert project in declaring, f"{project} declares no `type-check` script"

    def test_both_frontends_are_declared(self) -> None:
        declared = _declared_projects()
        assert "autobot-frontend" in declared
        assert "autobot-slm-frontend" in declared

    @staticmethod
    def _projects_declaring_type_check() -> set[str]:
        """Every tracked project whose package.json declares the script.

        Tracked enumeration rather than a glob: `REPO_ROOT.glob("*/package.json")` is
        one level deep, so it would have missed `libs/autobot-ui` and the MCP
        tools -- exactly the trees this defect was about -- and asserted over a
        population that excluded them. Tracked-only also excludes node_modules
        for free.
        """
        # `tracked_paths`, not a bare `git ls-files`: an inherited GIT_DIR
        # outranks `cwd=` and enumerates the OTHER checkout's index, answering
        # confidently about the wrong tree without erroring (#14896, caught by
        # the git-toplevel-env-scrubbed hook on this very file).
        #
        # It is also the ONLY place this guard reads a package.json. A second,
        # composed `REPO_ROOT / project / "package.json"` stood here, and
        # `python_filter_covers_its_guards_test` reads any `X / "literal"` as a
        # tree this guard depends on -- reporting a bare `package.json` that no
        # filter covers. One enumeration keeps that fact recorded once, in
        # `_glob_declared_uncovered`'s `*package.json` entry where the glob is
        # declared, rather than twice in two records with two mechanisms.
        listed = tracked_paths(REPO_ROOT, "*package.json", exclude=("node_modules",))
        found = set()
        for rel in listed:
            try:
                scripts = json.loads((REPO_ROOT / rel).read_text(encoding="utf-8")).get("scripts") or {}
            except (ValueError, OSError):
                continue
            if "type-check" in scripts:
                found.add(rel.rsplit("/", 1)[0] if "/" in rel else ".")
        return found

    def test_the_declared_list_is_exactly_the_trees_that_can_be_type_checked(self) -> None:
        """Both directions, because each is a different defect.

        A tree with the script and no entry gets run as autobot-frontend -- the
        bug. An entry with no script gets `npm run type-check` and a non-zero
        exit that is not a type error.
        """
        assert self._projects_declaring_type_check() == set(_declared_projects())


class TestRouting:
    """Each project claims its own paths, and nobody claims another's."""

    @pytest.mark.parametrize(
        "project, expected",
        [
            (
                "autobot-frontend",
                ["autobot-frontend/src/components/Chat.vue", "autobot-frontend/src/composables/useThing.ts"],
            ),
            (
                "autobot-slm-frontend",
                [
                    "autobot-slm-frontend/src/views/ExampleOnlyView.test.ts",
                    "autobot-slm-frontend/src/composables/useExampleOnly.test.ts",
                ],
            ),
        ],
    )
    def test_a_project_claims_exactly_its_own_paths(self, project: str, expected: list[str]) -> None:
        claimed = _filter(_extract(_CLAIM, "project claim"), project, example_changeset())
        assert claimed == expected

    def test_autobot_frontend_does_not_claim_the_slm_tree(self) -> None:
        """The defect, stated as a test: the prefix is anchored per project.

        `sed 's|^autobot-frontend/||'` is anchored, so an `autobot-slm-frontend/`
        path survived it intact and reached the wrong runner.
        """
        claimed = _filter(_extract(_CLAIM, "project claim"), "autobot-frontend", example_changeset())
        assert not [path for path in claimed if path.startswith("autobot-slm-frontend/")]

    def test_the_remainder_is_accounted_for_not_dropped(self) -> None:
        """`libs/*` and the MCP tools declare no type-check script and carry no
        install, so nothing local can check them. They must end up in the
        unclaimed list, which the hook reports as `could_not_run` -- a silent
        skip is the failure mode #16912 describes."""
        remainder = example_changeset()
        unclaim = _extract(_UNCLAIM, "unclaimed remainder")
        for project in _declared_projects():
            remainder = _filter(unclaim, project, remainder)
        assert remainder == [
            "libs/autobot-ui/src/components/Button.vue",
            "libs/autobot-sdk-ts/src/resources/exampleOnly.ts",
        ]

    def test_a_changeset_inside_one_project_leaves_no_remainder(self) -> None:
        remainder = single_project_change()
        unclaim = _extract(_UNCLAIM, "unclaimed remainder")
        for project in _declared_projects():
            remainder = _filter(unclaim, project, remainder)
        assert remainder == []


class TestNodeModulesUsable:
    """#17573's condition, made executable rather than described."""

    @staticmethod
    def _ask(directory) -> bool:
        match = _USABLE.search(_source())
        assert match, "the hook no longer defines node_modules_usable — move this test with it"
        script = f'{match.group(0)}\nnode_modules_usable "{directory}" && echo USABLE || echo NO'
        completed = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
        return completed.stdout.strip() == "USABLE"

    def test_a_traversable_install_is_usable(self, tmp_path) -> None:
        tmp_path.joinpath("node_modules").mkdir(mode=0o755)
        assert self._ask(tmp_path) is True

    @pytest.mark.skipif(
        os.geteuid() == 0,
        reason="root ignores the mode bits, so this would pass for the wrong reason",
    )
    def test_a_present_but_untraversable_install_is_not_usable(self, tmp_path) -> None:
        """The whole point: `-d` alone answers yes here.

        `autobot-slm-frontend/node_modules` is mode 644 on this host (#17573), so
        every binary under it is unreachable while the directory exists. Treating
        that as a usable toolchain is what turns "cannot run" into a verdict.
        """
        install = tmp_path.joinpath("node_modules")
        install.mkdir(mode=0o755)
        install.chmod(0o644)
        try:
            assert self._ask(tmp_path) is False
        finally:
            install.chmod(0o755)

    def test_a_missing_install_is_not_usable(self, tmp_path) -> None:
        assert self._ask(tmp_path) is False


#: A single-quoted `sh -c '...'` body, **across lines**. The #17575 defect can
#: return wrapped over several lines, and a per-line check would not see it
#: (#17579 review).
_SH_C_BODY = re.compile(r"sh\s+-c\s+'(?P<body>[^']*)'", re.DOTALL)

#: `$NAME` / `${NAME}`. Positional parameters are excluded by the first-character
#: class: `$1` and `$0` are given to the child by xargs, not inherited.
_VAR_READ = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")

_ASSIGNED_IN_BODY = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=", re.MULTILINE)
_EXPORTED = re.compile(r"^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)


def exported_names(source: str) -> set:
    """Variables the parent shell actually exports."""
    return set(_EXPORTED.findall(source))


def subshell_offenders(source: str) -> dict:
    """`{body: variables it reads that the parent never exports}`.

    A single-quoted body is expanded by the CHILD, so every name in it must
    reach the child through the environment. `set -u` does not help: the child
    is a fresh shell without `nounset`, so an unexported name expands to empty
    and whatever guarded on it silently answers no.
    """
    exported = exported_names(source)
    offenders = {}
    for match in _SH_C_BODY.finditer(source):
        body = match.group("body")
        assigned = set(_ASSIGNED_IN_BODY.findall(body))
        needed = {name for name in _VAR_READ.findall(body) if name not in assigned and name not in exported}
        if needed:
            offenders[body] = needed
    return offenders


class TestTheSubshellDetector:
    """The detector, against a fixture that must trip it and one that must not.

    #17579 review, and the objection was right twice over: the previous pair
    checked one line at a time, so a multi-line `sh -c` body would have evaded
    it, and the second test asked whether `sh -c '` and `$REPO_ROOT` both appear
    ANYWHERE in the file -- which the hook satisfies by using `$REPO_ROOT` in
    many legitimate places, so an unrelated single-quoted subshell would have
    failed it for nothing. Neither had the contrast pair this repository's path
    instruction requires, which is the same vacuity question I put on my own
    #17573 fixture an hour earlier.
    """

    def test_it_trips_on_a_single_line_body(self) -> None:
        """#17575 as it actually shipped."""
        source = """#!/usr/bin/env bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
echo x | xargs -I{} sh -c '[ -f "$REPO_ROOT/autobot-frontend/{}" ] && echo "{}"'
"""
        assert "REPO_ROOT" in next(iter(subshell_offenders(source).values()))

    def test_it_trips_on_a_body_wrapped_over_several_lines(self) -> None:
        """The form the previous per-line check could not see."""
        source = """#!/usr/bin/env bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
echo x | xargs -I{} sh -c '
    [ -f "$REPO_ROOT/autobot-frontend/{}" ] \\
        && echo "{}"
'
"""
        offenders = subshell_offenders(source)
        assert offenders, "a multi-line body reading an unexported variable was not detected"
        assert "REPO_ROOT" in next(iter(offenders.values()))

    def test_it_stays_quiet_on_a_body_that_reads_nothing(self) -> None:
        source = """#!/usr/bin/env bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
echo x | xargs -I{} sh -c '[ -f "{}" ] && echo "{}"'
"""
        assert subshell_offenders(source) == {}

    def test_it_stays_quiet_when_the_variable_is_exported(self) -> None:
        """The other correct fix for #17575, and it must not read as a defect."""
        source = """#!/usr/bin/env bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
echo x | xargs -I{} sh -c '[ -f "$REPO_ROOT/{}" ] && echo "{}"'
"""
        assert subshell_offenders(source) == {}

    def test_a_name_assigned_inside_the_body_is_not_a_read(self) -> None:
        source = """#!/usr/bin/env bash
echo x | sh -c 'found=1; echo "$found"'
"""
        assert subshell_offenders(source) == {}

    def test_positional_parameters_are_not_reads(self) -> None:
        """xargs hands those to the child; they are not inherited."""
        source = """#!/usr/bin/env bash
echo x | xargs -I{} sh -c 'echo "$0 $1 {}"'
"""
        assert subshell_offenders(source) == {}


class TestTheHookHasNoSuchSubshell:
    """The property, asserted against the shipped file by the detector above."""

    def test_no_subshell_reads_a_variable_the_parent_withholds(self) -> None:
        offenders = subshell_offenders(_source())
        assert not offenders, f"single-quoted sh -c bodies reading unexported names: {offenders}"


class TestTheComposableSiblingSelector:
    """#17575: this selector matched nothing for every input, invisibly.

    Its existence filter expanded `$REPO_ROOT` inside a single-quoted `sh -c`.
    Nothing in the hook exports that variable, so the child saw it empty, the
    test was `[ -f "/autobot-frontend/..." ]` for every path, and the selector
    returned nothing. There is no log line for "selected none", so its absence
    read exactly like a change with no sibling test to run.
    """

    @staticmethod
    def _select(project: str, project_dir, paths: list[str]) -> list[str]:
        expr = _extract(_COMPOSABLE, "composable sibling")
        script = (
            f"project={shlex.quote(project)}\n"
            f"project_dir={shlex.quote(str(project_dir))}\n"
            f"project_changed={shlex.quote(chr(10).join(paths))}\n"
            f"composable_tests=$({expr})\n"
            'printf "%s\\n" "$composable_tests"\n'
        )
        completed = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
        return [line for line in completed.stdout.splitlines() if line.strip()]

    def test_the_sibling_is_selected_when_it_exists(self, tmp_path) -> None:
        sibling = tmp_path.joinpath("src", "composables", "__tests__", "useThing.test.ts")
        sibling.parent.mkdir(parents=True)
        sibling.write_text("", encoding="utf-8")

        selected = self._select("autobot-frontend", tmp_path, ["autobot-frontend/src/composables/useThing.ts"])

        assert selected == ["src/composables/__tests__/useThing.test.ts"]

    def test_nothing_is_selected_when_the_sibling_does_not_exist(self, tmp_path) -> None:
        """The correct empty, as opposed to #17575's empty-for-every-input."""
        selected = self._select("autobot-frontend", tmp_path, ["autobot-frontend/src/composables/useThing.ts"])

        assert selected == []

    def test_the_selector_reads_no_variable_the_parent_withholds(self) -> None:
        """The property, not the spelling: `$REPO_ROOT` is gone from it."""
        assert "$REPO_ROOT" not in _extract(_COMPOSABLE, "composable sibling")


class TestTheFixturesAreFixtures:
    """A fixture path must not name a real file (#17574 review, twice over).

    `python_filter_covers_its_guards_test` treats a quoted path literal as a
    tree this guard reads, but only when the path resolves to a real file. So
    five fictional siblings passed silently while `autobot-frontend/src/App.vue`
    was recorded as a dependency -- of a guard that never opens it, and only
    feeds it to a `grep` as text.

    Naming a real file would be harmless if the consequence were a warning. It
    is not: the remedy is an entry in a **shrink-only** record, which nothing can
    later remove because there is no tree to widen a filter to.
    """

    @pytest.mark.parametrize("path", [*example_changeset(), *single_project_change()])
    def test_no_fixture_path_names_a_real_file(self, path: str) -> None:
        assert not (REPO_ROOT / path).exists(), (
            f"{path} exists in the repository, so the coverage detector will record it as a tree this "
            "guard reads. Fixtures are text fed to a filter -- pick a name nothing resolves to."
        )
