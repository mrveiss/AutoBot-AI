# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Load ``business_intelligence_dashboard`` against stubbed heavy dependencies (#22157).

Moved unchanged from the bootstrap that ``test_bi_dashboard.py`` and the network
utilisation test each carried a copy of. Registered by ``tests/conftest.py`` under
``_slm_bi_dashboard_loader`` (the ``spec_from_file_location`` pattern the root
conftest uses for ``_slm_module_stub``), so no test needs a ``sys.path`` shim.
"""

import importlib.util
import logging
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

# #11794: every sys.modules key this bootstrap writes.  Snapshotted before and
# restored right after the module under test is loaded — the bare ModuleType
# stand-ins (autobot_shared.redis_client has no get_async_redis_client, …)
# otherwise leak into every later-collected test file in a sweep
# (tests/test_rbac_*.py, tests/test_port_scanner_address.py).  Runtime tests
# only use patch.object(_bid_mod, ...), never sys.modules lookups.
_TOUCHED_KEYS = (
    "matplotlib",
    "matplotlib.pyplot",
    "aiofiles",
    "jinja2",
    "performance_monitor",
    "autobot_shared",
    "autobot_shared.network_constants",
    "autobot_shared.monitoring",
    "autobot_shared.monitoring.prometheus_query",
    "autobot_shared.redis_client",
    "autobot_shared.http_client",
    "autobot_shared.logging_manager",
    "autobot_shared.ssot_config",
    "business_intelligence_dashboard",
)

_SLM_ROOT = Path(__file__).resolve().parent.parent


class _NC:
    REDIS_VM_IP = "127.0.0.1"


class StubCostModel:
    cpu_monthly_usd = 55.0
    gpu_monthly_usd = 85.0
    npu_monthly_usd = 35.0
    memory_monthly_usd = 22.0
    storage_monthly_usd = 28.0
    network_monthly_usd = 90.0
    cpu_baseline_efficiency = 70.0
    gpu_baseline_efficiency = 60.0
    npu_baseline_efficiency = 50.0
    memory_baseline_efficiency = 80.0
    storage_baseline_efficiency = 60.0
    network_baseline_efficiency = 40.0
    # Issue #10778: link capacity 0 = unknown → no fabricated network %
    network_link_capacity_mbps = 0.0


class _StubConfig:
    cost_model = StubCostModel()


class _FakeTemplate:
    def __init__(self, src):
        self._src = src

    def render(self, **kwargs):
        return self._src


class _FakeNetIO:
    def __init__(self, bytes_sent=0, bytes_recv=0):
        self.bytes_sent = bytes_sent
        self.bytes_recv = bytes_recv


def _stub_third_party(stub_psutil: bool) -> None:
    _matplotlib = types.ModuleType("matplotlib")
    _matplotlib.use = lambda *a, **kw: None
    sys.modules.setdefault("matplotlib", _matplotlib)
    sys.modules.setdefault("matplotlib.pyplot", types.ModuleType("matplotlib.pyplot"))

    # numpy stub — only polyfit/arange/std/array are exercised
    import numpy as _real_numpy

    sys.modules.setdefault("numpy", _real_numpy)
    sys.modules.setdefault("aiofiles", types.ModuleType("aiofiles"))
    _jinja2 = types.ModuleType("jinja2")
    _jinja2.Template = _FakeTemplate
    sys.modules.setdefault("jinja2", _jinja2)

    # performance_monitor stub (local SLM dep)
    _pm = types.ModuleType("performance_monitor")
    _pm.ALERT_THRESHOLDS = {"cpu_percent": 80.0, "memory_percent": 85.0}
    sys.modules["performance_monitor"] = _pm

    if stub_psutil:  # net_io_counters used in _sample_net_bytes_per_sec
        _psutil = types.ModuleType("psutil")
        _psutil.net_io_counters = lambda: _FakeNetIO(bytes_sent=5_000_000, bytes_recv=3_000_000)
        sys.modules.setdefault("psutil", _psutil)


def _stub_monitoring() -> None:
    _pq = types.ModuleType("autobot_shared.monitoring.prometheus_query")
    _pq.query_instant = AsyncMock(return_value=None)
    _monitoring_pkg = types.ModuleType("autobot_shared.monitoring")
    # Keep it a *package*. Without __path__ this plain module shadows the real
    # `autobot_shared.monitoring` for the whole process, and any later import of a
    # submodule it does not stub fails with "is not a package" — even though the
    # submodule exists on disk. It is installed at import scope with no teardown, so
    # the damage is not confined to this file: it broke collection of
    # test_rbac_middleware_cache.py and test_rbac_permission_denied_audit.py in
    # seven of twelve shards the moment something imported
    # `autobot_shared.monitoring.metrics.audit` (#14750, same class as #14741).
    # Pointing __path__ at the real directory keeps the stubbed `prometheus_query`
    # in place while letting every other submodule resolve from disk.
    _monitoring_pkg.__path__ = [str(_SLM_ROOT.parent / "autobot_shared" / "monitoring")]
    sys.modules["autobot_shared.monitoring"] = _monitoring_pkg
    sys.modules["autobot_shared.monitoring.prometheus_query"] = _pq


def _stub_autobot_shared() -> None:
    sys.modules.setdefault("autobot_shared", types.ModuleType("autobot_shared"))
    _nc = types.ModuleType("autobot_shared.network_constants")
    _nc.NetworkConstants = _NC
    sys.modules["autobot_shared.network_constants"] = _nc
    _stub_monitoring()
    sys.modules["autobot_shared.redis_client"] = types.ModuleType("autobot_shared.redis_client")
    sys.modules["autobot_shared.http_client"] = types.ModuleType("autobot_shared.http_client")
    _lm = types.ModuleType("autobot_shared.logging_manager")
    _lm.get_logger = logging.getLogger
    sys.modules["autobot_shared.logging_manager"] = _lm
    _ssot = types.ModuleType("autobot_shared.ssot_config")
    _ssot.get_config = lambda: _StubConfig()
    sys.modules["autobot_shared.ssot_config"] = _ssot


def load_business_intelligence_dashboard(stub_psutil: bool = False) -> types.ModuleType:
    """Return the dashboard module loaded from its file with every stub removed again afterwards.

    ``stub_psutil`` installs the fake ``psutil`` the network-utilisation tests need.
    """
    pre_bootstrap = {key: sys.modules.get(key) for key in _TOUCHED_KEYS}
    if stub_psutil:  # restore or remove the fake too; a real psutil the unstubbed path imports stays loaded
        pre_bootstrap["psutil"] = sys.modules.get("psutil")
    _stub_third_party(stub_psutil)
    _stub_autobot_shared()
    path = _SLM_ROOT / "monitoring" / "business_intelligence_dashboard.py"
    spec = importlib.util.spec_from_file_location("business_intelligence_dashboard", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["business_intelligence_dashboard"] = module
    spec.loader.exec_module(module)
    # #11794: restore the pre-bootstrap state of every touched key (see above).
    for key, previous in pre_bootstrap.items():
        if previous is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = previous
    return module
