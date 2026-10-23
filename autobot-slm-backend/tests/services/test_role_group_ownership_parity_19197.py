# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19197: one role->group mapping for both inventory paths (wizard and inventory builder).

Split out of ``test_wizard_inventory_parity_14286.py`` to keep that file under the 600-line
ceiling. It reuses that module's real-loaded ``inventory_builder``, ``role_registry`` and
``setup_wizard`` (one loader, one set of stubs) by executing it under a private name.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

_spec = importlib.util.spec_from_file_location(
    "_wizard_parity_14286_for_19197", Path(__file__).with_name("test_wizard_inventory_parity_14286.py")
)
_parity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_parity)

_ib = _parity._ib
_ansible_groups_for_nodes = _parity._ansible_groups_for_nodes
ROLE_ANSIBLE_GROUPS = _parity.ROLE_ANSIBLE_GROUPS


def _wizard_groups(declared: list, detected: list) -> set:
    rows = [SimpleNamespace(node_id="n", role_name=r, assignment_type="manual") for r in declared] + [
        SimpleNamespace(node_id="n", role_name=r, assignment_type="auto") for r in detected if r not in declared
    ]
    db_nodes = [SimpleNamespace(node_id="n", roles=list(declared), detected_roles=list(detected))]
    out = _ansible_groups_for_nodes(rows, {"n": "n"}, db_nodes)
    return {g for g, members in out.items() if "n" in members}


def test_vnc_node_with_stale_postgres_gets_no_redis_on_either_path():
    declared, detected = ["vnc", "slm-agent"], ["postgres", "slm-database"]
    node = SimpleNamespace(node_id="n", roles=declared, detected_roles=detected)
    builder = _ib._strip_undeclared_privileged_groups(
        node, _ib.groups_for_role_tokens(*_ib.declared_and_detected(node))
    )
    wizard = _wizard_groups(declared, detected)
    assert not builder & {"redis", "database"}
    assert not wizard & {"redis", "database"}


def test_real_redis_host_gets_redis_on_either_path():
    declared, detected = ["slm-agent"], ["redis"]
    node = SimpleNamespace(node_id="n", roles=declared, detected_roles=detected)
    builder = _ib._strip_undeclared_privileged_groups(
        node, _ib.groups_for_role_tokens(*_ib.declared_and_detected(node))
    )
    assert {"redis", "database"} <= builder
    assert {"redis", "database"} <= _wizard_groups(declared, detected)


def test_declared_slm_database_agrees_across_paths():
    declared = ["slm-backend", "slm-database"]
    node = SimpleNamespace(node_id="n", roles=declared, detected_roles=["postgres"])
    builder = _ib._strip_undeclared_privileged_groups(
        node, _ib.groups_for_role_tokens(*_ib.declared_and_detected(node))
    )
    wizard = _wizard_groups(declared, ["postgres"])
    assert {"redis", "database"} <= builder and {"redis", "database"} <= wizard
    assert builder <= wizard


def test_drifted_rows_and_roles_give_equal_groups_on_both_paths():
    """Node.roles lacks slm-database but a MANUAL NodeRole row names it: declared means Node.roles on both
    paths, so the row is detected and the owner gate withholds redis/database from the wizard and builder alike.
    The wizard also unions the legacy ROLE_ANSIBLE_GROUPS vocabulary, so both sides are compared with the
    declared roles' legacy groups removed: everything else must be EQUAL."""
    declared, detected = ["vnc", "slm-agent"], ["slm-database"]
    node = SimpleNamespace(node_id="n", roles=declared, detected_roles=detected)
    rows = [
        SimpleNamespace(node_id="n", role_name="vnc", assignment_type="manual"),
        SimpleNamespace(node_id="n", role_name="slm-agent", assignment_type="manual"),
        SimpleNamespace(node_id="n", role_name="slm-database", assignment_type="manual"),
    ]
    out = _ansible_groups_for_nodes(rows, {"n": "n"}, [node])
    wizard = {g for g, members in out.items() if "n" in members}
    builder = _ib._strip_undeclared_privileged_groups(
        node, _ib.groups_for_role_tokens(*_ib.declared_and_detected(node))
    )
    legacy = {ROLE_ANSIBLE_GROUPS[t] for t in declared if t in ROLE_ANSIBLE_GROUPS}
    assert not wizard & {"redis", "database"}
    assert wizard - legacy == builder - legacy
