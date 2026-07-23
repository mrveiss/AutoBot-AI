# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Smoke tests for autobot-infrastructure/shared/scripts/zero_downtime_deploy.py (#11779).

The blue-green and canary paths previously called nine methods that were never
defined (AttributeError mid-switch). These tests statically prove no ``self.X``
reference lacks a definition, and exercise the implemented methods with mocked
subprocess/service calls — no real deploys.
"""

import ast
import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "zero_downtime_deploy.py"


def test_no_undefined_self_references() -> None:
    """AST walk: every self.<name> load in ZeroDowntimeDeployer must be defined."""
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))

    cls = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "ZeroDowntimeDeployer"
    )

    defined = {n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    class_attrs = {
        target.id
        for node in cls.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    assigned = set()
    loaded = {}
    for node in ast.walk(cls):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
            if isinstance(node.ctx, ast.Store):
                assigned.add(node.attr)
            else:
                loaded.setdefault(node.attr, []).append(node.lineno)

    missing = {name: lines for name, lines in loaded.items() if name not in defined | assigned | class_attrs}
    assert not missing, f"Undefined self.<name> references: {missing}"


def _load_module():
    """Load the deploy script as a module (it is standalone by design, #11761)."""
    pytest.importorskip("aiohttp")
    pytest.importorskip("yaml")

    spec = importlib.util.spec_from_file_location("zero_downtime_deploy_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def deployer(tmp_path, monkeypatch):
    """ZeroDowntimeDeployer with a mocked BackupManager and tmp deployment dir."""
    module = _load_module()
    monkeypatch.setattr(module, "BackupManager", MagicMock())
    instance = module.ZeroDowntimeDeployer(deployment_dir=str(tmp_path / "deployments"))
    return module, instance


BLUE_GREEN_CANARY_METHODS = [
    "_cleanup_blue_environment",
    "_update_service_registry_for_green",
    "_switch_traffic_to_blue",
    "_start_canary_service",
    "_configure_canary_traffic",
    "_monitor_canary_health",
    "_cleanup_canary_environment",
    "_rollback_canary_traffic",
    "_finalize_canary_deployment",
]


def test_previously_missing_methods_exist_and_are_coroutines(deployer) -> None:
    """All nine previously-undefined methods exist as coroutine functions (#11779)."""
    _, instance = deployer
    for name in BLUE_GREEN_CANARY_METHODS:
        method = getattr(instance, name, None)
        assert method is not None, f"{name} is not defined"
        assert asyncio.iscoroutinefunction(method), f"{name} is not async"


def test_update_service_registry_for_green_records_urls(deployer) -> None:
    """Registry update re-points the in-process registry at the green ports."""
    _, instance = deployer
    green_services = {"backend": {"port": 9001}, "frontend": {"port": 6173}}

    asyncio.run(instance._update_service_registry_for_green(green_services))

    assert instance.service_registry.services["backend"] == "http://localhost:9001"
    assert instance.service_registry.services["frontend"] == "http://localhost:6173"


def test_generate_nginx_config_interpolates_ports(deployer) -> None:
    """Nginx config is a real f-string — ports and env are interpolated (#11779)."""
    _, instance = deployer
    config = instance._generate_nginx_config({"backend": {"port": 9001}, "frontend": {"port": 6173}}, "green")

    assert "server localhost:9001;" in config
    assert "server localhost:6173;" in config
    assert "autobot_backend_green" in config
    assert "{env}" not in config and "{services" not in config


def test_generate_canary_nginx_config_weights_traffic(deployer) -> None:
    """Canary config splits traffic between blue and canary upstreams."""
    _, instance = deployer
    canary_services = {"backend": {"port": 10001}, "frontend": {"port": 7173}}

    config = instance._generate_canary_nginx_config(canary_services, 10)
    assert "server localhost:8001 weight=90;" in config
    assert "server localhost:10001 weight=10;" in config

    full = instance._generate_canary_nginx_config(canary_services, 100)
    assert "server localhost:10001;" in full
    assert "weight=" not in full


def test_traffic_and_cleanup_paths_use_mocked_calls(deployer, monkeypatch) -> None:
    """Blue switch/cleanup and canary rollback run without real subprocess calls."""
    module, instance = deployer

    stopped = []

    async def fake_stop(service_name):
        stopped.append(service_name)

    monkeypatch.setattr(instance, "_stop_service", fake_stop)
    # Development mode (no nginx) — traffic switches are logical no-ops
    instance.deployment_config["load_balancer"]["type"] = "none"

    assert asyncio.run(instance._switch_traffic_to_blue()) is True
    assert asyncio.run(instance._rollback_canary_traffic()) is True
    assert asyncio.run(instance._configure_canary_traffic({}, 25)) is True

    asyncio.run(instance._cleanup_blue_environment())
    assert stopped == ["backend", "frontend"]


def test_monitor_canary_health_delegates_to_green_monitor(deployer, monkeypatch) -> None:
    """Canary monitoring reuses the green load-verification loop."""
    _, instance = deployer
    calls = {}

    async def fake_verify(services, monitoring_duration):
        calls["args"] = (services, monitoring_duration)
        return True

    monkeypatch.setattr(instance, "_verify_green_under_load", fake_verify)

    result = asyncio.run(instance._monitor_canary_health({"backend": {}}, duration=42))
    assert result is True
    assert calls["args"] == ({"backend": {}}, 42)
