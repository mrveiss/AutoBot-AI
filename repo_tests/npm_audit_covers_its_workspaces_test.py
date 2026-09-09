# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The npm audit gate must audit what it claims to audit (#16131).

`security.yml` reported "0 advisories at every severity across 1191 deps" while
scanning **one** of the workspaces that can be audited. The number was true and
the scope was not, and the summary read as a repository-wide result -- family F:
the output is correct, complete, and about a different question.

This guard binds the audited set to the *discovered* set, so a new workspace with
a lockfile fails here rather than being silently outside the scan. A hard-coded
list would reproduce the original defect one level up: the list, not the tree,
would decide what "every workspace" means.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

WORKFLOW = Path(".github/workflows/security.yml")

#: Workspaces whose findings have NOT yet been triaged, so the gate reports them
#: without blocking on them (#16131 AC5). Widening a gate and a backlog of
#: untriaged findings in one change lands as a wall of failures nobody can
#: action, and the usual response to that is to turn the gate off.
#:
#: This list may only SHRINK. Each removal means someone triaged that workspace.
UNTRIAGED: frozenset[str] = frozenset(
    {
        ".mcp",
        "autobot-infrastructure/shared/config",
        "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker",
        "autobot-infrastructure/shared/mcp/tools/mcp-structured-thinking",
        "autobot-slm-frontend",
        "libs/autobot-sdk-ts",
    }
)


def _auditable_workspaces(root: Path) -> list[str]:
    """Directories holding BOTH a package.json and a package-lock.json.

    A lockfile is what `npm audit` needs to resolve a dependency tree, so a
    `package.json` without one is not an unaudited workspace -- it is an
    unauditable one, and counting it would make this guard fail for a reason
    nobody can fix.
    """
    try:
        manifests = tracked_paths(root, "*package.json")
    except EmptyEnumeration:
        # `tracked_paths` refuses to call an empty enumeration a clean tree.
        # Returning [] relocates the refusal to the reach floor below, which is
        # the typed failure the meta-test is built around (#16154).
        return []
    workspaces = []
    for rel in manifests:
        if "node_modules" in rel or not rel.endswith("/package.json") and rel != "package.json":
            continue
        directory = str(Path(rel).parent)
        if (root / directory / "package-lock.json").is_file():
            workspaces.append(directory)
    return sorted(set(workspaces))


REACH = declare(
    "npm-audit-workspace-coverage",
    discover=_auditable_workspaces,
    floor=5,
    what="workspaces with a package.json and a lockfile",
    growth=6,
)


def _audit_steps() -> list[str]:
    """Every `run:` block in the workflow that invokes `npm audit`."""
    document = yaml.safe_load((repo_root() / WORKFLOW).read_text(encoding="utf-8"))
    blocks = []
    for job in document.get("jobs", {}).values():
        for step in job.get("steps", []):
            run = step.get("run") or ""
            if "npm audit" in run:
                blocks.append(run)
    return blocks


def _hardcoded_audit_targets(block: str) -> set[str]:
    """Literal directories an `npm audit` line cds into.

    A dynamic `cd "$ws"` yields nothing, which is the point: this returns what
    was HARD-CODED, so the test below can require that set to be empty rather
    than trying to evaluate shell.
    """
    targets = set()
    for line in block.splitlines():
        if "npm audit" not in line or "cd " not in line:
            continue
        fragment = line.split("cd ", 1)[1].split("&&")[0].strip().rstrip(")").strip()
        if fragment.startswith("$") or fragment.startswith('"$'):
            continue
        targets.add(fragment.strip('"'))
    return targets


