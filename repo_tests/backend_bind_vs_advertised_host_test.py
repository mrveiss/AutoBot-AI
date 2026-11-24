# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#18810 / #22146: bind vs advertised host, and the one noVNC path home."""

import re

import pytest
import yaml
from jinja2 import ChainableUndefined, Environment
from repo_tests._paths import repo_root

from autobot_shared.egress_allowlist import _never_internal
from autobot_shared.ssot_config import VMConfig
from autobot_shared.ssot_reachable_host import host_or_default, is_unspecified_host
from autobot_shared.ssot_role_mirrors import NOVNC_PATH_DEFAULT
from tools.lint._comment_syntax import code_text

ROOT = repo_root()
ANSIBLE = ROOT / "autobot-slm-backend" / "ansible"
ENV_TEMPLATE = ANSIBLE / "roles" / "backend" / "templates" / "backend.env.j2"
ALL_VARS = ANSIBLE / "inventory" / "group_vars" / "all.yml"


def _rendered(**variables) -> dict[str, str]:
    env = Environment(undefined=ChainableUndefined)
    env.filters["bool"] = bool  # Ansible-only filter the template uses
    variables = {"backend_redis_password": "", "backend_redis_host": "h", **variables}
    text = env.from_string(ENV_TEMPLATE.read_text(encoding="utf-8")).render(**variables)
    pairs = (ln.split("=", 1) for ln in code_text(text, name="backend.env").splitlines() if "=" in ln)
    return {k: v for k, v in pairs}


def _advertised(backend_host: str, inventory_host: str | None) -> str:
    """Render ``backend_advertised_host`` from the role default with the real Jinja expression."""
    expr = yaml.safe_load(ALL_VARS.read_text(encoding="utf-8"))["backend_advertised_host"]
    extra = {"infrastructure": {"hosts": {"backend": inventory_host}}} if inventory_host else {}
    env = Environment()
    env.filters["regex_search"] = lambda v, p: (lambda m: m.group(0) if m else None)(re.search(p, v))  # Ansible filter
    return env.from_string(expr).render(backend_host=backend_host, slm_loopback_ipv4="127.0.0.1", **extra).strip()


def test_template_never_renders_bind_all_as_the_client_host() -> None:
    advertised = _advertised("0.0.0.0", "10.1.2.3")  # nosec B104
    out = _rendered(backend_host="0.0.0.0", backend_advertised_host=advertised, backend_port=8001)  # nosec B104
    assert out["AUTOBOT_BACKEND_BIND_HOST"] == "0.0.0.0"  # nosec B104
    assert out["AUTOBOT_BACKEND_HOST"] == "10.1.2.3"


def test_advertised_host_falls_back_to_loopback_without_inventory() -> None:
    assert _advertised("0.0.0.0", None) == "127.0.0.1"  # nosec B104
    assert _advertised("10.9.9.9", "10.1.2.3") == "10.9.9.9"


def test_unspecified_vm_main_is_kept_and_refused_not_substituted(monkeypatch) -> None:
    """A bind-all dialed host is left as written: egress refuses it, startup fails naming it."""
    monkeypatch.setenv("AUTOBOT_BACKEND_HOST", "0.0.0.0")  # nosec B104
    host = VMConfig(_env_file=None).main
    assert host == "0.0.0.0"  # nosec B104
    assert _never_internal(f"http://{host}:8001")  # the guard itself is unchanged
    assert not _never_internal("http://127.0.0.1:8001")


def test_empty_host_settings_take_the_default_without_logging(monkeypatch, caplog) -> None:
    monkeypatch.setenv("AUTOBOT_BACKEND_HOST", "")
    monkeypatch.setenv("AUTOBOT_BACKEND_BIND_HOST", " ")
    cfg = VMConfig(_env_file=None)
    assert (cfg.main, cfg.main_bind) == ("127.0.0.1", "127.0.0.1")
    assert not caplog.records
    assert host_or_default("backend.example") == "backend.example"
    assert is_unspecified_host("::") and is_unspecified_host("0.0.0.0")  # nosec B104
    assert not is_unspecified_host("") and not is_unspecified_host("backend.example")


