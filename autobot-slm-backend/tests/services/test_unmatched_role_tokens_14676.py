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

    Checking only `_ROLE_TO_GROUPS` would cry wolf on it.
    """
    assert inventory_builder.unmatched_role_tokens(["vnc"]) == set()


def test_role_with_its_own_playbook_is_not_flagged(inventory_builder):
    """`docker` deploys via deploy-hybrid-docker.yml and joins NO group.

    It is deliberately absent from both group maps, so a report that knows only
    about groups would call a working role dead -- the exact false alarm this
    report exists to avoid.
    """
    assert "docker" in inventory_builder._registry_deploy_paths()[1]
    assert inventory_builder.unmatched_role_tokens(["docker"]) == set()


def test_unreadable_registry_reports_nothing_rather_than_everything(inventory_builder, monkeypatch):
    """Being unable to check must not look like having found a problem.

    If an unreadable registry degraded to empty maps, every role outside
    `_ROLE_TO_GROUPS` -- `vnc` and `docker` included -- would be reported as
    deploying nothing.
    """
    monkeypatch.setattr(inventory_builder, "_registry_deploy_paths", lambda: None)
    for token in ("docker", "vnc", "backend", "definitely-not-a-real-role"):
        assert inventory_builder.unmatched_role_tokens([token]) == set(), token


def test_blank_and_case_variant_tokens_are_not_flagged(inventory_builder):
    assert inventory_builder.unmatched_role_tokens(["", "  "]) == set()
    assert inventory_builder.unmatched_role_tokens(["BACKEND", " backend "]) == set()


def test_mixed_batch_reports_only_the_unmatched(inventory_builder):
    assert inventory_builder.unmatched_role_tokens(["backend", "nope-not-a-role", "vnc"]) == {"nope-not-a-role"}
