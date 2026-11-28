# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The inventory a per-node role provisioning run hands ``provision-fleet-roles.yml`` (#2959, #22262).

The run targets ONE host, ``provision_target``. Roles still delegate tasks to the SLM manager
(``delegate_to: "{{ slm_manager_inventory_host }}"``, e.g. slm_agent reading the SLM's own
internal API key, #14350). That fact resolves from the ``slm_server`` group (group_vars/all.yml,
#9956), so an inventory without the manager host resolved it to a name no inventory defines, and
Ansible marked the delegated task UNREACHABLE: the run aborted before the vnc role created its
account, and every later fleet update failed the vnc gate (#22262).

The manager host is therefore copied from the fleet update's own inventory
(``build_registry_inventory``), with the exact vars that inventory gives it, never redefined here.
The run is limited to ``PROVISION_TARGET``, so the manager is only a delegation target, never
provisioned itself.
"""

from typing import Any

import yaml
from sqlalchemy import select

from autobot_shared.network_utils import is_local_ip
from autobot_shared.ssot_config import config
from models.database import Node
from services.inventory_builder import build_registry_inventory

#: The inventory host name of the node being provisioned; also the run's ``--limit``.
PROVISION_TARGET = "provision_target"
#: The group ``slm_manager_inventory_host`` resolves the SLM manager from (group_vars/all.yml).
SLM_MANAGER_GROUP = "slm_server"


def slm_manager_hosts(nodes: list[Any], local_ip_check: Any) -> dict[str, dict]:
    """The fleet update inventory's SLM manager host(s), each with every var that inventory gives it.

    The update inventory sets connection vars both on the host and in ``all.vars``; both are merged
    onto the host here (host wins, as in Ansible), so the provision inventory's other host is untouched.
    """
    update_inv = build_registry_inventory(nodes, local_ip_check)["all"]
    names = update_inv["children"].get(SLM_MANAGER_GROUP, {}).get("hosts", {})
    return {name: {**update_inv["vars"], **update_inv["hosts"][name]} for name in names}


def _target_hostvars(node_id: str, node: Any, target_roles: list[str], deps: list[str]) -> dict:
    """Host vars of ``provision_target``: the node's connection and the roles to provision."""
    hostvars: dict[str, Any] = {
        "node_hostname": node.hostname,  # the credential name uses it (#22211)
        "slm_node_id": node_id,  # the vnc role registers its credential only when this is set (#22211)
        "ansible_host": node.ip_address,
        "ansible_user": node.ssh_user or "autobot",
        "ansible_ssh_private_key_file": config.path.ssh_key_path,  # the update inventory's key (#12429)
        "ansible_python_interpreter": "/usr/bin/python3",
        "node_roles": list(target_roles),
    }
    if deps:
        hostvars["node_dependencies"] = deps
    return hostvars


def build_provision_inventory(
    node_id: str, node: Any, target_roles: list[str], nodes: list[Any], local_ip_check: Any
) -> str:
    """YAML inventory: ``provision_target`` plus the SLM manager host(s) in their group.

    Args:
        node_id: the target's node id.
        node: the target Node row.
        target_roles: roles to provision on it.
        nodes: every Node row, as the fleet update inventory is built from.
        local_ip_check: callable(ip) -> bool; ``is_local_ip`` in production.
    """
    from services.role_registry import ROLE_DEPENDENCIES  # local, as at its previous call site

    deps = sorted({d for r in target_roles for d in ROLE_DEPENDENCIES.get(r, [])})
    managers = slm_manager_hosts(nodes, local_ip_check)
    inventory = {
        "all": {
            "hosts": {PROVISION_TARGET: _target_hostvars(node_id, node, target_roles, deps), **managers},
            "children": {SLM_MANAGER_GROUP: {"hosts": {name: None for name in managers}}},
        }
    }
    return yaml.safe_dump(inventory, sort_keys=False, default_flow_style=False)


async def provision_inventory_for(db: Any, node_id: str, node: Any, target_roles: list[str]) -> str:
    """:func:`build_provision_inventory` over the node registry, as the fleet update reads it."""
    nodes = list((await db.execute(select(Node))).scalars().all())
    return build_provision_inventory(node_id, node, target_roles, nodes, is_local_ip)