def test_startup_validation_fails_naming_the_variable(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "autobot-backend"))
    import startup_validation

    ssot = startup_validation.config.vm  # the canonical reader; empty or unset already means the default
    monkeypatch.setattr(ssot, "main", "0.0.0.0")  # nosec B104
    message = startup_validation.validate_advertised_host()
    assert "AUTOBOT_BACKEND_HOST" in message and "AUTOBOT_BACKEND_BIND_HOST" in message
    monkeypatch.setattr(ssot, "main", "10.1.2.3")
    assert startup_validation.validate_advertised_host() is None
    monkeypatch.setenv("AUTOBOT_BACKEND_HOST", "")  # the default-host case, whatever the runner exports
    monkeypatch.setattr(ssot, "main", VMConfig(_env_file=None).main)
    assert startup_validation.validate_advertised_host() is None


def test_unit_runs_the_startup_validation_before_the_backend() -> None:
    unit = (ANSIBLE / "roles" / "backend" / "templates" / "autobot-backend.service.j2").read_text(encoding="utf-8")
    pre = [ln.split("=", 1)[1].split() for ln in unit.splitlines() if ln.startswith("ExecStartPre=")]
    assert any(cmd[-1].endswith("/startup_validation.py") for cmd in pre), pre


def test_loader_reads_the_bind_from_the_bind_variable() -> None:
    """``backend.server_host`` (default: bind-all, ``config/defaults.py``) is a bind setting; only the bind variable sets it."""
    loader = (ROOT / "autobot-backend/config/loader.py").read_text(encoding="utf-8")
    assert '"AUTOBOT_BACKEND_BIND_HOST": ["backend", "server_host"]' in loader
    assert '"AUTOBOT_BACKEND_HOST": ["backend"' not in loader


