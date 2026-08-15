# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The wizard inventory path must reach the canonical groups and vars (#14286).

Two ansible execution stacks existed. The canonical one
(``services/playbook_executor.py``) builds its inventory from
``services/inventory_builder.py`` and symlinks ``inventory/group_vars`` beside
it. The second (``api/setup_wizard.py::_generate_dynamic_inventory``, used by
``/infrastructure/execute``) wrote a bare inventory with neither, and emitted a
different group vocabulary — so plays gated on ``aiml`` / ``database`` matched
zero hosts and reported success having done nothing, and
``chromadb_service_owner`` derived from role defaults instead of from
``role_redis_active``.

Loading, learned across three CI rounds on this PR
--------------------------------------------------

Both conftests in play stub ``services.*`` names as MagicMocks, and a MagicMock
group set iterates as EMPTY — which is precisely the pre-fix behaviour, so a
test that accidentally gets one passes while proving nothing.

So every module under test is real-loaded from its path under a private name,
following ``test_dynamic_inventory_group_vars_11781.py`` in this directory. Two
rules this module keeps, each of which it broke once:

* Never leave a ``sys.modules`` entry different from how it was found. An
  earlier version popped ``services.inventory_builder`` on the way out, and
  ``services/inventory_builder_test.py`` — a file this PR does not touch — then
  resolved that name through the leftover MagicMock parent and failed.
* Never depend on a stub being absent. The names below are saved and restored
  exactly, whether they were real, stubbed, or missing.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE_DIR = _BACKEND_ROOT / "ansible"


def _real_module(name: str, path: Path) -> ModuleType:
    """Execute *path* as a module under *name* without touching sys.modules."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # a module must be findable while it executes
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _load():
    """Real-load inventory_builder, playbook_executor, role_registry and the wizard.

    ``setup_wizard`` imports ``groups_for_role_tokens`` at module level, so the
    real ``inventory_builder`` has to occupy ``services.inventory_builder``
    while the wizard executes — and only while.
    """
    touched = (
        "api",
        "api.websocket",
        "config",
        "services",
        "services.ansible_secrets",
        "services.ansible_utils",
        "services.auth",
        "services.database",
        "services.inventory_builder",
        "services.playbook_executor",
        "services.role_registry",
    )
    saved = {name: sys.modules.get(name) for name in touched}
    try:
        for name in touched:
            sys.modules[name] = MagicMock()
        placeholder = sys.modules["config"]
        placeholder.settings = SimpleNamespace()

        inventory_builder = _real_module("_ib_14286", _BACKEND_ROOT / "services" / "inventory_builder.py")
        role_registry = _real_module("_rr_14286", _BACKEND_ROOT / "services" / "role_registry.py")
        executor = _real_module("_pe_14286", _BACKEND_ROOT / "services" / "playbook_executor.py")

        sys.modules["services.inventory_builder"] = inventory_builder
        sys.modules["services.role_registry"] = role_registry
        sys.modules["services.playbook_executor"] = executor
        wizard = _real_module("_wizard_14286", _BACKEND_ROOT / "api" / "setup_wizard.py")
        return inventory_builder, role_registry, executor, wizard
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


_ib, _rr, _pe, _wiz = _load()

ROLE_ANSIBLE_GROUPS = _rr.ROLE_ANSIBLE_GROUPS
PlaybookExecutor = _pe.PlaybookExecutor
link_group_vars = _pe.link_group_vars
_build_inventory_children = _wiz._build_inventory_children


def _children_for(roles_by_node: dict[str, list[str]]) -> dict[str, dict]:
    """Run the wizard's real children builder over a fleet."""
    hosts = {n: {} for n in roles_by_node}
    node_roles = [
        SimpleNamespace(node_id=node, role_name=role) for node, roles in roles_by_node.items() for role in roles
    ]
    children, _groups = _build_inventory_children(hosts, node_roles, {n: n for n in roles_by_node})
    return children


def _hosts_in(children: dict, group: str) -> set[str]:
    return set(children.get(group, {}).get("hosts", {}) or {})


def test_the_modules_under_test_are_real_not_mocks():
    """Every assertion below is worthless if this one does not hold.

    A MagicMock group set iterates as empty, which is indistinguishable from
    the bug being present — so the harness is checked before the behaviour.
    """
    assert not isinstance(_ib, MagicMock)
    assert isinstance(ROLE_ANSIBLE_GROUPS, dict) and ROLE_ANSIBLE_GROUPS
    assert isinstance(PlaybookExecutor, type)
    assert callable(link_group_vars)
    assert _ib.groups_for_role_tokens(["redis"]) >= {"redis", "database"}


# --------------------------------------------------------------------------
# 1. The alias groups the canonical builder emits now reach this path too.
# --------------------------------------------------------------------------


def test_the_wizard_children_carry_the_canonical_alias_groups():
    children = _children_for({"ai-node": ["ai-stack"], "db-node": ["redis"], "api-node": ["backend"]})

    # ai-stack: the canonical builder puts it in aiml/ai as well as ai_stack.
    assert _hosts_in(children, "aiml") == {"ai-node"}
    assert _hosts_in(children, "ai") == {"ai-node"}
    # redis: `database` and `redis`, the names update-all-nodes.yml gates on.
    assert _hosts_in(children, "database") == {"db-node"}
    assert _hosts_in(children, "redis") == {"db-node"}
    # backend: `main`.
    assert _hosts_in(children, "main") == {"api-node"}
    # universal groups apply to every non-SLM node.
    for universal in ("autobot", "autobot_cluster", "infrastructure", "production_vms"):
        assert _hosts_in(children, universal) == {"ai-node", "db-node", "api-node"}, universal


# --------------------------------------------------------------------------
# 2. The union must not cost anything that already worked.
# --------------------------------------------------------------------------


