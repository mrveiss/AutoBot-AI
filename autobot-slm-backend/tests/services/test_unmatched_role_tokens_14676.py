"""A role that maps to no ansible group must be reported, not silently inert (#14676).

Loads the module from disk: conftest stubs ``services.*`` as MagicMock, and a
MagicMock satisfies every truthiness check these assertions make, so a plain
import would pass against a mock that implements nothing.
"""

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def inventory_builder():
    """Load the module under test from disk, over a REAL registry.

    conftest stubs `services.*` as MagicMock. A Mock imports cleanly, iterates
    as empty and answers `.get()` with another Mock -- which is truthy -- so
    every role would look matched and the report would silently return nothing.
    Installing a genuine registry module makes these assertions exercise the
    logic instead of a mock's blanket answers.

    The stand-in mirrors the real registry's SHAPE; that it also mirrors its
    CONTENT is pinned separately by
    `test_the_stand_in_matches_the_real_registry`, so this cannot drift into
    testing a fiction.
    """
    registry = types.ModuleType("services.role_registry")
    registry.ROLE_ANSIBLE_GROUPS = {"vnc": "backend"}
    registry.DEFAULT_ROLES = (
        {"name": "docker", "ansible_playbook": "deploy-hybrid-docker.yml"},
        {"name": "redis", "ansible_playbook": "setup-redis-stack.yml"},
        {"name": "slm-frontend", "ansible_playbook": "playbooks/deploy-slm-manager.yml"},
    )
    services_pkg = sys.modules.get("services") or types.ModuleType("services")
    if not hasattr(services_pkg, "__path__"):
        services_pkg.__path__ = []  # type: ignore[attr-defined]

    saved = {k: sys.modules.get(k) for k in ("services", "services.role_registry")}
    sys.modules["services"] = services_pkg
    sys.modules["services.role_registry"] = registry

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
    # The registry really is readable here -- otherwise every assertion below
    # would pass vacuously against the "cannot judge" empty set.
    assert module._registry_deploy_paths() is not None, "registry stand-in did not take effect"

    yield module

    for k, v in saved.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


def test_the_stand_in_matches_the_real_registry() -> None:
    """Pin the two facts the stand-in encodes, against the real source.

    Read as text, not imported: importing the real registry pulls config and
    writes key material into the tree. If someone gives `docker` a group or
    drops its playbook, this fails and the stand-in gets corrected rather than
    quietly testing something that is no longer true.
    """
    registry_src = (BACKEND / "services" / "role_registry.py").read_text(encoding="utf-8")
    assert '"name": "docker"' in registry_src
    assert '"ansible_playbook": "deploy-hybrid-docker.yml"' in registry_src
    assert '"vnc"' in registry_src

    # Parsed, not string-sliced: splitting on the first "}" covers only the
    # first frozenset in the literal, so a substring check there would pass
    # whatever the rest of the map said.
    builder_src = (BACKEND / "services" / "inventory_builder.py").read_text(encoding="utf-8")
    tree = ast.parse(builder_src)
    keys: list[str] = []
    for node in tree.body:
        targets = getattr(node, "targets", []) or ([node.target] if hasattr(node, "target") else [])
        if any(getattr(t, "id", None) == "_ROLE_TO_GROUPS" for t in targets):
            assert isinstance(node.value, ast.Dict), "_ROLE_TO_GROUPS is no longer a dict literal"
            keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
    assert keys, "could not read _ROLE_TO_GROUPS — this guard would pass vacuously"
    assert "docker" not in keys, "docker gained a group mapping — the stand-in and the docker test need revisiting"


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
