# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The contrast half of the resolution guards: what each detector must REJECT (#15671).

`ansible_manifest_resolution_test.py` runs every detector against the live
ansible tree, which is green -- and a detector that has only ever been shown a
green tree has proved nothing. It could return an empty list unconditionally and
every one of those tests would still pass. The repo standard is a contrast pair
per detector: a fixture that SHOULD trip it and one that should not.

Nothing here reads the repository. Every fixture is a three-line table, and the
detectors take the table, the bindings and the key function as arguments for
exactly that reason -- a detector that can only see the live tree cannot be
handed a broken one.

The sharpest pair is `test_a_binding_whose_install_task_vanished_is_a_finding`.
`dropped_declarations` used to open with `if not derived: continue`, so a site
whose `requirements:` install was replaced by an inline `name:` list derived
nothing, was skipped, and kept its stale declared manifest through this guard,
the forward-resolution guard and the multi-source guard alike. That skip is
gone; this is the fixture that says so.
"""

from __future__ import annotations

from repo_tests import ansible_manifest_resolution as resolution
from repo_tests.ansible_manifest_resolution_test import (
    dropped_declarations,
    multi_source_drift,
    one_manifest_findings,
    stale_exceptions,
    undeclared_installs,
    unread_declared_manifests,
    unresolved_and_stale_sites,
)

__all__: list[str] = []

_SITE_A = ("roles/alpha/tasks/main.yml", "/opt/fixture/alpha/venv")
_SITE_B = ("roles/beta/tasks/main.yml", "/opt/fixture/beta/venv")
_ALPHA = "alpha/requirements.txt"
_BETA = "beta/requirements.txt"
_VENV = "/opt/fixture/alpha/venv"


def _entry(*manifests: str) -> resolution.Resolution:
    return resolution.Resolution(manifests, "a fixture table, not the tree")


def _verbatim(_path: str, environment: str) -> str:
    """The identity key function: a fixture's environments are already keys."""
    return environment


# --- unresolved_and_stale_sites -------------------------------------------


def test_a_site_no_entry_names_and_an_entry_no_site_matches_are_both_findings() -> None:
    table = {_SITE_A: _entry(_ALPHA)}
    unresolved, stale = unresolved_and_stale_sites(table, {_SITE_A, _SITE_B})
    assert unresolved == [_SITE_B] and stale == []
    unresolved, stale = unresolved_and_stale_sites({**table, _SITE_B: _entry(_BETA)}, {_SITE_A})
    assert unresolved == [] and stale == [_SITE_B]


def test_a_table_that_matches_the_walk_is_not_a_finding() -> None:
    assert unresolved_and_stale_sites({_SITE_A: _entry(_ALPHA)}, {_SITE_A}) == ([], [])


# --- unread_declared_manifests ---------------------------------------------


def test_a_declared_manifest_no_walk_reads_is_a_finding() -> None:
    assert unread_declared_manifests({_SITE_A: _entry(_ALPHA)}, {_BETA}) == {_ALPHA}


def test_a_declared_manifest_the_walk_reads_is_not_a_finding() -> None:
    assert unread_declared_manifests({_SITE_A: _entry(_ALPHA)}, {_ALPHA, _BETA}) == set()
    # The host-wide sentinel is not a path and must never be looked for on disk.
    assert unread_declared_manifests({_SITE_A: _entry(resolution.EVERY_MANIFEST)}, set()) == set()


# --- undeclared_installs ---------------------------------------------------


def test_a_manifest_installed_but_not_declared_is_a_finding() -> None:
    found = undeclared_installs({_SITE_A: _entry(_ALPHA)}, {_VENV: frozenset({_BETA})}, _verbatim)
    assert len(found) == 1 and _BETA in found[0]


def test_an_install_the_entry_names_is_not_a_finding() -> None:
    table = {_SITE_A: _entry(_ALPHA)}
    assert undeclared_installs(table, {_VENV: frozenset({_ALPHA})}, _verbatim) == []
    # A host-wide entry is bound to every manifest, so nothing can be undeclared.
    every = {_SITE_A: _entry(resolution.EVERY_MANIFEST)}
    assert undeclared_installs(every, {_VENV: frozenset({_BETA})}, _verbatim) == []


# --- dropped_declarations --------------------------------------------------


def test_a_binding_whose_install_task_vanished_is_a_finding() -> None:
    """The regression the `if not derived: continue` skip used to swallow.

    A site that stops carrying `requirements:` derives nothing, which is
    indistinguishable from a site the walk never could see. The old skip read
    both as "cannot check" and passed; this asserts the declared manifest is now
    reported instead.
    """
    found = dropped_declarations({_SITE_A: _entry(_ALPHA)}, {}, {}, _verbatim)
    assert len(found) == 1 and _ALPHA in found[0]


def test_a_declared_manifest_replaced_by_another_is_a_finding() -> None:
    found = dropped_declarations({_SITE_A: _entry(_ALPHA)}, {_VENV: frozenset({_BETA})}, {}, _verbatim)
    assert len(found) == 1 and _ALPHA in found[0]


