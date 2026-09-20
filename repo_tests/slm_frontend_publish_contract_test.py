# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Both SLM publishers satisfy the same contract, and disagreement is the failure (#15724).

The two existing guards each assert the contract in their own words and both
pass. What nothing checked was whether they still describe the *same* contract.
This does: every clause is evaluated against every implementation, so a clause
satisfied on one side and not the other is a failure naming both.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

import pytest
from repo_tests.slm_frontend_publish_contract import (
    CLAUSES,
    IMPLEMENTATIONS,
    MIN_IMPLEMENTATIONS,
    REPO_ROOT,
)

from tools.lint._scan_helpers import tracked_paths

#: What makes a file a *publisher* is that it flips the served pointer, not that
#: it builds. `npm run build:slm` alone is a builder: `role_registry.py` and
#: `role.json.j2` both run it, and neither publishes -- vite's default `outDir`
#: is `dist`, a sibling of the served `current` symlink, so they produce a
#: bundle nothing serves (#15889). Keying the search on the build command
#: reported those as unregistered publishers, which they are not.
#:
#: The search runs over the tree rather than over the registry, or it could only
#: ever find what it already knew about.
_PUBLISHER_HINTS = (
    re.compile(r"mv -T \.current\.next current"),
    # The Python spelling. Without it this search could only find publishers
    # written in a shell dialect -- which is how `services/slm_frontend_build.py`
    # sat unregistered while the guard reported a complete registry. A detector
    # that recognises one language cannot find a third-language implementation,
    # which is the exact case #15724 asks it to catch.
    re.compile(r"os\.replace\(staged, root / link_name\)"),
)

#: A `build:slm` invocation that does not pass `--outDir` builds into vite's
#: default `dist`. That is not an outage today, because `dist` is a sibling of
#: `current` rather than `current` itself -- but it is one config change away
#: from being one, which is why these are enumerated rather than ignored.
_UNSTAGED_BUILDERS = {
    "autobot-slm-backend/services/role_registry.py": "#15889 -- post_sync_cmd builds into dist/, which nothing serves",
    "autobot-slm-backend/ansible/roles/slm_manager/templates/role.json.j2": "#15889 -- build_steps, same shape",
}

#: Files that legitimately mention the idiom without being publishers: the
#: contract itself, the guards, and documentation. Listed by path with the
#: reason, rather than inferred from context.
#: Only files that actually contain the flip idiom need to be here. Each entry
#: was checked: the two guards that merely mention publishing were removed
#: again, because an allowlist entry that is not load-bearing is a standing
#: exemption for whatever later takes that path.
_NOT_PUBLISHERS = {
    "repo_tests/slm_frontend_publish_contract.py",
    "repo_tests/slm_frontend_publish_contract_test.py",
    "repo_tests/slm_frontend_atomic_publish_15610_test.py",
}


