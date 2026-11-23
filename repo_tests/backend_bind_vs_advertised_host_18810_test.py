# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#18810 / #22146: bind vs advertised host, and the one noVNC path home."""

from pathlib import Path

import yaml
from jinja2 import ChainableUndefined, Environment

from autobot_shared.egress_allowlist import _never_internal
from autobot_shared.ssot_config import VMConfig
from autobot_shared.ssot_reachable_host import reachable_host
from autobot_shared.ssot_role_mirrors import NOVNC_PATH_DEFAULT

ANSIBLE = Path(__file__).resolve().parents[1] / "autobot-slm-backend" / "ansible"
ENV_TEMPLATE = ANSIBLE / "roles" / "backend" / "templates" / "backend.env.j2"
BACKEND_DEFAULTS = ANSIBLE / "roles" / "backend" / "defaults" / "main.yml"
VNC_DEFAULTS = ANSIBLE / "roles" / "vnc" / "defaults" / "main.yml"


def _rendered(**variables) -> dict[str, str]:
    env = Environment(undefined=ChainableUndefined)
    env.filters["bool"] = bool  # Ansible-only filter the template uses
    variables = {"backend_redis_password": "", "backend_redis_host": "h", **variables}
    text = env.from_string(ENV_TEMPLATE.read_text(encoding="utf-8")).render(**variables)
    pairs = (ln.split("=", 1) for ln in text.splitlines() if "=" in ln and not ln.startswith("#"))
    return {k: v for k, v in pairs}


def _advertised(backend_host: str, inventory_host: str | None) -> str:
    """Render ``backend_advertised_host`` from the role default with the real Jinja expression."""
    expr = yaml.safe_load(BACKEND_DEFAULTS.read_text(encoding="utf-8"))["backend_advertised_host"]
    extra = {"infrastructure": {"hosts": {"backend": inventory_host}}} if inventory_host else {}
    return Environment().from_string(expr).render(backend_host=backend_host, **extra).strip()


def test_template_never_renders_bind_all_as_the_client_host() -> None:
    advertised = _advertised("0.0.0.0", "10.1.2.3")  # nosec B104
    out = _rendered(backend_host="0.0.0.0", backend_advertised_host=advertised, backend_port=8001)  # nosec B104
    assert out["AUTOBOT_BACKEND_BIND_HOST"] == "0.0.0.0"  # nosec B104
    assert out["AUTOBOT_BACKEND_HOST"] == "10.1.2.3"


def test_advertised_host_falls_back_to_loopback_without_inventory() -> None:
    assert _advertised("0.0.0.0", None) == "127.0.0.1"  # nosec B104
    assert _advertised("10.9.9.9", "10.1.2.3") == "10.9.9.9"


def test_unspecified_vm_main_is_replaced_and_egress_accepts_the_result(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_BACKEND_HOST", "0.0.0.0")  # nosec B104
    host = VMConfig(_env_file=None).main
    assert host == "127.0.0.1"
    assert not _never_internal(f"http://{host}:8001")
    assert _never_internal("http://0.0.0.0:8001")  # the guard itself is unchanged  # nosec B104


def test_reachable_host_logs_loudly(caplog) -> None:
    assert reachable_host("::") == "127.0.0.1"
    assert "AUTOBOT_BACKEND_BIND_HOST" in caplog.text
    assert reachable_host("backend.example") == "backend.example"


def test_bind_host_is_its_own_setting(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_BACKEND_BIND_HOST", "0.0.0.0")  # nosec B104
    monkeypatch.setenv("AUTOBOT_BACKEND_HOST", "10.1.2.3")
    cfg = VMConfig(_env_file=None)
    assert (cfg.main, cfg.main_bind) == ("10.1.2.3", "0.0.0.0")  # nosec B104


def test_novnc_path_has_one_home() -> None:
    role = yaml.safe_load(VNC_DEFAULTS.read_text(encoding="utf-8"))["novnc_path"]
    assert role == NOVNC_PATH_DEFAULT
    assert (
        _rendered(backend_host="127.0.0.1", backend_advertised_host="127.0.0.1", novnc_path=role)["AUTOBOT_NOVNC_PATH"]
        == role
    )
    unit = (ANSIBLE / "roles" / "vnc" / "templates" / "vnc-websockify.service.j2").read_text(encoding="utf-8")
    assert "--web={{ novnc_path }}" in unit


def test_fleet_update_converges_the_vnc_pin() -> None:
    play = (ANSIBLE / "playbooks" / "update-all-nodes.yml").read_text(encoding="utf-8")
    assert "tasks_from: novnc" in play
    assert (ANSIBLE / "roles" / "vnc" / "tasks" / "novnc.yml").is_file()
