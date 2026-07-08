# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression guard for the PortInfo heartbeat schema (GH#11224).

The security-posture audit only works if the agent-reported bind ``address``
survives heartbeat ingest. Pydantic defaults to ``extra="ignore"``, so unless
``PortInfo`` declares ``address`` it is silently stripped at
``api/nodes.py`` (``[p.model_dump() for p in heartbeat.listening_ports]``) and
``Node.listening_ports`` never carries an address — making the audit inert.

This test loads the real ``models.schemas`` (the slm conftest stubs it for API
tests) and asserts the field round-trips.
"""

import importlib.util
import sys
from pathlib import Path

_slm_root = Path(__file__).parent.parent
if str(_slm_root) not in sys.path:
    sys.path.insert(0, str(_slm_root))


def _load_real(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _slm_root / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load real models.database (schemas imports NodeStatus from it) then real
# models.schemas, swapping the conftest stubs and restoring them afterwards.
_orig_db = sys.modules.get("models.database")
_orig_schemas = sys.modules.get("models.schemas")
_load_real("models.database", "models/database.py")
_schemas = _load_real("models.schemas", "models/schemas.py")
PortInfo = _schemas.PortInfo
if _orig_db is not None:
    sys.modules["models.database"] = _orig_db
else:
    sys.modules.pop("models.database", None)
if _orig_schemas is not None:
    sys.modules["models.schemas"] = _orig_schemas
else:
    sys.modules.pop("models.schemas", None)


class TestPortInfoSchemaAddress:
    def test_address_survives_model_dump(self):
        dumped = PortInfo(port=6379, process="redis", pid=42, address="0.0.0.0").model_dump()
        assert dumped["address"] == "0.0.0.0"

    def test_address_defaults_to_none_for_old_agents(self):
        dumped = PortInfo(port=6379, process="redis", pid=42).model_dump()
        assert dumped["address"] is None

    def test_extra_address_from_payload_is_not_dropped(self):
        # Mirrors ingest: dict from an agent heartbeat validated as PortInfo.
        payload = {"port": 5432, "process": "postgres", "pid": 9, "address": "127.0.0.1"}
        assert PortInfo(**payload).model_dump()["address"] == "127.0.0.1"