def test_no_group_this_path_already_emitted_disappears():
    """Every ROLE_ANSIBLE_GROUPS value still resolves after the change.

    The two maps are not supersets of each other — `databases`,
    `browser_automation` and tts-worker's `npu_worker` exist only in
    ROLE_ANSIBLE_GROUPS, and playbooks gate on them. Swapping rather than
    unioning would trade one silent no-op for another.
    """
    for role, legacy_group in ROLE_ANSIBLE_GROUPS.items():
        children = _children_for({"n": [role]})
        assert _hosts_in(children, legacy_group) == {"n"}, f"{role} lost its {legacy_group} membership"


# --------------------------------------------------------------------------
# 3. The invariant, not the instance: no play may gate on a group this path
#    cannot produce for a fleet that carries every role.
# --------------------------------------------------------------------------

# Group names in `hosts:` that are not inventory groups: static-inventory host
# names, a literal host, and the extra-var-supplied `target`. Each is resolved
# by something other than role membership, so this rule has nothing to say
# about them.
_NOT_ROLE_GROUPS = frozenset(
    {
        "all",
        "localhost",
        "target",
        "autobot-host",
        "autobot-backend",
        "01-Backend",
        "02-Frontend",
        "03-AI-Stack",
        "04-Databases",
    }
)

# Hyphenated spellings that no inventory builder emits — either vocabulary.
# Pre-existing and out of scope here; they are a separate defect from the two
# vocabularies disagreeing, which is what this change fixes.
_KNOWN_UNREACHABLE = frozenset({"browser-automation", "npu-worker"})


def _gated_groups() -> set[str]:
    """Every group name a playbook's `hosts:` gates on."""
    found: set[str] = set()
    for path in _ANSIBLE_DIR.rglob("*.yml"):
        if "roles/" in str(path.relative_to(_ANSIBLE_DIR)):
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"\s*hosts:\s*([^#]+)", line)
            if not match:
                continue
            for token in re.split(r"[,:]", match.group(1)):
                token = token.strip().strip("\"'")
                if token and not token.startswith("{{"):
                    found.add(token)
    return found


def test_every_group_a_play_gates_on_is_reachable_through_this_path():
    gated = _gated_groups()
    assert gated, "found no `hosts:` lines — the scan is broken, not the inventory"

    every_role = sorted(ROLE_ANSIBLE_GROUPS)
    children = _children_for({"fleet-node": every_role, "slm-node": ["slm-backend"]})

    unreachable = {
        group
        for group in gated
        if group not in _NOT_ROLE_GROUPS and group not in _KNOWN_UNREACHABLE and not _hosts_in(children, group)
    }
    assert not unreachable, f"plays gate on groups this path cannot emit: {sorted(unreachable)}"


def test_the_known_unreachable_list_is_not_stale():
    """A name that stopped being gated on must leave the exemption list.

    An exemption naming something that no longer exists exempts nothing and
    hides the next real case behind an entry nobody rereads.
    """
    gated = _gated_groups()
    stale = _KNOWN_UNREACHABLE - gated
    assert not stale, f"no play gates on these any more — drop them: {sorted(stale)}"


# --------------------------------------------------------------------------
# 4. group_vars parity — the shared linker, and this path using it.
# --------------------------------------------------------------------------


def test_link_group_vars_creates_the_sibling(tmp_path):
    ansible_dir = tmp_path / "ansible"
    (ansible_dir / "inventory" / "group_vars").mkdir(parents=True)
    (ansible_dir / "inventory" / "group_vars" / "all.yml").write_text("k: v\n", encoding="utf-8")
    inventory = tmp_path / "run" / "inv.yml"
    inventory.parent.mkdir()
    inventory.write_text("all: {}\n", encoding="utf-8")

    link_group_vars(inventory, ansible_dir)

    linked = inventory.parent / "group_vars"
    assert linked.is_symlink()
    assert (linked / "all.yml").read_text(encoding="utf-8") == "k: v\n"


def test_the_executor_method_still_links_after_the_extraction(tmp_path):
    """The method kept its behaviour when its body moved to a function.

    Asserted by running it, not by reading it: a wrapper that forgot to call
    through would still contain the name.
    """
    ansible_dir = tmp_path / "ansible"
    (ansible_dir / "inventory" / "group_vars").mkdir(parents=True)
    inventory = tmp_path / "run" / "inv.yml"
    inventory.parent.mkdir()
    inventory.write_text("all: {}\n", encoding="utf-8")

    executor = PlaybookExecutor.__new__(PlaybookExecutor)  # skip __init__ (env probing)
    executor.ansible_dir = ansible_dir
    executor._link_group_vars(inventory)

    assert (inventory.parent / "group_vars").is_symlink()


def _wizard_generator_ast() -> ast.AST:
    source = (_BACKEND_ROOT / "api" / "setup_wizard.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_generate_dynamic_inventory":
            return node
    raise AssertionError("_generate_dynamic_inventory not found")


def test_the_wizard_inventory_is_written_where_a_link_can_live():
    """mkstemp must be given a dir=.

    Bare ``tempfile.mkstemp()`` lands in /tmp itself, and the group_vars
    symlink would then be created in a world-writable directory shared with
    every other user on the box.
    """
    calls = [
        node
        for node in ast.walk(_wizard_generator_ast())
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "mkstemp"
    ]
    assert calls, "no mkstemp call found — this test is pinned to the wrong thing"
    for call in calls:
        assert any(kw.arg == "dir" for kw in call.keywords), "mkstemp without dir= writes into bare /tmp"


def test_the_wizard_path_links_group_vars():
    called = {
        node.func.id
        for node in ast.walk(_wizard_generator_ast())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "link_group_vars" in called, "the wizard inventory still has no group_vars sibling"
