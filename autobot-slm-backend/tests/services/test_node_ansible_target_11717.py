# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for Node.ansible_target fallback (#11717).

Regression guard: the dynamic registry inventory (services/inventory_builder.py,
#10109) keys every host by node_id and registers no IP alias. Before this fix,
ansible_target fell back to ip_address for nodes without ansible_name (every
auto-registered node), so `--limit <ip>` matched nothing and Ansible aborted
with "no hosts to target" before reconciler remediation could run.

The slm-backend root conftest stubs `sqlalchemy`/`models.database` as
MagicMocks for API tests (so importing api/* doesn't need a live DB). A bare
`from models.database import Node` would just get an inert MagicMock whose
attributes don't round-trip constructor kwargs, so this test would pass even
if the real property were wrong. Following the established real-load pattern
(tests/services/test_security_posture_auditor.py, #11224), this module
swaps in the REAL sqlalchemy + models.database for the duration of the test,
then restores the stubs so sibling test files are unaffected.
"""

import importlib
import importlib.util
import sys
from pathlib import Path

_slm_root = Path(__file__).parent.parent.parent
if str(_slm_root) not in sys.path:
    sys.path.insert(0, str(_slm_root))

_SQLALCHEMY_MODULES = ["sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio", "sqlalchemy.orm"]

_orig_modules = {name: sys.modules.get(name) for name in [*_SQLALCHEMY_MODULES, "models.database"]}
for _name in _SQLALCHEMY_MODULES:
    sys.modules.pop(_name, None)
try:
    for _name in _SQLALCHEMY_MODULES:
        importlib.import_module(_name)

    _real_md_spec = importlib.util.spec_from_file_location("models.database", _slm_root / "models" / "database.py")
    _real_md = importlib.util.module_from_spec(_real_md_spec)
    sys.modules["models.database"] = _real_md
    _real_md_spec.loader.exec_module(_real_md)
    Node = _real_md.Node
finally:
    for _name, _mod in _orig_modules.items():
        if _mod is not None:
            sys.modules[_name] = _mod
        else:
            sys.modules.pop(_name, None)

# TEST-NET-3 (RFC 5737) — reserved for documentation/examples, never a real
# AutoBot fleet address. Any value works here; only node_id/ansible_name matter.
_SAMPLE_IP = "203.0.113.26"


class TestAnsibleTargetFallback:
    """Node.ansible_target must resolve to a name the registry inventory has."""

    def test_falls_back_to_node_id_when_ansible_name_is_none(self):
        """Auto-registered node (ansible_name NULL) targets node_id, not ip_address.

        node_id is guaranteed to resolve in the registry inventory (#10109);
        the IP address is never registered as a host key/alias there.
        """
        node = Node(
            node_id="b9a29e04",
            hostname="VNC",
            ip_address=_SAMPLE_IP,
            ansible_name=None,
        )
        assert node.ansible_target == "b9a29e04"

    def test_prefers_ansible_name_when_set(self):
        """A node with an explicit ansible_name (static-inventory node) still wins."""
        node = Node(
            node_id="00-slm-manager",
            hostname="slm",
            ip_address="10.0.1.5",
            ansible_name="00-SLM-Manager",
        )
        assert node.ansible_target == "00-SLM-Manager"
