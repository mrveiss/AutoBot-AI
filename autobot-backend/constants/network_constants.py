#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Network Constants — Re-export shim (#1195)
==========================================

Canonical module lives in ``autobot-shared/network_constants.py``.
This shim re-exports every public name so that the 74+ backend files
using ``from constants.network_constants import ...`` keep working
with zero import changes.

The file is loaded directly via importlib to avoid a circular import:
  constants.network_constants → autobot_shared.__init__
  → redis_client → utils.redis_management.config
  → constants.network_constants  (incomplete)
"""

import importlib.util
import os
import sys

# ---------------------------------------------------------------------------
# Load the canonical module directly from the file, bypassing
# autobot_shared/__init__.py which triggers a circular import chain.
# ---------------------------------------------------------------------------
_MOD_NAME = "autobot_shared.network_constants"

if _MOD_NAME not in sys.modules:
    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.dirname(os.path.dirname(_here))

    # Try autobot-shared/ first (actual directory), then autobot_shared/
    for _candidate in ("autobot-shared", "autobot_shared"):
        _shared_file = os.path.join(_root, _candidate, "network_constants.py")
        if os.path.isfile(_shared_file):
            break

    _spec = importlib.util.spec_from_file_location(_MOD_NAME, _shared_file)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_MOD_NAME] = _mod
    _spec.loader.exec_module(_mod)
else:
    _mod = sys.modules[_MOD_NAME]

# Pull every name into this module's namespace so that
# ``from constants.network_constants import X`` keeps working.
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})

# Explicit names for static analysers / IDE auto-complete
NetworkConstants = _mod.NetworkConstants
ServiceURLs = _mod.ServiceURLs
NetworkConfig = _mod.NetworkConfig
DatabaseConstants = _mod.DatabaseConstants
get_network_config = _mod.get_network_config
BACKEND_URL = _mod.BACKEND_URL
FRONTEND_URL = _mod.FRONTEND_URL
REDIS_HOST = _mod.REDIS_HOST
REDIS_VM_IP = _mod.REDIS_VM_IP
MAIN_MACHINE_IP = _mod.MAIN_MACHINE_IP
LOCALHOST_IP = _mod.LOCALHOST_IP
_emit_deprecation_warning = _mod._emit_deprecation_warning
