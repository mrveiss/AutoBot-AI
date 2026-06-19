# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Dynamic Ansible inventory builder from DB node registry.

Fixes #10109: static slm-nodes.yml uses display names as host names which do
not match the node_id passed as --limit, so plays target zero hosts.  The
generated inventory uses node_id as the host name so --limit <node_id> always
resolves.

Fixes #10095: co-located self-node deploy SSHes to its own IP (refused).
Any node whose ip_address is a local/loopback address receives
``ansible_connection: local`` so Ansible never opens an SSH connection.

The generated inventory reproduces every global all.vars from slm-nodes.yml
and emits ALL group aliases so every ``hosts:`` / ``groups[...]`` reference
in every playbook under autobot-slm-backend/ansible/ resolves correctly.

GROUP CONTRACT
--------------
Exhaustive union of group names referenced by hosts:/groups[] across all
playbooks (run:
  grep -rhoE "hosts: [a-zA-Z0-9_:!.]+|groups\\[['\\"]+[a-z_]+['\\"]+\\]" \\
      autobot-slm-backend/ansible/playbooks/ autobot-slm-backend/ansible/*.yml
):

  slm_server, slm, slm_nodes        — SLM-manager node
  backend, main                      — backend/API node
  frontend                           — frontend node
  npu, npu_worker, npu_workers       — NPU inference worker
  ai_stack, aiml, ai                 — AI / LLM / ChromaDB stack
  database, redis                    — database / Redis node
  browser, browser_worker            — browser automation node
  infrastructure                     — all non-SLM nodes
  autobot, autobot_cluster           — all nodes
  monitoring_vm                      — optional; nodes with 'monitoring' role
  llm_nodes                          — LLM CPU/GPU inference nodes
  production_vms                     — alias for infrastructure

Groups parameterised at runtime (``target``, ``autobot-backend``,
``autobot-host``, ``{{ node_id }}``) need NOT be in the static inventory —
they are resolved via --limit or passed as extra-vars.
"""

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ROLE → GROUP MAPPING
# ---------------------------------------------------------------------------
# DB role tokens (Node.roles / Node.detected_roles union) and the ansible
# group names they map to.  Matching rules:
#   1. Exact key match (e.g. "redis" → redis + database)
#   2. Prefix key match for keys ending with "-" (e.g. "slm-" catches
#      "slm-backend", "slm-frontend", "slm-agent", etc.)
#   3. All matching entries accumulate (no early exit).
#
# Real role tokens seen in production:
#   slm-backend, slm-frontend, slm-database, slm-monitoring, slm-agent
#   autobot-llm-cpu, autobot-llm-gpu
#   autobot_shared
#   browser-service
#   tts-worker, npu-worker
#   ai-stack, chromadb
#   redis, frontend, backend, celery, docker, scheduler, postgres
#   monitoring

_ROLE_TO_GROUPS: dict[str, frozenset] = {
    # SLM manager / slm-agent / any slm-* role
    "slm-": frozenset({"slm", "slm_server", "slm_nodes"}),
    "slm_agent": frozenset({"slm", "slm_server", "slm_nodes"}),
    # Backend / API server
    "backend": frozenset({"backend", "main"}),
    "celery": frozenset({"backend", "main"}),
    "scheduler": frozenset({"backend", "main"}),
    "autobot_shared": frozenset({"backend", "main"}),
    # Frontend
    "frontend": frozenset({"frontend"}),
    # NPU inference
    "npu-worker": frozenset({"npu", "npu_worker", "npu_workers"}),
    "npu_worker": frozenset({"npu", "npu_worker", "npu_workers"}),
    # AI / LLM / ChromaDB
    "ai-stack": frozenset({"ai_stack", "aiml", "ai", "llm_nodes"}),
    "chromadb": frozenset({"ai_stack", "aiml", "ai"}),
    "autobot-llm-": frozenset({"ai_stack", "aiml", "ai", "llm_nodes"}),
    "tts-worker": frozenset({"ai_stack", "aiml", "ai"}),
    # Database / Redis / Postgres
    "redis": frozenset({"redis", "database"}),
    "postgres": frozenset({"database"}),
    "slm-database": frozenset({"redis", "database"}),
    # Browser automation
    "browser-service": frozenset({"browser", "browser_worker"}),
    # Monitoring (optional; maps to monitoring_vm)
    "monitoring": frozenset({"monitoring_vm"}),
    "slm-monitoring": frozenset({"monitoring_vm"}),
}

# Groups that every non-SLM node belongs to
_UNIVERSAL_NON_SLM: frozenset = frozenset({"infrastructure", "autobot", "autobot_cluster", "production_vms"})

# Groups that every node (including SLM) belongs to
_UNIVERSAL_ALL: frozenset = frozenset({"autobot", "autobot_cluster"})

# Full required-group contract — see module docstring for provenance
REQUIRED_GROUPS: frozenset = frozenset(
    {
        "slm",
        "slm_server",
        "slm_nodes",
        "backend",
        "main",
        "frontend",
        "npu",
        "npu_worker",
        "npu_workers",
        "ai_stack",
        "aiml",
        "ai",
        "database",
        "redis",
        "browser",
        "browser_worker",
        "infrastructure",
        "autobot",
        "autobot_cluster",
        "monitoring_vm",
        "llm_nodes",
        "production_vms",
    }
)

# Global all.vars — reproduced verbatim from slm-nodes.yml
_ALL_VARS: dict[str, str] = {
    "ansible_user": "autobot",
    "ansible_ssh_private_key_file": "/etc/autobot/ssh/autobot_key",
    "ansible_python_interpreter": "/usr/bin/python3",
    "slm_host": (
        "{{ lookup('env', 'SLM_HOST') | default(lookup('pipe',"
        ' \'grep -oP "SLM_HOST=\\\\K.*" /etc/autobot/slm-secrets.env'
        " 2>/dev/null || echo 127.0.0.1'), true) }}"
    ),
    "network_subnet": (
        "{{ lookup('env', 'NETWORK_SUBNET') or"
        " lookup('pipe', 'grep -oP \"NETWORK_SUBNET=\\\\K.*\""
        " /etc/autobot/slm-secrets.env 2>/dev/null') or '0.0.0.0/0' }}"
    ),
    "network_gateway": (
        "{{ lookup('env', 'NETWORK_GATEWAY') or"
        " lookup('pipe', 'grep -oP \"NETWORK_GATEWAY=\\\\K.*\""
        " /etc/autobot/slm-secrets.env 2>/dev/null') or '0.0.0.0' }}"
    ),
}


def _role_tokens_to_groups(role_tokens: list[str]) -> set[str]:
    """Map a list of DB role token strings to the union of ansible group names.

    Matching is exact-string first; if no exact key matches, checks each
    mapping key as a prefix of the token (for keys ending with ``-``).
    All matching entries accumulate.

    Args:
        role_tokens: List of role/detected_role strings from the DB.

    Returns:
        Set of ansible group name strings.
    """
    groups: set[str] = set()
    for token in role_tokens:
        token = token.strip().lower()
        if not token:
            continue
        # Exact key match
        if token in _ROLE_TO_GROUPS:
            groups |= _ROLE_TO_GROUPS[token]
            continue
        # Prefix key match (handles "slm-" catching "slm-backend")
        for key, key_groups in _ROLE_TO_GROUPS.items():
            if key.endswith("-") and token.startswith(key):
                groups |= key_groups
            elif not key.endswith("-") and token == key:
                groups |= key_groups
    return groups


def _union_roles(node: Any) -> list[str]:
    """Return union of node.roles and node.detected_roles as a deduped list."""
    seen: set[str] = set()
    result: list[str] = []
    for r in list(node.roles or []) + list(node.detected_roles or []):
        if r not in seen:
            seen.add(r)
            result.append(r)
    return result


def _build_hostvars(node: Any, local_ip_check: Any) -> dict:
    """Return the host-variable dict for one Node record.

    Args:
        node: SQLAlchemy Node ORM instance (or duck-type compatible).
        local_ip_check: callable(ip: str) -> bool.  When True the host gets
            ``ansible_connection: local`` to avoid SSH to self (#10095).

    Returns:
        Dict of Ansible host variables for this node.
    """
    hostvars: dict[str, Any] = {
        "ansible_host": node.ip_address,
        "ansible_user": node.ssh_user or "autobot",
        "ansible_port": node.ssh_port or 22,
        "slm_node_id": node.node_id,
        # #9965: stamp the node's assigned role tokens so role_active_facts can
        # activate roles via node_roles, not group membership alone. Group-based
        # activation silently skips roles whose inventory group isn't the one
        # role_*_active checks (e.g. tts-worker -> npu_worker group, but
        # role_tts_worker_active checks node_roles only; browser-service ->
        # browser_automation group, but role_browser_active checks browser/
        # browser_worker) — so optional assigned roles never deploy.
        "node_roles": _union_roles(node),
    }
    if local_ip_check(node.ip_address):
        hostvars["ansible_connection"] = "local"
    return hostvars


def build_registry_inventory(nodes: list[Any], local_ip_check: Any) -> dict:
    """Build a full Ansible YAML inventory dict from the DB node list.

    The returned dict is shaped as::

        all:
          vars: {...}
          hosts:
            <node_id>: {ansible_host, ansible_user, ansible_port, slm_node_id, ...}
          children:
            <group>:
              hosts:
                <node_id>: {}

    so that ``yaml.dump(inv)`` produces a valid Ansible inventory.

    Every required group key is always present (possibly with no hosts) so
    that plays referencing groups that have no assigned nodes produce a
    "skipped all hosts" message rather than "Could not match host pattern".

    Args:
        nodes: List of Node ORM instances (or duck-type compatible objects).
        local_ip_check: callable(ip: str) -> bool.  Pass
            ``autobot_shared.network_utils.is_local_ip`` in production; pass
            a lambda in tests.

    Returns:
        Dict suitable for ``yaml.dump`` to produce an Ansible inventory file.
    """
    # Pre-populate every required group so validate_inventory never complains
    # about a missing key even when no node carries that role.
    groups: dict[str, dict] = {g: {"hosts": {}} for g in REQUIRED_GROUPS}

    host_section: dict[str, dict] = {}

    for node in nodes:
        host_name: str = node.node_id  # host name IS the node_id (#10109)
        hostvars = _build_hostvars(node, local_ip_check)
        host_section[host_name] = hostvars

        role_tokens = _union_roles(node)
        node_groups = _role_tokens_to_groups(role_tokens)

        # Every node joins autobot + autobot_cluster (centralized logging, etc.)
        node_groups |= _UNIVERSAL_ALL

        # Non-SLM nodes also join infrastructure + production_vms
        is_slm = bool(node_groups & {"slm", "slm_server", "slm_nodes"})
        if not is_slm:
            node_groups |= _UNIVERSAL_NON_SLM

        for g in node_groups:
            if g not in groups:
                groups[g] = {"hosts": {}}
            groups[g]["hosts"][host_name] = {}

    return {
        "all": {
            "vars": dict(_ALL_VARS),
            "hosts": host_section,
            "children": groups,
        }
    }


def validate_inventory(inv: dict, required_groups: frozenset = REQUIRED_GROUPS) -> None:
    """Raise ValueError if any required group key is absent from the inventory.

    Empty groups (key present, hosts dict empty) are allowed — Ansible
    handles them gracefully.  Missing keys cause "Could not match supplied
    host pattern" errors that are hard to diagnose at runtime.

    Args:
        inv: Inventory dict as returned by build_registry_inventory.
        required_groups: Set of group names that MUST be present as keys.

    Raises:
        ValueError: with a sorted list of every missing group name.
    """
    children = inv.get("all", {}).get("children", {})
    missing = sorted(required_groups - set(children.keys()))
    if missing:
        raise ValueError(
            f"Generated inventory is missing required groups: {missing}. "
            "Check ROLE_TO_GROUPS mapping in inventory_builder.py."
        )


def _write_inventory_file(inv: dict, path: Path) -> None:
    """Dump *inv* to *path* as YAML (UTF-8, mode 0600).

    Args:
        inv: Inventory dict from build_registry_inventory.
        path: Destination path; parent directory must exist.
    """
    path.write_text(
        yaml.dump(inv, default_flow_style=False, allow_unicode=True, sort_keys=True),
        encoding="utf-8",
    )
    path.chmod(0o600)
    logger.debug("Wrote dynamic inventory to %s", path)


def write_temp_inventory(inv: dict, uid_tmp_dir: str | None = None) -> Path:
    """Write *inv* to a unique temp file and return its Path.

    The file is created inside *uid_tmp_dir* (defaults to the uid-scoped
    ANSIBLE_LOCAL_TMP used by PlaybookExecutor) so it cannot collide across
    users.  The caller is responsible for deleting it after the playbook run.

    Args:
        inv: Inventory dict from build_registry_inventory.
        uid_tmp_dir: Directory for the temp file.  If None, uses
            ``/tmp/ansible_local_tmp_<uid>`` (nosec B108 — uid-scoped).

    Returns:
        Path to the written inventory file.
    """
    if uid_tmp_dir is None:
        uid_tmp_dir = f"/tmp/ansible_local_tmp_{os.getuid()}"  # nosec B108
    tmp_dir = Path(uid_tmp_dir)
    tmp_dir.mkdir(mode=0o700, exist_ok=True)

    fd, tmp_path_str = tempfile.mkstemp(
        prefix="autobot_inv_",
        suffix=".yml",
        dir=str(tmp_dir),
    )
    os.close(fd)
    tmp_path = Path(tmp_path_str)
    _write_inventory_file(inv, tmp_path)
    return tmp_path


def scan_playbook_dir_for_groups(playbook_dir: Path) -> frozenset:
    """Parse ``hosts:`` and ``groups[...]`` references from playbook YAML files.

    Used as a cross-check against the hardcoded REQUIRED_GROUPS constant.
    Returns the union set of all static group names referenced; skips Jinja2
    expressions and built-in names (all, localhost, target).

    Args:
        playbook_dir: Directory to search recursively for *.yml files.

    Returns:
        frozenset of group name strings found in the playbooks.
    """
    _STATIC = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
    _IGNORE = {"all", "localhost", "target"}

    found: set[str] = set()
    hosts_re = re.compile(r"^\s*-?\s*hosts:\s*([^\s#]+)")
    groups_re = re.compile(r"""groups\[['"]([a-zA-Z0-9_]+)['"]\]""")

    for yml_file in Path(playbook_dir).rglob("*.yml"):
        try:
            text = yml_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            m = hosts_re.match(line)
            if m:
                val = m.group(1).strip()
                if _STATIC.match(val) and val not in _IGNORE:
                    found.add(val)
            for g in groups_re.findall(line):
                if g not in _IGNORE:
                    found.add(g)

    return frozenset(found)