def test_the_audit_is_driven_by_discovery_not_a_hard_coded_workspace() -> None:
    """#16131 AC1: discovered, not listed.

    The step scanned `autobot-frontend` alone while six other workspaces carried
    a lockfile, and its summary reported a repository-wide result. The defect is
    not the scanning -- it is the claiming.

    This asserts the SHAPE rather than trying to evaluate the shell: the audit
    must enumerate from `git ls-files`, and no `npm audit` line may cd into a
    literal directory. A hard-coded list would move the same defect up one level,
    with the list rather than the tree deciding what "every workspace" means.
    """
    blocks = _audit_steps()
    assert blocks, "no step invokes `npm audit` -- the gate has gone missing entirely"

    scanning = [b for b in blocks if "npm audit --audit-level" in b]
    assert scanning, "no step runs the audit itself"

    for block in scanning:
        assert "git ls-files" in block and "package-lock.json" in block, (
            "the audit does not enumerate workspaces from the tree. A hard-coded list "
            "reproduces #16131: the list, not the tree, decides what 'every workspace' means."
        )
        hardcoded = _hardcoded_audit_targets(block)
        assert not hardcoded, (
            "`npm audit` cds into literal director"
            + ("y" if len(hardcoded) == 1 else "ies")
            + f": {sorted(hardcoded)}. Enumerate instead, or this set silently stops "
            "matching the tree."
        )


def test_the_discovery_expression_matches_what_this_test_discovers() -> None:
    """The workflow's enumeration and this guard's must agree.

    Two enumerations of the same thing that disagree is the failure this file
    exists to prevent, one level up. Both must exclude node_modules and key on a
    lockfile; if the workflow's filter drifts, the sets diverge and the guard
    goes on reporting full coverage over a narrower scan.
    """
    root = repo_root()
    discovered = set(REACH.examined(root))
    REACH.completed(len(discovered))

    assert discovered, "no auditable workspace found -- the guard would pass over nothing"
    for block in [b for b in _audit_steps() if "npm audit --audit-level" in b]:
        assert "node_modules" in block, (
            "the workflow's enumeration does not exclude node_modules, so it audits "
            "vendored lockfiles this guard does not count -- the two sets disagree"
        )


def test_the_untriaged_list_only_shrinks() -> None:
    """An entry that is no longer auditable means the list went stale.

    A list carrying dead entries silently permits the next workspace to be added
    to it, which is how a temporary allowance becomes the permanent scope.
    """
    stale = UNTRIAGED - set(_auditable_workspaces(repo_root()))
    assert not stale, "UNTRIAGED names workspaces that are no longer auditable -- remove them:\n  " + "\n  ".join(
        sorted(stale)
    )


def test_no_workspace_is_both_audited_and_declared_untriaged_forever() -> None:
    """UNTRIAGED is a staging area, not a second scope.

    Every entry must be a real auditable workspace, so the list can be worked
    down to empty rather than becoming the place workspaces go to be ignored.
    """
    auditable = set(_auditable_workspaces(repo_root()))
    assert UNTRIAGED <= auditable, (
        "UNTRIAGED contains something that is not an auditable workspace: " f"{sorted(UNTRIAGED - auditable)}"
    )


def test_js_yaml_is_off_the_advisory_range_in_every_lockfile() -> None:
    """#16131 AC3, verified against the RANGE rather than against a version bump.

    GHSA-2883 covers js-yaml < 4.3.2 on the 4.x line and < 3.15.2 on 3.x. The
    fix for the 4.x range is 4.3.2 -- NOT the upper bound of the affected range,
    which is the reading that produced a "no fix exists" claim on #16089.
    """
    root = repo_root()
    offenders = []
    # `git ls-files`, NOT a filesystem walk (#15955). This repository keeps git
    # worktrees INSIDE the working copy, so `root.glob("**/...")` reaches other
    # checkouts of itself -- and would report js-yaml versions from a branch
    # nobody is asking about. Caught by the guard for exactly this, on this file.
    try:
        lockfiles = tracked_paths(root, "*package-lock.json")
    except EmptyEnumeration:
        lockfiles = []
    for relative in sorted(lockfiles):
        if "node_modules" in relative:
            continue
        lockfile = root / relative
        document = json.loads(lockfile.read_text(encoding="utf-8"))
        for name, entry in document.get("packages", {}).items():
            if not name.endswith("node_modules/js-yaml"):
                continue
            version = entry.get("version") or ""
            parts = [int(p) for p in version.split(".") if p.isdigit()]
            if len(parts) < 3:
                continue
            major, minor, patch = parts[0], parts[1], parts[2]
            fixed = (major, minor, patch) >= (4, 3, 2) or (major == 3 and (minor, patch) >= (15, 2))
            if not fixed:
                offenders.append(f"{relative}: js-yaml {version}")

    assert not offenders, "js-yaml inside GHSA-2883's affected range:\n  " + "\n  ".join(offenders)