def test_every_env_file_writer_carries_the_bind_host() -> None:
    for name in (".env.example", ".env.base", ".env.localhost", ".env.network-template"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "AUTOBOT_BACKEND_BIND_HOST=" in text, name
    gen = (ROOT / "autobot-infrastructure/shared/scripts/generate-env-files.py").read_text(encoding="utf-8")
    assert gen.count("AUTOBOT_BACKEND_BIND_HOST=") == gen.count('f"AUTOBOT_BACKEND_HOST=') == 5
    deepseek = (ROOT / "autobot-infrastructure/shared/scripts/environment/set-env-deepseek.sh").read_text(
        encoding="utf-8"
    )
    assert "AUTOBOT_BACKEND_BIND_HOST=" in deepseek and "BACKEND_HOST:-0.0.0.0" not in deepseek


def test_bind_host_is_its_own_setting(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_BACKEND_BIND_HOST", "0.0.0.0")  # nosec B104
    monkeypatch.setenv("AUTOBOT_BACKEND_HOST", "10.1.2.3")
    cfg = VMConfig(_env_file=None)
    assert (cfg.main, cfg.main_bind) == ("10.1.2.3", "0.0.0.0")  # nosec B104


def test_novnc_path_has_one_home() -> None:
    role = yaml.safe_load(ALL_VARS.read_text(encoding="utf-8"))["novnc_path"]
    assert role == NOVNC_PATH_DEFAULT
    vnc_defaults = (ANSIBLE / "roles" / "vnc" / "defaults" / "main.yml").read_text(encoding="utf-8")
    assert "\nnovnc_path:" not in vnc_defaults  # not a second home
    template = ENV_TEMPLATE.read_text(encoding="utf-8")
    assert "AUTOBOT_NOVNC_PATH={{ novnc_path }}" in template and "novnc_path is defined" not in template
    unit = (ANSIBLE / "roles" / "vnc" / "templates" / "vnc-websockify.service.j2").read_text(encoding="utf-8")
    assert "--web={{ novnc_path }}" in unit


def test_fleet_update_converges_the_vnc_pin_with_the_account_guards() -> None:
    play = (ANSIBLE / "playbooks" / "update-all-nodes.yml").read_text(encoding="utf-8")
    assert "tasks_from: novnc" in play and "novnc_require_vnc_account: true" in play
    tasks = yaml.safe_load((ANSIBLE / "roles" / "vnc" / "tasks" / "novnc.yml").read_text(encoding="utf-8"))
    names = [t["name"] for t in tasks]
    assert "ansible.builtin.assert" in tasks[0] and tasks[0]["when"]
    assert any("account and group exist" in n for n in names[:2])
    pin = [i for i, n in enumerate(names) if "Download noVNC" in n][0]
    unpack = [i for i, n in enumerate(names) if "Unpack noVNC" in n][0]
    link = [i for i, n in enumerate(names) if n.startswith("Point ")][0]
    remove = [i for i, n in enumerate(names) if "Remove distro noVNC" in n][0]
    assert pin < unpack < link < remove  # the distro copy goes only once the pinned one is in place
    assert tasks[pin]["ansible.builtin.get_url"]["checksum"].startswith("sha256:")


def test_updater_renders_the_env_before_it_restarts_the_backend() -> None:
    play = (ANSIBLE / "playbooks" / "update-all-nodes.yml").read_text(encoding="utf-8")
    env = play.index("tasks_from: env_only")
    restart = play.index('- name: "[PLAY 2] Backend | Restart service"')
    assert env < restart


def _advertised_with(backend_host: str) -> str:
    expr = yaml.safe_load(ALL_VARS.read_text(encoding="utf-8"))["backend_advertised_host"]
    env = Environment()
    env.filters["regex_search"] = lambda v, p: (lambda m: m.group(0) if m else None)(re.search(p, v))  # Ansible filter
    return (
        env.from_string(expr)
        .render(
            backend_host=backend_host, slm_loopback_ipv4="127.0.0.1", infrastructure={"hosts": {"backend": "10.1.2.3"}}
        )
        .strip()
    )


_BIND_ALL_SPELLINGS = [  # nosec B104
    "0.0.0.0",
    "",
    "::",
    "::0",
    "0::0",
    "0:0::0",
    "0:0:0:0:0:0:0:0",
    "0000:0000:0000:0000:0000:0000:0000:0000",
    "::0.0.0.0",
    "[::]",
    "[::0]",
    "[0:0:0:0:0:0:0:0]",
    " :: ",
    "0:0:0:0:0:0:0:0".upper(),
]


@pytest.mark.parametrize("spelling", _BIND_ALL_SPELLINGS)
def test_every_bind_all_spelling_falls_back_to_the_inventory_host(spelling) -> None:
    assert _advertised_with(spelling) == "10.1.2.3"
    assert is_unspecified_host(spelling.strip()) or spelling == ""  # agrees with validate_advertised_host


def test_a_specific_backend_host_is_advertised_as_is() -> None:
    assert _advertised_with("10.9.9.9") == "10.9.9.9"


def test_config_service_reports_the_dial_host_not_the_bind_host() -> None:
    source = (ROOT / "autobot-backend/services/config_service.py").read_text(encoding="utf-8")
    assert "configured_host = BACKEND_HOST_IP" in source
    assert 'get("backend.server_host"' not in source


def test_vnc_convergence_runs_before_the_backend_restart_and_with_tags() -> None:
    plays = yaml.safe_load((ANSIBLE / "playbooks" / "update-all-nodes.yml").read_text(encoding="utf-8"))
    tasks = [t for play in plays for t in play.get("tasks", [])]
    names = [t.get("name", "") for t in tasks]
    vnc = next(i for i, n in enumerate(names) if "Converge the pinned noVNC" in n)
    restart = names.index("[PLAY 2] Backend | Restart service")
    assert vnc < restart  # VNCServerManager reads novnc_available once, at init
    task = tasks[vnc]
    assert task["ansible.builtin.include_role"]["apply"]["tags"] == ["backend", "vnc", "deploy"]
    assert task["tags"] == ["backend", "vnc", "deploy"]  # --tags backend must include the convergence too


def test_unpack_destination_follows_the_install_root() -> None:
    tasks = yaml.safe_load((ANSIBLE / "roles" / "vnc" / "tasks" / "novnc.yml").read_text(encoding="utf-8"))
    unpack = next(t for t in tasks if "ansible.builtin.unarchive" in t)["ansible.builtin.unarchive"]
    assert unpack["dest"] == "{{ novnc_install_root | dirname }}"
    assert unpack["creates"].startswith("{{ novnc_install_root }}")


def test_compose_bind_host_has_one_variable_for_command_and_env() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert compose.count("${AUTOBOT_BACKEND_BIND_HOST:-0.0.0.0}") == 2
    assert "AUTOBOT_BACKEND_BIND_HOST=0.0.0.0" not in compose


@pytest.mark.parametrize(
    "specific", ["10.9.9.9", "2001:db8::1", "[2001:db8::1]", "backend.example", "::1", "0:0:0:0:0:0:0:1"]
)
def test_a_specific_or_loopback_host_is_never_taken_for_bind_all(specific) -> None:
    assert _advertised_with(specific) == specific


def test_websockify_restart_handler_honours_the_no_restart_sync() -> None:
    handlers = yaml.safe_load((ANSIBLE / "roles" / "vnc" / "handlers" / "main.yml").read_text(encoding="utf-8"))
    handler = next(h for h in handlers if h["name"] == "restart websockify")
    assert "autobot_restart_services" in handler["when"]


def test_distro_novnc_stays_until_websockify_can_restart() -> None:
    tasks = yaml.safe_load((ANSIBLE / "roles" / "vnc" / "tasks" / "novnc.yml").read_text(encoding="utf-8"))
    removal = next(t for t in tasks if t.get("ansible.builtin.apt", {}).get("state") == "absent")
    assert "autobot_restart_services" in removal["when"]


def test_the_novnc_archive_has_one_path_variable() -> None:
    tasks = (ANSIBLE / "roles" / "vnc" / "tasks" / "novnc.yml").read_text(encoding="utf-8")
    assert tasks.count("{{ novnc_archive_path }}") == 2 and "/tmp/noVNC" not in tasks


def test_websockify_unit_destination_routes_through_the_systemd_unit_dir_var() -> None:
    tasks = yaml.safe_load((ANSIBLE / "roles" / "vnc" / "tasks" / "novnc.yml").read_text(encoding="utf-8"))
    unit = next(t for t in tasks if t.get("name") == "Deploy websockify systemd service")
    assert unit["ansible.builtin.template"]["dest"] == "{{ systemd_unit_dir }}/{{ websockify_service_name }}.service"
    group_vars = yaml.safe_load((ANSIBLE / "inventory" / "group_vars" / "all.yml").read_text(encoding="utf-8"))
    assert group_vars["systemd_unit_dir"] == "/etc/systemd/system"


def test_a_config_save_keeps_the_persisted_bind_host(monkeypatch, tmp_path) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "autobot-backend"))
    from services.config_service import ConfigService, config_manager

    cfg_file = tmp_path / "config.yaml"
    monkeypatch.setattr(config_manager, "base_config_file", cfg_file)
    # the merged config carries the environment override; the persisted value is read raw from the file
    monkeypatch.setattr(config_manager, "get_nested", lambda key, default=None: "10.9.9.9")
    cfg_file.write_text("backend:\n  server_host: 0.0.0.0\n", encoding="utf-8")  # nosec B104
    saved = {"backend": {"server_host": "10.1.2.3", "server_port": 8001}}
    ConfigService._keep_persisted_bind_host(saved)
    assert saved["backend"] == {"server_port": 8001, "server_host": "0.0.0.0"}  # nosec B104
    cfg_file.write_text("backend: {}\n", encoding="utf-8")
    fresh = {"backend": {"server_host": "10.1.2.3"}}
    ConfigService._keep_persisted_bind_host(fresh)
    assert fresh["backend"] == {}  # nothing stored: the reported dial host is never persisted as the bind
    cfg_file.unlink()
    missing = {"backend": {"server_host": "10.1.2.3"}}
    ConfigService._keep_persisted_bind_host(missing)
    assert missing["backend"] == {}