def test_an_installed_or_excused_declaration_is_not_a_finding() -> None:
    table = {_SITE_A: _entry(_ALPHA)}
    assert dropped_declarations(table, {_VENV: frozenset({_ALPHA})}, {}, _verbatim) == []
    excused = {(_SITE_A[0], _ALPHA): "delivered by an image build, not a pip task"}
    assert dropped_declarations(table, {}, excused, _verbatim) == []
    assert dropped_declarations({_SITE_A: _entry(resolution.EVERY_MANIFEST)}, {}, {}, _verbatim) == []


# --- stale_exceptions ------------------------------------------------------


def test_each_way_an_exception_stops_describing_the_tree_is_a_finding() -> None:
    table = {_SITE_A: _entry(_ALPHA)}
    gone = stale_exceptions(table, {}, {(_SITE_B[0], _BETA): "why"}, _verbatim)
    assert len(gone) == 1 and "no longer a declared site" in gone[0]
    undeclared = stale_exceptions(table, {}, {(_SITE_A[0], _BETA): "why"}, _verbatim)
    assert len(undeclared) == 1 and "no longer declares" in undeclared[0]
    derivable = stale_exceptions(table, {_VENV: frozenset({_ALPHA})}, {(_SITE_A[0], _ALPHA): "why"}, _verbatim)
    assert len(derivable) == 1 and "now derivably installs" in derivable[0]


def test_an_exception_that_still_describes_the_tree_is_not_a_finding() -> None:
    table = {_SITE_A: _entry(_ALPHA)}
    assert stale_exceptions(table, {}, {(_SITE_A[0], _ALPHA): "image-delivered"}, _verbatim) == []


# --- multi_source_drift ----------------------------------------------------


_BOTH = frozenset({resolution.MANIFEST_SOURCE, resolution.INLINE_SOURCE})
_MANIFEST = frozenset({resolution.MANIFEST_SOURCE})


def test_a_new_two_shape_venv_and_a_record_whose_venv_was_fixed_are_both_findings() -> None:
    unrecorded, stale = multi_source_drift({_VENV: _BOTH}, {})
    assert unrecorded == [_VENV] and stale == []
    unrecorded, stale = multi_source_drift({_VENV: _MANIFEST}, {_VENV: "recorded"})
    assert unrecorded == [] and stale == [_VENV]


def test_a_recorded_two_shape_venv_is_not_a_finding() -> None:
    assert multi_source_drift({_VENV: _BOTH}, {_VENV: "recorded"}) == ([], [])
    assert multi_source_drift({_VENV: _MANIFEST}, {}) == ([], [])


# --- one_manifest_findings -------------------------------------------------

_FILE_ONE = "roles/alpha/tasks/main.yml"
_FILE_TWO = "playbooks/alpha.yml"
_CLEAN = dict(
    shapes={_VENV: _MANIFEST},
    bindings={_VENV: frozenset({_ALPHA})},
    per_file={_FILE_ONE: frozenset({_ALPHA}), _FILE_TWO: frozenset({_ALPHA})},
    filling=frozenset({_FILE_ONE, _FILE_TWO}),
    expected=_ALPHA,
)


def _findings(**overrides) -> list[str]:
    return one_manifest_findings(_VENV, **{**_CLEAN, **overrides})


def test_two_paths_reading_one_manifest_is_not_a_finding() -> None:
    assert _findings() == []


def test_a_venv_no_pip_task_fills_is_a_finding() -> None:
    assert len(_findings(shapes={})) == 1


def test_an_inline_shape_or_a_second_bound_manifest_is_a_finding() -> None:
    assert _findings(shapes={_VENV: _BOTH})
    assert _findings(bindings={_VENV: frozenset({_ALPHA, _BETA})})


def test_a_single_path_cannot_pin_a_two_path_collision() -> None:
    assert _findings(per_file={_FILE_ONE: frozenset({_ALPHA})}, filling=frozenset({_FILE_ONE}))


def test_a_second_file_reading_a_different_manifest_is_a_finding() -> None:
    """The union hides this: `bindings` still says {ALPHA} while a path reads BETA."""
    found = _findings(per_file={_FILE_ONE: frozenset({_ALPHA}), _FILE_TWO: frozenset({_BETA})})
    assert len(found) == 1 and _FILE_TWO in found[0]


def test_a_path_whose_requirements_resolve_to_nothing_is_a_finding() -> None:
    """`_resolve_manifest` returning None drops out of the union without a trace."""
    unresolvable = _findings(per_file={_FILE_ONE: frozenset({_ALPHA}), _FILE_TWO: frozenset({resolution.UNRESOLVED})})
    assert len(unresolvable) == 1 and resolution.UNRESOLVED in unresolvable[0]
    absent = _findings(
        per_file={_FILE_ONE: frozenset({_ALPHA}), _FILE_TWO: frozenset({_ALPHA})},
        filling=frozenset({_FILE_ONE, _FILE_TWO, "playbooks/gamma.yml"}),
    )
    assert len(absent) == 1 and "gamma" in absent[0]
