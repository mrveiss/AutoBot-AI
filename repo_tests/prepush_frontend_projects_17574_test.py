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


#: Illustrative changeset paths, fed to the hook's own filters as text. **Every
#: one must be fictional.** `python_filter_covers_its_guards_test` records a
#: quoted path literal as a tree this guard reads whenever the path is a real
#: file -- so a fixture that happens to name one asserts a dependency this guard
#: does not have, and lands in a shrink-only record that nothing can remove.
#: `autobot-frontend/src/App.vue` stood here and is a real file; five siblings
#: were already fictional and went unnoticed for exactly that reason.
#: `test_no_fixture_path_names_a_real_file` keeps this true.
FRONTEND_CHANGES = [
    "autobot-frontend/src/components/Chat.vue",
    "autobot-frontend/src/composables/useThing.ts",
    "autobot-slm-frontend/src/views/RolesView.test.ts",
    "autobot-slm-frontend/src/composables/usePerformanceMonitoring.test.ts",
    "libs/autobot-ui/src/components/Button.vue",
    "libs/autobot-sdk-ts/src/resources/exampleOnly.ts",
]

#: One project, one file -- the no-remainder case. Fictional, as above.
SINGLE_PROJECT_CHANGE = ("autobot-frontend/src/ExampleOnlyView.vue",)


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
                    "autobot-slm-frontend/src/views/RolesView.test.ts",
                    "autobot-slm-frontend/src/composables/usePerformanceMonitoring.test.ts",
                ],
            ),
        ],
    )
    def test_a_project_claims_exactly_its_own_paths(self, project: str, expected: list[str]) -> None:
        claimed = _filter(_extract(_CLAIM, "project claim"), project, FRONTEND_CHANGES)
        assert claimed == expected

    def test_autobot_frontend_does_not_claim_the_slm_tree(self) -> None:
        """The defect, stated as a test: the prefix is anchored per project.

        `sed 's|^autobot-frontend/||'` is anchored, so an `autobot-slm-frontend/`
        path survived it intact and reached the wrong runner.
        """
        claimed = _filter(_extract(_CLAIM, "project claim"), "autobot-frontend", FRONTEND_CHANGES)
        assert not [path for path in claimed if path.startswith("autobot-slm-frontend/")]

    def test_the_remainder_is_accounted_for_not_dropped(self) -> None:
        """`libs/*` and the MCP tools declare no type-check script and carry no
        install, so nothing local can check them. They must end up in the
        unclaimed list, which the hook reports as `could_not_run` -- a silent
        skip is the failure mode #16912 describes."""
        remainder = FRONTEND_CHANGES
        unclaim = _extract(_UNCLAIM, "unclaimed remainder")
        for project in _declared_projects():
            remainder = _filter(unclaim, project, remainder)
        assert remainder == [
            "libs/autobot-ui/src/components/Button.vue",
            "libs/autobot-sdk-ts/src/resources/exampleOnly.ts",
        ]

    def test_a_changeset_inside_one_project_leaves_no_remainder(self) -> None:
        remainder = list(SINGLE_PROJECT_CHANGE)
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


class TestNoUnexportedVariableInASubshell:
    """#17575: `$REPO_ROOT` inside a single-quoted `sh -c` is always empty.

    Nothing in the hook exports it, so the child expands it to nothing and the
    existence test it guarded was false for every input -- a selector that
    matched nothing, indistinguishable from one that had nothing to match.
    """

    def test_no_single_quoted_subshell_reads_repo_root(self) -> None:
        offenders = [line for line in _source().splitlines() if "sh -c '" in line and "$REPO_ROOT" in line]
        assert not offenders, offenders

    def test_repo_root_is_either_exported_or_never_needed_downstream(self) -> None:
        """Belt and braces: if a future edit adds an export, this still holds.

        The assertion is the property, not the mechanism -- either the variable
        travels, or no child shell depends on it.
        """
        source = _source()
        exported = re.search(r"^\s*export\s+REPO_ROOT\b", source, re.MULTILINE) is not None
        depends = "sh -c '" in source and "$REPO_ROOT" in source
        assert exported or not depends


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

    @pytest.mark.parametrize("path", [*FRONTEND_CHANGES, *SINGLE_PROJECT_CHANGE])
    def test_no_fixture_path_names_a_real_file(self, path: str) -> None:
        assert not (REPO_ROOT / path).exists(), (
            f"{path} exists in the repository, so the coverage detector will record it as a tree this "
            "guard reads. Fixtures are text fed to a filter -- pick a name nothing resolves to."
        )
