# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Ansible and requirements must not state different versions of one package (#15568).

`openvino` was restated as a literal in seven files, so every dependabot bump went
red until six of them were hand-edited (#15408). #10524 built the mechanism that
fixes that shape -- `constraints/shared.txt` plus `scripts/check_constraint_drift.py`
-- but that guard reads only `requirements*.txt`. Ansible declares packages too, in
four different shapes, and nothing has ever compared the two sides. This test is
that comparison.

The four ansible shapes, all of which really install:

  * an `ansible.builtin.pip` / `pip` task's `name:` (a string or a list);
  * `python_security_updates`, a `package: minimum_version` map that
    `roles/dependency_patching` renders into a requirements file and pip-installs;
  * `packages.python` lists in `inventory/group_vars/*`;
  * `*_python_packages` list vars (`roles/slm_agent`).

Which manifest a declaration is compared against (#15629)
--------------------------------------------------------

The first pass compared every declaration against the UNION of every manifest in
the tree, so a declaration matching *any* manifest's text read as agreement. That
is the wrong direction to be wrong in: a role provisions ONE component, so a floor
that matches some other component's manifest is stale where it is used and looks
exactly like a floor that is correct. `roles/ai-stack` carried `fastapi>=0.115.0`
and `uvicorn[standard]>=0.35.0` against an ai-stack manifest declaring `>=0.141.1`
and `>=0.52.4`; `docs/guides/requirements-local.txt` states the older pair
verbatim, the union found it, and the guard stayed silent until #15623 raised
them by reading rather than by failing.

Each site is now resolved to the manifest(s) it actually provisions, through
`repo_tests/ansible_manifest_resolution.py`. That resolution is declared per site
and cross-checked against the bindings the ansible tree states about itself, and
it is exhaustive: a declaration site the walk reaches that the table does not name
is a finding, not a skipped comparison. The two ai-stack floors are pinned as a
regression case below, proved in both directions: flagged against the pre-#15623
tree, silent against this one.

Two assertions, deliberately of different strengths:

`test_no_constrained_package_carries_a_version_in_ansible` is absolute. A package
`constraints/shared.txt` pins may never carry a version at an ansible site, for the
reason the constraints file states in its own header: ansible can co-locate roles on
one host, so two floors for one library make pip unsatisfiable and skew the numpy ABI
on embeddings one role writes and another reads. This is the ansible half of
`check_constraint_drift.py`, which cannot see these files.

`test_every_cross_manifest_divergence_is_in_the_baseline` is ratcheted through
`ansible_pip_parity_baseline.txt`, because the backlog this test first measured
was 55 and asserting it flat would have reddened the tree rather than described
it. That backlog is now zero -- #15597 raised the twelve `python_security_updates`
floors that sat below the shipped requirements, #15598 the sixteen role pip
tasks, and #15596 stripped the twenty-seven restated versions out of the three
dormant `packages.python` lists -- and sharpening the comparison to the site's own
manifest adds none, so the baseline still carries no entries and both assertions
bite on the first offence. The file only shrinks, and a stale entry fails just as
loudly as a new divergence; it is kept, empty, as the mechanism rather than
deleted, because deleting it would make the next divergence's fix a matter of
re-inventing the ratchet.

Agreement is compared as specifier text, not as a resolved range. `>=0.115.0` and
`==0.115.0` are treated as different statements of the same version because they are:
one manifest moving to a pin while another keeps a floor is exactly the drift #15408
describes, and a range-aware comparison would call it equal and miss it.
"""

from __future__ import annotations

import functools
import pathlib
import re
from typing import NamedTuple

import pytest

yaml = pytest.importorskip("yaml")

from repo_tests import ansible_manifest_resolution as resolution  # noqa: E402

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CONSTRAINTS = _REPO_ROOT / "constraints" / "shared.txt"
# Named `..._pip_parity_...`, NOT `..._requirements_...`: this file RECORDS
# divergences (none, as of #15596/#15597/#15598), it does not DECLARE
# dependencies. `declared_distributions.py`
# globs `*requirements*.txt` to find manifests it must read as declaration
# sources, and `declared_distributions_test.py` fails on any tracked file
# matching that glob which the oracle does not read. A recorder that reads as
# a manifest would have every package name in it counted as "declared here"
# by three downstream guards (#15518). The distinction is the one #15566 is
# about: a recorder holds a name as data, a manifest holds it as a claim.
_BASELINE = pathlib.Path(__file__).with_name("ansible_pip_parity_baseline.txt")

# `.claude` holds Claude Code's own per-session worktree copies of this repo
# (see .git/info/exclude). Without it the walk reads another session's
# requirements manifests as if they were this tree's: measured 65 files
# locally against 37 with it excluded. CI never has the directory, so the
# merge gate was unaffected and the omission was invisible there -- which is
# exactly why it belongs in the list rather than in a note.
_EXCLUDE_DIRS = ("node_modules", ".worktrees", ".claude", ".git", "__pycache__")
_PIP_KEYS = ("pip", "ansible.builtin.pip")
_REQUIREMENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(.*)$")
_SPECIFIER = re.compile(r"^(==|>=|<=|~=|!=|>|<)")

# Floors, not censuses: they measure how far the walk REACHES, never how much it
# finds. Fixing a divergence must never trip one -- only a parser that has quietly
# stopped matching the files it claims to read.
_MIN_ANSIBLE_DOCUMENTS = 250  # 329 parsed on 2026-09-04
_MIN_PIP_SITES = 15  # 18 carry at least one name: entry
_MIN_ANSIBLE_DECLARATIONS = 95  # 115, versioned and bare together
_MIN_REQUIREMENT_FILES = 30  # 34
_MIN_REQUIREMENT_PACKAGES = 140  # 161
# The resolver's own reach (#15629). `_MIN_DERIVED_BINDINGS` counts the venvs the
# ansible tree itself binds to a repo manifest -- a resolver that stopped matching
# `requirements:` tasks or `build-filtered-requirements.sh` rewrites would derive
# nothing and leave the declared table cross-checked against an empty set, which
# reads as agreement. `_MIN_SITES_WITH_A_MANIFEST` is the same guarantee for the
# declared half: emptying entries out to `()` would silence their comparison.
_MIN_DERIVED_BINDINGS = 5  # 7
_MIN_SITES_WITH_A_MANIFEST = 11  # 13 of 18; 2 are host-wide, 3 have no manifest
# Exact, unlike the others: `constraints/shared.txt` guards two packages and a
# floor of 2 is the whole population. Legitimately shrinking that file to one
# guarded package trips this as a walk failure, which it would not be -- so
# raise the floor with the file rather than reading a red here as a parser bug.
_MIN_CONSTRAINED_PACKAGES = 2  # numpy, openvino

_AI_STACK_SITE = ("autobot-slm-backend/ansible/roles/ai-stack/tasks/main.yml", "{{ ai_install_dir }}/venv")
# The regression case for #15629, frozen at d69c8fd70^ -- the tree as it stood
# before #15623 raised these two floors by hand. Frozen, not read live, because
# the demonstration is a fact about that tree: the union carried `>=0.115.0` and
# `>=0.35.0` (`docs/guides/requirements-local.txt` states both verbatim, and the
# windows NPU worker's manifest carried `uvicorn[standard]>=0.24.0`), while the
# manifest roles/ai-stack provisions against carried neither. Read live, the
# demonstration would evaporate the first time that guide is bumped.
_PRE_15623_FLOORS = (("fastapi", ">=0.115.0"), ("uvicorn", ">=0.35.0"))
_PRE_15623_AI_MANIFEST = {"fastapi": {">=0.141.1"}, "uvicorn": {">=0.52.4"}}
_PRE_15623_UNION = {
    "fastapi": {">=0.141.1", ">=0.115.0", ">=0.104.0", "==0.141.1"},
    "uvicorn": {">=0.52.4", ">=0.35.0", ">=0.24.0", "==0.52.4"},
}


class Declaration(NamedTuple):
    """One package named at one ansible declaration site."""

    path: str
    context: str
    environment: str  # the pip task's virtualenv/executable text; "" for the var shapes
    package: str
    specifier: str  # "" for a bare name, which is the shape the SSOT wants

    @property
    def key(self) -> str:
        return f"{self.path}::{self.package}"

    @property
    def site(self) -> tuple[str, str]:
        return self.path, self.environment


def _normalise(name: str) -> str:
    """PEP 503 normalization so Pillow / pillow and nltk / NLTK compare equal."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _split(text: str) -> tuple[str, str] | None:
    """``'numpy>=2.0  # note'`` -> ``('numpy', '>=2.0')``; a non-requirement -> None."""
    stripped = text.split("#", 1)[0].split(";", 1)[0].strip()
    match = _REQUIREMENT.match(stripped)
    if match is None:
        return None
    remainder = match.group(2).strip()
    if remainder and not _SPECIFIER.match(remainder):
        return None
    return _normalise(match.group(1)), re.sub(r"\s+", "", remainder)


def _strings(value: object) -> list[str]:
    """A pip ``name:`` is a single string or a list of them."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _environment(task: dict) -> str:
    """Which environment a pip task installs into -- the key a site resolves through."""
    for field in ("virtualenv", "executable", "chdir"):
        if isinstance(task.get(field), str):
            return task[field]
    return ""


def _sites(key: object, value: object) -> list[tuple[str, str, list[str]]]:
    """``(context, environment, raw entries)`` for each declaration shape ``key`` opens."""
    found: list[tuple[str, str, list[str]]] = []
    if key in _PIP_KEYS and isinstance(value, dict):
        found.append((f"{key}:name", _environment(value), _strings(value.get("name"))))
    if key == "packages" and isinstance(value, dict):
        found.append(("packages.python", "", _strings(value.get("python"))))
    if key == "python_security_updates" and isinstance(value, dict):
        floors = [f"{pkg}>={ver}" for pkg, ver in value.items()]
        found.append(("python_security_updates", "", floors))
    if isinstance(key, str) and key.endswith("_python_packages") and isinstance(value, list):
        found.append((key, "", _strings(value)))
    return [site for site in found if site[2]]


def _walk(node: object, path: str, sites: set[tuple[str, str]]) -> list[Declaration]:
    """Every declaration reachable from ``node``, recording the sites it passed."""
    found: list[Declaration] = []
    if isinstance(node, dict):
        for key, value in node.items():
            for context, environment, entries in _sites(key, value):
                sites.add((path, environment))
                found.extend(_declarations(path, context, environment, entries))
            found.extend(_walk(value, path, sites))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk(item, path, sites))
    return found


def _declarations(path: str, context: str, environment: str, entries: list[str]) -> list[Declaration]:
    parsed = (_split(entry) for entry in entries)
    return [Declaration(path, context, environment, name, spec) for name, spec in filter(None, parsed)]


@functools.cache
def ansible_declarations() -> tuple[tuple[Declaration, ...], frozenset[tuple[str, str]], int]:
    """Every ansible pip declaration, the sites walked, and the documents parsed."""
    declarations: list[Declaration] = []
    sites: set[tuple[str, str]] = set()
    documents = resolution.ansible_documents()
    for relative, document in documents:
        declarations.extend(_walk(document, relative, sites))
    return tuple(declarations), frozenset(sites), len(documents)


def requirement_files() -> list[pathlib.Path]:
    """The same set ``scripts/check_constraint_drift.py`` guards, plus the SSOT."""
    files: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()
    for pattern in ("requirements*.txt", "requirements*/*.txt"):
        for path in _REPO_ROOT.rglob(pattern):
            if any(part in _EXCLUDE_DIRS for part in path.parts) or path in seen:
                continue
            seen.add(path)
            files.append(path)
    return sorted(files)


def _specifiers(paths: list[pathlib.Path]) -> dict[str, set[str]]:
    """``package -> every version specifier text stated for it``."""
    stated: dict[str, set[str]] = {}
    for path in paths:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            parsed = _split(line)
            if parsed is not None and parsed[1]:
                stated.setdefault(parsed[0], set()).add(parsed[1])
    return stated


@functools.cache
def requirement_specifiers() -> dict[str, set[str]]:
    return _specifiers(requirement_files() + [_CONSTRAINTS])


@functools.cache
def _manifest_specifiers(manifests: tuple[str, ...]) -> dict[str, set[str]]:
    """What one site's OWN manifests state -- the union only where a site declares it."""
    if resolution.EVERY_MANIFEST in manifests:
        return requirement_specifiers()
    return _specifiers([_REPO_ROOT / manifest for manifest in manifests])


def constrained_packages() -> set[str]:
    return set(_specifiers([_CONSTRAINTS]))


def baseline_keys() -> list[str]:
    lines = _BASELINE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def _contradicts(specifier: str, stated: set[str] | None) -> bool:
    """The comparison itself: a package the manifest states, in text this does not match."""
    return bool(specifier) and bool(stated) and specifier not in stated


def unresolved_sites() -> list[tuple[str, str]]:
    """Sites the walk reached that no resolution names -- a new role, or a renamed venv."""
    return sorted(ansible_declarations()[1] - set(resolution.SITE_MANIFESTS))


@functools.cache
def _classified() -> tuple[dict[str, Declaration], dict[tuple[str, str], frozenset[str]]]:
    """``(divergences, unanchored packages per site)`` over every versioned declaration."""
    diverging: dict[str, Declaration] = {}
    unanchored: dict[tuple[str, str], set[str]] = {}
    for declaration in ansible_declarations()[0]:
        if not declaration.specifier:
            continue
        resolved = resolution.SITE_MANIFESTS.get(declaration.site)
        if resolved is None:  # an unresolved site cannot agree with anything
            diverging[declaration.key] = declaration
            continue
        stated = _manifest_specifiers(resolved.manifests).get(declaration.package)
        if _contradicts(declaration.specifier, stated):
            diverging[declaration.key] = declaration
        elif not stated:
            unanchored.setdefault(declaration.site, set()).add(declaration.package)
    return diverging, {site: frozenset(packages) for site, packages in unanchored.items()}


def divergences() -> dict[str, Declaration]:
    """``path::package -> declaration`` for an ansible version its own manifest contradicts."""
    return _classified()[0]


def test_the_walk_reaches_the_manifests_it_claims_to_read() -> None:
    """A parser that matches nothing would pass every assertion below in silence."""
    declarations, sites, documents = ansible_declarations()
    stated = requirement_specifiers()
    bound = [entry for entry in resolution.SITE_MANIFESTS.values() if entry.manifests]
    assert documents >= _MIN_ANSIBLE_DOCUMENTS, f"parsed only {documents} ansible documents"
    assert len(sites) >= _MIN_PIP_SITES, f"found only {len(sites)} pip declaration sites"
    assert len(declarations) >= _MIN_ANSIBLE_DECLARATIONS, f"only {len(declarations)} declarations"
    assert len(requirement_files()) >= _MIN_REQUIREMENT_FILES
    assert len(stated) >= _MIN_REQUIREMENT_PACKAGES, f"only {len(stated)} versioned packages"
    assert len(constrained_packages()) >= _MIN_CONSTRAINED_PACKAGES
    assert len(resolution.derived_bindings()) >= _MIN_DERIVED_BINDINGS, "the resolver derived nothing"
    assert len(bound) >= _MIN_SITES_WITH_A_MANIFEST, f"only {len(bound)} sites resolve to a manifest"


def test_every_declaration_site_resolves_to_the_manifests_it_provisions() -> None:
    """An unresolved site is a finding: it cannot be compared, so it must not be silent."""
    unresolved = unresolved_sites()
    stale = sorted(set(resolution.SITE_MANIFESTS) - ansible_declarations()[1])
    assert not unresolved, (
        "These ansible pip declaration sites resolve to no manifest. Add an entry to "
        "SITE_MANIFESTS in repo_tests/ansible_manifest_resolution.py naming the manifest(s) "
        "the site provisions -- or an empty tuple and the reason it has none (#15629):\n  "
        + "\n  ".join(f"{path} [{environment or 'no venv'}]" for path, environment in unresolved)
    )
    assert not stale, (
        "These SITE_MANIFESTS entries match no declaration site any more — the task was "
        "removed or its virtualenv renamed. Delete them:\n  " + "\n  ".join(map(str, stale))
    )


def test_every_declared_manifest_exists_and_is_read() -> None:
    """A renamed manifest must fail here, not resolve to an empty specifier set."""
    known = {path.relative_to(_REPO_ROOT).as_posix() for path in requirement_files()}
    declared = {
        manifest
        for entry in resolution.SITE_MANIFESTS.values()
        for manifest in entry.manifests
        if manifest != resolution.EVERY_MANIFEST
    }
    assert declared <= known, f"declared manifests no walk reads: {sorted(declared - known)}"


def test_the_declared_resolution_matches_what_ansible_states() -> None:
    """Where the tree binds a venv to a manifest, the declared entry must contain it."""
    bindings = resolution.derived_bindings()
    mismatched = []
    for site, entry in sorted(resolution.SITE_MANIFESTS.items()):
        derived = bindings.get(resolution.environment_key(*site), frozenset())
        missing = derived - set(entry.manifests)
        if missing and resolution.EVERY_MANIFEST not in entry.manifests:
            mismatched.append(f"{site[0]} [{site[1]}] installs {sorted(missing)}, not declared")
    assert not mismatched, (
        "The ansible tree installs manifests into these venvs that their SITE_MANIFESTS "
        "entries do not name:\n  " + "\n  ".join(mismatched)
    )


def test_every_declared_manifest_is_still_installed() -> None:
    """The other direction: a declared manifest whose install task has gone.

    Containment on its own is one-directional. It catches a manifest the tree
    installs and the table omits, and misses the reverse -- an entry that keeps
    naming a manifest after its install task is deleted. `derived` stays a
    subset of `declared`, nothing fires, and the table quietly stops describing
    the tree, which is the drift this module exists to prevent.

    Only sites with at least one derivable edge are checked, because a site the
    walk cannot see at all would otherwise fail for the wrong reason.
    `LOGICAL_ONLY` names the genuine exceptions with their cause.
    """
    bindings = resolution.derived_bindings()
    dropped = []
    for site, entry in sorted(resolution.SITE_MANIFESTS.items()):
        derived = bindings.get(resolution.environment_key(*site), frozenset())
        if not derived or resolution.EVERY_MANIFEST in entry.manifests:
            continue
        for manifest in entry.manifests:
            if manifest in derived or (site[0], manifest) in resolution.LOGICAL_ONLY:
                continue
            dropped.append(f"{site[0]} [{site[1]}] declares {manifest}, nothing installs it")

    assert not dropped, (
        "These SITE_MANIFESTS entries name a manifest the ansible tree no longer "
        "installs into that venv. Either the wiring was removed and the entry is "
        "stale, or the binding is real but underivable and belongs in "
        "LOGICAL_ONLY with its reason:\n  " + "\n  ".join(dropped)
    )


def test_no_logical_only_exception_is_stale() -> None:
    """LOGICAL_ONLY shrinks. An exception that stopped being needed must go.

    An exception list that is never re-examined becomes a second table with the
    same drift problem one level down — so each entry is checked against both
    the declaration it excuses and the walk it excuses it from.
    """
    stale = []
    for (path, manifest), reason in sorted(resolution.LOGICAL_ONLY.items()):
        sites = [key for key in resolution.SITE_MANIFESTS if key[0] == path]
        if not sites:
            stale.append(f"{path} is no longer a declared site")
            continue
        site = sites[0]
        if manifest not in resolution.SITE_MANIFESTS[site].manifests:
            stale.append(f"{path} no longer declares {manifest}")
            continue
        if manifest in resolution.derived_bindings().get(resolution.environment_key(*site), frozenset()):
            stale.append(f"{path} now derivably installs {manifest} — drop the exception ({reason})")

    assert not stale, "LOGICAL_ONLY carries entries that no longer describe the tree:\n  " + "\n  ".join(stale)


def test_the_pre_15623_ai_stack_floors_are_a_regression_case() -> None:
    """The two floors #15623 raised by hand: flagged then, silent now (#15629)."""
    for package, specifier in _PRE_15623_FLOORS:
        assert not _contradicts(specifier, _PRE_15623_UNION[package]), (
            f"{package}{specifier} must read as agreement against the pre-#15623 UNION — "
            "that blindness is the bug this test pins"
        )
        assert _contradicts(
            specifier, _PRE_15623_AI_MANIFEST[package]
        ), f"{package}{specifier} must diverge from the manifest roles/ai-stack provisions"
    entry = resolution.SITE_MANIFESTS[_AI_STACK_SITE]
    stated = _manifest_specifiers(entry.manifests)
    live = [d for d in ansible_declarations()[0] if d.site == _AI_STACK_SITE and d.specifier]
    named = {d.package for d in live}
    assert {"fastapi", "uvicorn"} <= named, f"the ai-stack list no longer versions both: {sorted(named)}"
    assert not [
        d for d in live if _contradicts(d.specifier, stated.get(d.package))
    ], "roles/ai-stack has drifted from its own manifest again"


def test_no_constrained_package_carries_a_version_in_ansible() -> None:
    """`constraints/shared.txt` is the only place a guarded version may be written."""
    guarded = constrained_packages()
    offenders = [
        f"{d.path} [{d.context}] declares {d.package}{d.specifier}"
        for d in ansible_declarations()[0]
        if d.specifier and d.package in guarded
    ]
    assert not offenders, (
        "These ansible sites restate a version constraints/shared.txt already pins.\n  "
        + "\n  ".join(sorted(offenders))
        + "\nFix: drop the specifier and pass "
        "`-c {{ code_source_dir | default('/opt/autobot/code_source') }}/constraints/shared.txt`"
        " in extra_args, as roles/npu-worker and roles/tts-worker do."
    )


def test_every_cross_manifest_divergence_is_in_the_baseline() -> None:
    """A package may not be versioned one way in ansible and another in its own manifest."""
    found = divergences()
    unlisted = sorted(set(found) - set(baseline_keys()))
    detail = [
        f"{key}: ansible {found[key].specifier}, "
        f"{sorted(resolution.SITE_MANIFESTS[found[key].site].manifests)} state "
        f"{sorted(_manifest_specifiers(resolution.SITE_MANIFESTS[found[key].site].manifests).get(found[key].package, ()))}"
        for key in unlisted
        if found[key].site in resolution.SITE_MANIFESTS
    ]
    assert not unlisted, (
        "New ansible/requirements version divergence:\n  "
        + "\n  ".join(detail or unlisted)
        + f"\nFix the declaration. {_BASELINE.name} only shrinks — adding a line to it"
        " to clear this failure is not the fix (#15568)."
    )


def test_the_baseline_carries_no_stale_entry() -> None:
    """An entry that no longer diverges exempts nothing while looking authoritative."""
    keys = baseline_keys()
    assert len(keys) == len(set(keys)), "duplicate entries in the baseline"
    stale = sorted(set(keys) - set(divergences()))
    assert not stale, (
        "These baseline entries no longer diverge — the declaration was fixed or "
        "removed. Delete them:\n  " + "\n  ".join(stale)
    )


def test_every_unanchored_floor_is_recorded_at_its_site() -> None:
    """A floor its own manifest does not declare is visible, not silently uncompared."""
    measured = _classified()[1]
    wrong = []
    for site, entry in sorted(resolution.SITE_MANIFESTS.items()):
        found = measured.get(site, frozenset())
        recorded = frozenset(entry.unanchored)
        if found != recorded:
            wrong.append(f"{site[0]} [{site[1] or 'no venv'}]: found {sorted(found)}, recorded {sorted(recorded)}")
    assert not wrong, (
        "These sites version a package their own manifests do not declare, and the "
        "`unanchored=` record in SITE_MANIFESTS no longer matches. The union used to hide "
        "these behind another component's text; record them or drop the floor (#15629):\n  " + "\n  ".join(wrong)
    )