def strip_comments(text: str) -> str:
    """Drop whole-line comments before matching.

    Both implementations document the flip idiom in prose directly above the
    code that performs it -- the Ansible file carries
    `#     && mv -T .current.next current` at line 82 and the real task at 212.
    Matching raw text means a clause is satisfied by the explanation of the
    behaviour rather than the behaviour, so deleting the task and keeping the
    comment passes. Found by mutation: weakening the real task left every test
    green.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _sources() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name, path in IMPLEMENTATIONS.items():
        assert path.is_file(), f"the {name} publisher is missing or moved: {path}"
        out[name] = strip_comments(path.read_text(encoding="utf-8"))
    return out


def clause_violations(sources: Dict[str, str]) -> List[Tuple[str, str, List[str]]]:
    """(clause, why, implementations failing it) for every clause not met everywhere."""
    out = []
    for clause in CLAUSES:
        failing = [impl for impl, text in sources.items() if not re.search(clause.patterns[impl], text)]
        if failing:
            out.append((clause.name, clause.why, failing))
    return out


def test_the_sweep_reached_both_implementations() -> None:
    """Runs first: an empty registry passes every assertion below vacuously.

    Bound to implementations discovered, never to violations found.
    """
    assert (
        len(IMPLEMENTATIONS) >= MIN_IMPLEMENTATIONS
    ), f"only {len(IMPLEMENTATIONS)} publishers registered, floor is {MIN_IMPLEMENTATIONS}"
    for name, path in IMPLEMENTATIONS.items():
        assert path.is_file(), f"the {name} publisher is missing or moved: {path}"
        assert path.stat().st_size > 0, f"the {name} publisher is empty"


def test_every_clause_holds_in_every_implementation() -> None:
    violations = clause_violations(_sources())

    assert not violations, "the two SLM publishers no longer agree:\n" + "\n".join(
        f"  [{name}] not satisfied by: {', '.join(failing)}\n      {why}" for name, why, failing in violations
    )


@pytest.mark.parametrize("clause", CLAUSES, ids=lambda c: c.name)
def test_each_clause_is_stated_for_every_implementation(clause) -> None:
    """A clause missing a pattern for one side would silently exempt it.

    `clause_violations` only checks implementations the clause names, so an
    absent key is not a failure there -- it is an exemption nobody declared.
    """
    missing = set(IMPLEMENTATIONS) - set(clause.patterns)
    assert not missing, (
        f"clause {clause.name!r} states no pattern for {sorted(missing)}, so that "
        "implementation is exempt from it without anyone saying so"
    )


#: Below this the enumeration collapsed rather than the tree being clean. Bound
#: to files enumerated, never to publishers found.
_MIN_CANDIDATES = 400


def _tracked_candidates() -> List[str]:
    """Tracked files a publisher could live in, from ``git`` not a walk (#15955)."""
    return sorted(tracked_paths(REPO_ROOT, "*.sh", "*.yml", "*.yaml", "*.j2", "*.py"))


def test_the_candidate_sweep_reached_the_tree() -> None:
    """Runs first: an empty enumeration finds no unlisted publisher either."""
    found = _tracked_candidates()
    assert len(found) >= _MIN_CANDIDATES, (
        f"enumerated only {len(found)} candidate file(s) (floor {_MIN_CANDIDATES}) — "
        "the enumeration broke, so a clean result below asserts nothing."
    )


def test_no_unlisted_publisher_exists() -> None:
    """A third implementation in a third language is caught, not accommodated."""
    registered = {str(p.relative_to(REPO_ROOT)) for p in IMPLEMENTATIONS.values()}
    unlisted: List[str] = []

    # #15955: was `REPO_ROOT.rglob("*")` with a hand-written prefix prune. Two
    # defects, both mine, both invisible in CI:
    #
    # 1. The prune listed `.worktrees/` and not `.claude/worktrees/`, where this
    #    repository also keeps checkouts. 5,307 files from another checkout were
    #    scanned on every developer run. No false positive TODAY only because
    #    that worktree sits on a revision predating the publisher work -- one
    #    merge into it and this guard names paths its author has never seen.
    #
    # 2. `rglob("*")` DESCENDS into `node_modules` and filters afterwards, so the
    #    prune never protected the walk. A root-owned `node_modules` made the
    #    whole sweep die on PermissionError, red with no explanation.
    #
    # `git ls-files` fixes both by never entering either directory, so the prune
    # is deleted rather than extended.
    for rel in _tracked_candidates():
        path = REPO_ROOT / rel
        if rel in registered or rel in _NOT_PUBLISHERS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(h.search(text) for h in _PUBLISHER_HINTS):
            unlisted.append(rel)

    assert not unlisted, (
        "these look like SLM frontend publishers but are not registered in "
        "IMPLEMENTATIONS, so no clause is checked against them:\n  "
        + "\n  ".join(sorted(unlisted))
        + "\n\nRegister them, or add them to _NOT_PUBLISHERS with the reason."
    )


#: The one override value the user-frontend path uses (#15603). Anything
#: else -- including a typo of it -- must fail loudly rather than silently
#: changing which vite mode an actual deploy runs.
_KNOWN_BUILD_SCRIPT_OVERRIDE = "build"

_INCLUDE_TASKS_RE = re.compile(r"include_tasks:\s*\S*build_publish_slm_frontend\.yml\s*$")
_BUILD_SCRIPT_OVERRIDE_RE = re.compile(r'slm_frontend_publish_build_script:\s*"([^"]*)"')
_PUBLISH_DIR_RE = re.compile(r"slm_frontend_publish_dir:\s*(\S.*?)\s*$")
_PUBLISH_LABEL_RE = re.compile(r'slm_frontend_publish_label:\s*"([^"]*)"')


@dataclass(frozen=True)
class _CallSite:
    """One include_tasks call site of build_publish_slm_frontend.yml, as read from ansible source."""

    path: str
    line: int
    label: str
    dir_expr: str
    build_script: str  #: "" means unset -- the SLM path, defaulting to build:slm.


def _call_sites() -> List[_CallSite]:
    """Every include_tasks call site of build_publish_slm_frontend.yml, across the ansible tree.

    Reads label/dir/script together from the same vars: block (#17136):
    splitting them into separate single-purpose scans would mean re-deriving
    this exact indentation-aware block boundary twice, and the two scans
    silently drifting apart is exactly the kind of gap #17136 exists to close.
    """
    sites: List[_CallSite] = []
    for path in sorted((REPO_ROOT / "autobot-slm-backend" / "ansible").rglob("*.yml")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not _INCLUDE_TASKS_RE.search(line):
                continue
            indent = len(line) - len(line.lstrip(" "))
            # vars:/when:/tags: are SIBLING keys of include_tasks: (both
            # direct children of the same task-item mapping), not nested
            # under it, so they sit at the SAME indent -- only a `- ` list
            # marker at or below the *task item's own* indent (2 less, the
            # `- name:` line) starts the next task and ends this one.
            task_indent = max(indent - 2, 0)
            label = dir_expr = build_script = ""
            for follow in lines[i + 1 :]:
                follow_indent = len(follow) - len(follow.lstrip(" "))
                stripped = follow.lstrip(" ")
                if follow.strip() and follow_indent <= task_indent and stripped.startswith("-"):
                    break
                if follow.strip() and follow_indent < task_indent:
                    break
                if not label:
                    match = _PUBLISH_LABEL_RE.search(follow)
                    if match:
                        label = match.group(1)
                if not dir_expr:
                    match = _PUBLISH_DIR_RE.search(follow)
                    if match:
                        dir_expr = match.group(1).strip('"')
                if not build_script:
                    match = _BUILD_SCRIPT_OVERRIDE_RE.search(follow)
                    if match:
                        build_script = match.group(1)
            sites.append(
                _CallSite(
                    path=str(path.relative_to(REPO_ROOT)),
                    line=i + 1,
                    label=label,
                    dir_expr=dir_expr,
                    build_script=build_script,
                )
            )
    return sites


def _build_script_overrides() -> Dict[str, List[str]]:
    """path (relative to REPO_ROOT) -> the override found at each call site, in file order."""
    overrides: Dict[str, List[str]] = {}
    for site in _call_sites():
        overrides.setdefault(site.path, []).append(site.build_script)
    return overrides


#: A call site names the SLM dashboard's own directory either by the
#: established `slm_frontend_dir` variable (with or without a `default(...)`
#: fallback) or by a literal/templated path containing "autobot-slm-frontend"
#: -- every other call site publishes the general user-facing frontend
#: (`autobot-frontend`, or `autobot-vue`, its pre-rename directory name still
#: used by deploy-native-services.yml -- confirmed NOT the SLM frontend by
#: docs/developer/AUTOBOT_REFERENCE.md, "The SLM frontend is in
#: autobot-slm-frontend/, NOT autobot-vue"). Checked against every one of
#: this scan's own live call sites in test_call_site_classification_matches_
#: this_pin below, not just asserted.
def _publishes_slm_frontend(dir_expr: str) -> bool:
    return "slm_frontend_dir" in dir_expr or "autobot-slm-frontend" in dir_expr


def test_no_build_publish_slm_frontend_caller_overrides_away_from_a_known_script():
    """#17133 review: the shared task's build:slm default only protects the
    SLM UI's API base if every call site either leaves
    slm_frontend_publish_build_script unset (the SLM path) or sets it to
    exactly "build" (the user-frontend path, #15603) -- anything else would
    silently change which vite mode an actual deploy runs, the exact class
    of defect relaxing the "builds with build:slm" clause's ansible pattern
    to accept the templated form could otherwise hide.
    """
    overrides = _build_script_overrides()
    all_values = [v for values in overrides.values() for v in values]
    assert any(v == "" for v in all_values), "no unset (SLM-path) call site found -- the scan itself is broken"
    assert any(
        v == _KNOWN_BUILD_SCRIPT_OVERRIDE for v in all_values
    ), "no user-frontend override found -- the scan itself is broken"

    bad = {path: values for path, values in overrides.items() if any(v not in ("", "build") for v in values)}
    assert not bad, f"unexpected slm_frontend_publish_build_script override(s), expected '' or 'build': {bad}"


#: Every real call site, resolved by hand against its own dir_expr and cross-
#: checked in test_call_site_classification_matches_this_pin below -- names
#: what #17136 asks for explicitly, rather than trusting the heuristic alone.
_EXPECTED_SLM_LABELS = frozenset({"[PLAY 1] SLM", "Node update", "SLM"})


def _slm_sites_with_wrong_script(sites: List[_CallSite]) -> List[_CallSite]:
    """SLM-publishing call sites whose build_script has been overridden away from build:slm."""
    return [site for site in sites if _publishes_slm_frontend(site.dir_expr) and site.build_script]


def test_call_site_classification_matches_this_pin():
    """The heuristic's result, pinned per real site (#17136 AC2) -- a
    classification change here is a deliberate diff, not a silent drift.
    Checked per site, not by label: "SLM" labels two distinct call sites
    (slm_manager/tasks/main.yml and provision-fleet-roles.yml), so keying
    anything by label alone would silently drop one.

    Native deploy (frontend) and Frontend were the two labels #17136 could
    not resolve from their names alone: both publish `.../autobot-frontend`
    or `.../autobot-vue`, neither of which is the SLM frontend (confirmed
    against docs/developer/AUTOBOT_REFERENCE.md), so `build` is already
    correct at both -- no live defect, just an unresolved label.
    """
    sites = _call_sites()
    assert len(sites) >= 9, f"found only {len(sites)} call site(s) -- the scan itself is broken"

    for site in sites:
        expected_slm = site.label in _EXPECTED_SLM_LABELS
        actual_slm = _publishes_slm_frontend(site.dir_expr)
        assert actual_slm == expected_slm, (
            f"{site.path}:{site.line} ({site.label!r}, dir={site.dir_expr!r}) classified as "
            f"{'SLM' if actual_slm else 'user'} frontend, expected {'SLM' if expected_slm else 'user'}"
        )

    found_labels = {site.label for site in sites}
    expected_labels = _EXPECTED_SLM_LABELS | {
        "Fleet update (user frontend)",
        "Node update (user frontend)",
        "SLM co-located (user frontend)",
        "TLS rebuild (user frontend)",
        "Native deploy (frontend)",
        "Frontend",
    }
    assert found_labels >= expected_labels, f"a known call site's label moved or vanished: {sorted(found_labels)}"


def test_a_site_publishing_the_slm_frontend_leaves_the_build_script_unset():
    """#17136 AC1: build:slm only pins VITE_API_URL=/slm if the SLM's OWN call
    sites never override it -- the prior guard allowed "build" at any site,
    including one that publishes the SLM frontend itself.
    """
    wrong = _slm_sites_with_wrong_script(_call_sites())
    assert not wrong, (
        "these call sites publish the SLM frontend (their slm_frontend_publish_dir names it) "
        f"but override slm_frontend_publish_build_script away from build:slm: {wrong}"
    )


def test_the_slm_publish_check_catches_a_flipped_call_site():
    """Negative control (#17136 AC3): flip one real SLM site's script to "build" and confirm it's caught."""
    sites = _call_sites()
    slm_site = next(site for site in sites if _publishes_slm_frontend(site.dir_expr))
    flipped = _CallSite(
        path=slm_site.path,
        line=slm_site.line,
        label=slm_site.label,
        dir_expr=slm_site.dir_expr,
        build_script="build",
    )
    other_sites = [site for site in sites if site is not slm_site]

    wrong = _slm_sites_with_wrong_script(other_sites + [flipped])

    assert wrong == [flipped], f"flipping an SLM site's build_script to 'build' was not caught: {wrong}"
