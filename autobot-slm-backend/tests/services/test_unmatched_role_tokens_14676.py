"""A role that maps to no ansible group must be reported, not silently inert (#14676).

Loads the module from disk: conftest stubs ``services.*`` as MagicMock, and a
MagicMock satisfies every truthiness check these assertions make, so a plain
import would pass against a mock that implements nothing.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def inventory_builder():
    path = BACKEND / "services" / "inventory_builder.py"
    assert path.is_file(), f"module under test is missing: {path}"
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    spec = importlib.util.spec_from_file_location("inventory_builder_14676", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    from unittest.mock import MagicMock

    assert not isinstance(module.unmatched_role_tokens, MagicMock)
    return module


def test_unknown_role_is_reported(inventory_builder):
    """The defect: a custom role was accepted and then contributed nothing."""
    assert inventory_builder.unmatched_role_tokens(["definitely-not-a-real-role"]) == {"definitely-not-a-real-role"}


def test_unknown_role_really_reaches_no_group(inventory_builder):
    """Why it matters -- the token resolves to no group at all."""
    assert inventory_builder._role_tokens_to_groups(["definitely-not-a-real-role"]) == set()


def test_known_role_is_not_flagged(inventory_builder):
    assert inventory_builder.unmatched_role_tokens(["backend"]) == set()
    assert inventory_builder._role_tokens_to_groups(["backend"])


def test_legacy_map_only_role_is_not_flagged(inventory_builder):
    """`vnc` reaches its group solely via ROLE_ANSIBLE_GROUPS (#14638).

    Checking only `_ROLE_TO_GROUPS` would cry wolf on it, so the report must
    consult both maps.
    """
    assert inventory_builder.unmatched_role_tokens(["vnc"]) == set()


def test_blank_and_case_variant_tokens_are_not_flagged(inventory_builder):
    assert inventory_builder.unmatched_role_tokens(["", "  "]) == set()
    assert inventory_builder.unmatched_role_tokens(["BACKEND", " backend "]) == set()


def test_mixed_batch_reports_only_the_unmatched(inventory_builder):
    assert inventory_builder.unmatched_role_tokens(["backend", "nope-not-a-role", "vnc"]) == {"nope-not-a-role"}
