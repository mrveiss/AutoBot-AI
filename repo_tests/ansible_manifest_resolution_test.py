# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Each ansible pip site resolves to the manifest it actually provisions (#15629).

Split out of ``ansible_requirements_parity_test.py`` when that file passed
MAX_LINES. The seam is the one the modules already draw: this file asserts the
**resolution** -- that the declared site->manifest table describes the tree, in
both directions, and that a venv is filled from one source shape -- while the
parity file asserts the **comparison** that resolution feeds, and owns the walk
and the baseline.

Splitting rather than raising a ceiling, per the standing rule; and splitting
here rather than at an arbitrary line count, because the two halves fail for
different reasons and a reader chasing one should not have to read the other.
"""

from __future__ import annotations

import pathlib

from repo_tests import ansible_manifest_resolution as resolution
from repo_tests.ansible_requirements_parity_test import (
    _NPU_VENV,
    _REPO_ROOT,
    ansible_declarations,
    requirement_files,
    unresolved_sites,
)

__all__: list[str] = []


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


def test_no_venv_is_provisioned_from_more_than_one_source_shape() -> None:
    """One venv, one kind of source. A venv fed by both has two sources of truth.

    A `requirements:` install reads a manifest; a `name:` list restates packages
    inline. Where both fill one venv, what a node ends up with depends on which
    entry point ran, and neither answer is wrong -- they are simply different
    machines, which is what makes the shape invisible to a comparison that only
    checks whether each floor agrees with its manifest (#15671).

    `MULTI_SOURCE_VENVS` is asserted by exact set equality, so it cannot be used
    to wave a new one through: a venv that starts being filled two ways fails,
    and an entry left behind after its venv was fixed fails just as loudly.
    """
    found = resolution.multi_source_venvs()
    recorded = frozenset(resolution.MULTI_SOURCE_VENVS)
    shapes = resolution.provisioning_shapes()
    unrecorded = sorted(found - recorded)
    stale = sorted(recorded - found)
    assert not unrecorded, (
        "These venvs are filled from BOTH a manifest and an inline `name:` list, so their "
        "contents depend on which ansible entry point ran. Move the inline packages into the "
        "manifest and install from it with `-c constraints/shared.txt`, as roles/npu-worker "
        "does (#15671):\n  " + "\n  ".join(f"{key}: {sorted(shapes[key])}" for key in unrecorded)
    )
    assert not stale, (
        "These MULTI_SOURCE_VENVS entries name a venv that is no longer filled two ways — the "
        "fix landed and the record did not. Delete them (#15684):\n  " + "\n  ".join(stale)
    )


def test_the_npu_worker_venv_is_filled_only_from_its_manifest() -> None:
    """The #15671 regression case, pinned at the venv the two paths collided on.

    Named rather than left to the record above because the record is a set of
    strings: emptied of this key it says nothing about WHY the key left, and the
    next role to add a convenient `name:` list here would only have to add one
    line to put it back. This asserts the positive — more than one ansible file
    fills this venv, every one of them reads a manifest, and the manifest they
    read is `autobot-npu-worker/requirements.txt` and nothing else.
    """
    shapes = resolution.provisioning_shapes()
    bindings = resolution.derived_bindings()
    assert _NPU_VENV in shapes, (
        f"{_NPU_VENV} is filled by no pip task the walk can see — roles/npu-worker and "
        "playbooks/deploy-native-services.yml both provision it, so this is a parser failure"
    )
    assert bindings.get(_NPU_VENV) == frozenset({resolution.NPU}), (
        f"{_NPU_VENV} resolves to {sorted(bindings.get(_NPU_VENV) or ())}, not to "
        f"{resolution.NPU} alone. The shape assertion below cannot see this: three files could "
        "each carry a `requirements:` and still read three DIFFERENT manifests, which is the same "
        "two-sources-of-truth defect one level down. One venv, one manifest (#15671)"
    )
    assert shapes[_NPU_VENV] == frozenset({resolution.MANIFEST_SOURCE}), (
        f"{_NPU_VENV} is filled from {sorted(shapes[_NPU_VENV])}. Every path into it must read "
        "autobot-npu-worker/requirements.txt; an inline `name:` list here is the defect #15671 "
        "removed, where the role installed five packages the manifest did not declare and only "
        "the other path applied constraints/shared.txt"
    )
    filling = resolution.files_filling(_NPU_VENV)
    assert len(filling) > 1, (
        f"only {sorted(filling)} fills {_NPU_VENV}; the collision this pins needs at least two "
        "files resolving to one venv, so a rename that split them would make this vacuous"
    )
