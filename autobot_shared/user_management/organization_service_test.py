# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The shared OrganizationService is the single implementation (#12647).

`organization_service.py` was byte-identical across both backends — 545
duplicated lines — but could not be relocated the way `team_service.py` was
(#13164), because it queries the *concrete* `Organization` and `User` models
and those stay backend-local under the abstract-core decision.

The resolution was injection: the canonical service names neither class, and
each backend subclasses it to bind its own. These tests pin the three
properties that makes safe:

1. the canonical service never reaches for a concrete model itself,
2. a subclass that forgets to bind fails loudly at construction rather than
   deep inside a query,
3. the public API is exactly what the pre-refactor forked class exposed.
"""

import ast
import pathlib

import pytest

from autobot_shared.user_management.organization_service import (
    DuplicateOrganizationError,
    OrganizationLimitError,
    OrganizationNotFoundError,
    OrganizationService,
    OrganizationServiceError,
)

# parents: [0] user_management, [1] autobot_shared, [2] repo root.
_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SUBCLASSES = {
    "backend": _ROOT / "autobot-backend/user_management/services/organization_service.py",
    "slm": _ROOT / "autobot-slm-backend/user_management/services/organization_service.py",
}
_SRC = pathlib.Path(__file__).with_name("organization_service.py")

# The surface the forked class exposed before the extraction, measured on
# origin/Dev_new_gui. Losing one of these would break a caller silently.
_PUBLIC_API = [
    "can_add_user",
    "create_organization",
    "deactivate_organization",
    "delete_organization",
    "get_organization",
    "get_organization_by_slug",
    "get_organization_stats",
    "get_team_count",
    "get_user_count",
    "list_organizations",
    "update_organization",
]

_ERRORS = (
    OrganizationServiceError,
    OrganizationNotFoundError,
    DuplicateOrganizationError,
    OrganizationLimitError,
)


def test_canonical_service_names_no_concrete_model():
    """The whole point: `autobot_shared` must not reach into a backend.

    A bare `Organization` or `User` in a code position would mean an import
    from a backend-local package — the inverted dependency this design exists
    to avoid.
    """
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))

    bare = sorted(
        {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id in {"Organization", "User"}}
    )

    assert bare == [], f"canonical service references concrete models: {bare}"


def test_canonical_service_does_not_import_a_backend_package():
    """`from user_management...` here would be the inverted dependency."""
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))

    offenders = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("user_management")
    ]

    assert offenders == [], f"canonical service imports backend-local modules: {offenders}"


def test_unbound_subclass_fails_at_construction():
    """Failing here beats an AttributeError deep inside a query."""

    class Unbound(OrganizationService):
        pass

    with pytest.raises(TypeError) as excinfo:
        Unbound(session=object())

    assert "organization_model" in str(excinfo.value)


def test_public_api_matches_the_pre_refactor_surface():
    """No method lost when 545 forked lines became one implementation."""
    public = sorted(
        name
        for name in dir(OrganizationService)
        if not name.startswith("_") and callable(getattr(OrganizationService, name, None))
    )

    for name in _PUBLIC_API:
        assert name in public, f"lost {name}"


def test_error_hierarchy_survived_the_move():
    """Callers catch OrganizationServiceError to cover all of them."""
    for error in _ERRORS[1:]:
        assert issubclass(error, OrganizationServiceError)


@pytest.mark.parametrize("backend", sorted(_SUBCLASSES))
def test_backend_subclass_exists(backend):
    assert _SUBCLASSES[backend].is_file(), f"{backend} subclass missing"


@pytest.mark.parametrize("backend", sorted(_SUBCLASSES))
def test_backend_subclass_binds_both_models(backend):
    """Read structurally — importing needs a full backend on sys.path."""
    tree = ast.parse(_SUBCLASSES[backend].read_text(encoding="utf-8"))

    bound = {
        target.id: node.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    assert bound.get("organization_model") == "Organization"
    assert bound.get("user_model") == "User"


@pytest.mark.parametrize("backend", sorted(_SUBCLASSES))
def test_backend_subclass_reexports_the_error_classes(backend):
    """Importers catch these from the backend path — keep that working."""
    source = _SUBCLASSES[backend].read_text(encoding="utf-8")

    for error in _ERRORS:
        assert error.__name__ in source, f"{backend} drops {error.__name__}"
