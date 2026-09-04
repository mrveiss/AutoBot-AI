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

Every guard below is two pieces (#15671): a pure detector taking the table, the
bindings and a key function as arguments, and a test that hands it the live
tree. The detectors are separated for one reason -- a detector that only ever
sees the live tree cannot be shown to REJECT anything, and the repo standard is
a contrast pair per detector. `ansible_manifest_resolution_contrast_test.py`
supplies those pairs against synthetic tables; this file supplies the live half.

Each comparison also states the REACH it needs before it compares. A floor bound
to the number of findings passes in silence when the parser breaks, and this
whole issue family is about a guard that could not see what it claimed to read.
"""

from __future__ import annotations

from typing import Callable

from repo_tests import ansible_manifest_resolution as resolution
from repo_tests.ansible_requirements_parity_test import (
    _MIN_DERIVED_BINDINGS,
    _MIN_PIP_SITES,
    _MIN_PROVISIONED_VENVS,
    _MIN_REQUIREMENT_FILES,
    _NPU_VENV,
    _REPO_ROOT,
    ansible_declarations,
    requirement_files,
)

__all__: list[str] = []

#: The identity key function, for fixtures whose environments are already keys.
KeyOf = Callable[[str, str], str]


def _reached(measured: int, minimum: int, what: str) -> None:
    """State the sweep's reach before comparing findings against it.

    Bound to entries discovered, never to findings: a floor that counts findings
    passes when the parser returns nothing, and then fixing a real finding trips
    it. Both failure directions are wrong, and one of them is silent.
    """
    assert measured >= minimum, f"the walk reached only {measured} {what} (floor {minimum}) — it has stopped reading"


# --- detectors: pure, so the contrast file can feed them a tree that must fail ---


def unresolved_and_stale_sites(table: dict, walked) -> tuple[list, list]:
    """``(sites no entry names, entries no site matches)`` -- drift in both directions."""
    return sorted(set(walked) - set(table)), sorted(set(table) - set(walked))


def unread_declared_manifests(table: dict, known) -> set[str]:
    """Declared manifests that no requirements walk reads -- a rename, or a typo."""
    declared = {m for entry in table.values() for m in entry.manifests if m != resolution.EVERY_MANIFEST}
    return declared - set(known)


def undeclared_installs(table: dict, bindings: dict, key_of: KeyOf) -> list[str]:
    """Manifests the tree installs into a venv that the venv's entry does not name."""
    found = []
    for site, entry in sorted(table.items()):
        missing = bindings.get(key_of(*site), frozenset()) - set(entry.manifests)
        if missing and resolution.EVERY_MANIFEST not in entry.manifests:
            found.append(f"{site[0]} [{site[1]}] installs {sorted(missing)}, not declared")
    return found


def dropped_declarations(table: dict, bindings: dict, exceptions: dict, key_of: KeyOf) -> list[str]:
    """The reverse: a declared manifest the tree no longer installs into that venv.

    #15671 removed the `if not derived: continue` this used to open with. The
    skip was there so a site the walk cannot see would not fail for the wrong
    reason -- but deriving nothing is EXACTLY what a site whose install task was
    deleted looks like, so the skip excused the drift it existed to catch. A
    structurally underivable binding now says so in `LOGICAL_ONLY`, by name.
    """
    found = []
    for site, entry in sorted(table.items()):
        if resolution.EVERY_MANIFEST in entry.manifests:
            continue
        derived = bindings.get(key_of(*site), frozenset())
        for manifest in entry.manifests:
            if manifest in derived or (site[0], manifest) in exceptions:
                continue
            found.append(f"{site[0]} [{site[1]}] declares {manifest}, nothing installs it")
    return found


def stale_exceptions(table: dict, bindings: dict, exceptions: dict, key_of: KeyOf) -> list[str]:
    """LOGICAL_ONLY shrinks: an exception that stopped being needed must go."""
    found = []
    for (path, manifest), reason in sorted(exceptions.items()):
        sites = [key for key in table if key[0] == path]
        if not sites:
            found.append(f"{path} is no longer a declared site")
        elif manifest not in table[sites[0]].manifests:
            found.append(f"{path} no longer declares {manifest}")
        elif manifest in bindings.get(key_of(*sites[0]), frozenset()):
            found.append(f"{path} now derivably installs {manifest} — drop the exception ({reason})")
    return found


def multi_source_drift(shapes: dict, recorded) -> tuple[list, list]:
    """``(venvs newly filled two ways, records whose venv was fixed)``."""
    found = {key for key, kinds in shapes.items() if len(kinds) > 1}
    return sorted(found - set(recorded)), sorted(set(recorded) - found)


def one_manifest_findings(
    environment: str, shapes: dict, bindings: dict, per_file: dict, filling, expected: str
) -> list[str]:
    """Every way one venv can fail "filled from one manifest, by every path into it".

    `bindings` unions across files, so one file resolving makes the venv look
    bound; `per_file` is what proves the OTHER paths read the same manifest, and
    `filling` catches a path that fills the venv with no resolvable install at
    all -- `_resolve_manifest` returning None drops out of the union silently.
    """
    if environment not in shapes:
        return [f"{environment}: no pip task the walk can see fills it"]
    found = []
    if shapes[environment] != frozenset({resolution.MANIFEST_SOURCE}):
        found.append(f"{environment}: filled from {sorted(shapes[environment])}, not from a manifest alone")
    if bindings.get(environment) != frozenset({expected}):
        found.append(f"{environment}: resolves to {sorted(bindings.get(environment) or ())}, not {expected} alone")
    if len(per_file) < 2:
        found.append(f"{environment}: only {sorted(per_file)} installs into it; this pins a two-path collision")
    for path in sorted(set(filling) - set(per_file)):
        found.append(f"{environment}: {path} fills it with no install this walk can resolve to a manifest")
    for path, manifests in sorted(per_file.items()):
        if manifests != frozenset({expected}):
            found.append(f"{environment}: {path} installs {sorted(manifests)}, not {expected}")
    return found


# --- the live tree ---------------------------------------------------------


def test_every_declaration_site_resolves_to_the_manifests_it_provisions() -> None:
    """An unresolved site is a finding: it cannot be compared, so it must not be silent."""
    walked = ansible_declarations()[1]
    _reached(len(walked), _MIN_PIP_SITES, "pip declaration sites")
    unresolved, stale = unresolved_and_stale_sites(resolution.SITE_MANIFESTS, walked)
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
    files = requirement_files()
    _reached(len(files), _MIN_REQUIREMENT_FILES, "requirements manifests")
    known = {path.relative_to(_REPO_ROOT).as_posix() for path in files}
    unread = unread_declared_manifests(resolution.SITE_MANIFESTS, known)
    assert not unread, f"declared manifests no walk reads: {sorted(unread)}"


def test_the_declared_resolution_matches_what_ansible_states() -> None:
    """Where the tree binds a venv to a manifest, the declared entry must contain it."""
    bindings = resolution.derived_bindings()
    _reached(len(bindings), _MIN_DERIVED_BINDINGS, "derived venv->manifest bindings")
    mismatched = undeclared_installs(resolution.SITE_MANIFESTS, bindings, resolution.environment_key)
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

    Every binding the walk cannot derive is named in `LOGICAL_ONLY` with its
    cause. No site is skipped for deriving nothing, because that is precisely
    what a deleted install task looks like (#15671).
    """
    bindings = resolution.derived_bindings()
    _reached(len(bindings), _MIN_DERIVED_BINDINGS, "derived venv->manifest bindings")
    dropped = dropped_declarations(
        resolution.SITE_MANIFESTS, bindings, resolution.LOGICAL_ONLY, resolution.environment_key
    )
    assert not dropped, (
        "These SITE_MANIFESTS entries name a manifest the ansible tree no longer "
        "installs into that venv. Either the wiring was removed and the entry is "
        "stale, or the binding is real but underivable and belongs in "
        "LOGICAL_ONLY with its reason:\n  " + "\n  ".join(dropped)
    )


def test_no_logical_only_exception_is_stale() -> None:
    """An exception list that is never re-examined is a second table with the same drift."""
    bindings = resolution.derived_bindings()
    _reached(len(bindings), _MIN_DERIVED_BINDINGS, "derived venv->manifest bindings")
    stale = stale_exceptions(resolution.SITE_MANIFESTS, bindings, resolution.LOGICAL_ONLY, resolution.environment_key)
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
    shapes = resolution.provisioning_shapes()
    _reached(len(shapes), _MIN_PROVISIONED_VENVS, "venvs with a known source shape")
    unrecorded, stale = multi_source_drift(shapes, resolution.MULTI_SOURCE_VENVS)
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
    fills this venv, every one of them reads a manifest, and the manifest each
    of them reads is `autobot-npu-worker/requirements.txt` and nothing else.
    """
    shapes = resolution.provisioning_shapes()
    _reached(len(shapes), _MIN_PROVISIONED_VENVS, "venvs with a known source shape")
    findings = one_manifest_findings(
        _NPU_VENV,
        shapes,
        resolution.derived_bindings(),
        resolution.manifests_installed_by_file(_NPU_VENV),
        resolution.files_filling(_NPU_VENV),
        resolution.NPU,
    )
    assert not findings, (
        "roles/npu-worker, playbooks/deploy-native-services.yml and update-all-nodes.yml all "
        "fill this venv, and #15671 is the claim that they now read one manifest between "
        "them:\n  " + "\n  ".join(findings)
    )
