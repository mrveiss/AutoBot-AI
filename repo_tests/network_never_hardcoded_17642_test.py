# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No network range is guessed, defaulted or fixed (#17642, #16833).

#17642: ``network_subnet`` is the source of firewall and pg_hba rules. Every
definition fell back to ``''`` or ``0.0.0.0/0`` and several uses added their own
``default('0.0.0.0/0')``, so an unresolved value opened the rule to any source
with no error. Each definition now ends in ``undef(hint=...)``, which stops the
play when the value is used -- and a consumer-side ``default`` would swallow
that refusal again, so none may exist.

#16833: docker-compose.yml fixed ``autobot-mgmt`` at 172.30.0.0/24, which took
over the host's route on a LAN using the same /24. The range now comes only
from AUTOBOT_DOCKER_MGMT_PREFIX, picked per host by docker/pick_mgmt_prefix.py.

**What these do not cover.** No play is run and no container started: the
refusal is checked as the definition's text and the host-detection function is
run with a stubbed ``ip``. A real install on a host whose network cannot be
detected is the end-to-end proof.
"""

from __future__ import annotations

import ast
import importlib.util
import ipaddress
import random
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

_ROOT = repo_root()
_ANSIBLE = _ROOT / "autobot-slm-backend" / "ansible"
_DEFINITION_FILES = [
    *_ROOT.glob("autobot-slm-backend/ansible/**/*.yml"),
    _ROOT / "install.sh",
]
_BUILDER = _ROOT / "autobot-slm-backend/services/inventory_builder.py"
_DEF_RE = re.compile(r"""["']?network_(subnet|gateway)["']?\s*:\s*\(?\s*\n?\s*["'](\{\{.*?\}\})""", re.S)


def _definitions() -> list[tuple[str, str]]:
    found = []
    for path in _DEFINITION_FILES:
        text = path.read_text(encoding="utf-8")
        found += [(path.name, m.group(2)) for m in _DEF_RE.finditer(text) if "lookup(" in m.group(2)]
    return found


def test_every_network_definition_refuses_instead_of_falling_back() -> None:
    defs = _definitions()
    assert len(defs) >= 15, f"expected 8 subnet + 7 gateway definitions, read {len(defs)}"
    open_ended = [
        (f, d)
        for f, d in defs
        if "undef(hint=" not in d or re.search(r"or '(0\.0\.0\.0(/0)?)?' \}\}|default\('0\.0\.0\.0", d)
    ]
    assert not open_ended, f"network definitions that fall back instead of refusing: {open_ended}"


def test_the_slm_generated_inventory_refuses_too() -> None:
    """inventory_builder.py builds both values through one helper; it must end in a refusal."""
    tree = ast.parse(_BUILDER.read_text(encoding="utf-8"))
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_secrets_lookup")
    body = ast.unparse(helper)
    assert "undef(hint=" in body and "0.0.0.0" not in body and "or ''" not in body
    calls = {
        k.value: v.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Dict)
        for k, v in zip(n.keys, n.values)
        if isinstance(k, ast.Constant) and k.value in ("network_subnet", "network_gateway") and isinstance(v, ast.Call)
    }
    assert calls == {"network_subnet": "_secrets_lookup", "network_gateway": "_secrets_lookup"}


def test_every_secrets_lookup_reaches_the_refusal() -> None:
    """grep exits 1 on a missing key; without `|| true` the pipe lookup raises first, hiding the hint."""
    piped = [(f, d) for f, d in _definitions() if "lookup('pipe'" in d]
    assert len(piped) >= 11, f"read {len(piped)} secrets-file lookups"
    assert all("2>/dev/null || true')" in d for _, d in piped), [f for f, d in piped if "|| true" not in d]
    assert "2>/dev/null || true')" in _BUILDER.read_text(encoding="utf-8")


@pytest.mark.skipif(not shutil.which("ansible"), reason="ansible is not installed on this runner")
def test_ansible_stops_with_the_hint_when_the_subnet_is_unset(tmp_path: Path) -> None:
    """The definition itself, evaluated by ansible: unset -> the hint; set -> the value."""
    definition = next(d for f, d in _definitions() if f == "slm-nodes.yml" and "NETWORK_SUBNET" in d)
    definition = definition.replace("/etc/autobot/slm-secrets.env", str(tmp_path / "absent.env"))
    inventory = {
        "all": {"hosts": {"localhost": {"ansible_connection": "local"}}, "vars": {"network_subnet": definition}}
    }
    inv = tmp_path / "inv.yml"
    inv.write_text(yaml.safe_dump(inventory), encoding="utf-8")
    cmd = ["ansible", "localhost", "-i", str(inv), "-m", "debug", "-a", "msg={{ network_subnet }}"]
    base = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "ANSIBLE_LOCAL_TEMP": str(tmp_path)}
    unset = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=base)
    assert unset.returncode != 0, unset.stdout
    assert "never falls back to an open range" in unset.stdout + unset.stderr, unset.stdout + unset.stderr
    blank = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env={**base, "NETWORK_SUBNET": "  "})
    assert blank.returncode != 0, "a whitespace-only NETWORK_SUBNET was accepted as a value"
    given = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120, env={**base, "NETWORK_SUBNET": "198.51.100.0/24"}
    )
    assert given.returncode == 0 and "198.51.100.0/24" in given.stdout, given.stdout + given.stderr


def test_no_use_of_network_subnet_supplies_its_own_default() -> None:
    uses = [
        f"{p.relative_to(_ROOT)}:{n}"
        for p in _ROOT.glob("autobot-slm-backend/ansible/**/*.yml")
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"network_(subnet|gateway)\s*\|\s*default", line)
    ]
    assert not uses, f"a default here swallows the refusal and re-opens the rule: {uses}"


# --- install.sh: given or detected, never guessed ---


def _detect(addr_line: str, route_line: str, env: str = "") -> subprocess.CompletedProcess:
    text = (_ROOT / "install.sh").read_text(encoding="utf-8")
    func = re.search(r"^detect_network\(\) \{.*?^\}", text, re.S | re.M)
    assert func, "detect_network() not found in install.sh"
    with tempfile.TemporaryDirectory() as tmp:
        stub = Path(tmp) / "ip"
        stub.write_text(
            f"#!/bin/sh\ncase \"$*\" in *addr*) echo '{addr_line}' ;; *route*) echo '{route_line}' ;; esac\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)
        script = f"""set -euo pipefail
fatal() {{ echo "FATAL: $*"; exit 1; }}
{env}
local_ip=192.0.2.10
{func.group(0)}
detect_network
echo "SUBNET=${{network_subnet}} GATEWAY=${{network_gateway}}"
"""
        return subprocess.run(
            [shutil.which("bash") or "bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
            env={"PATH": f"{tmp}:/usr/bin:/bin"},
        )


def test_detects_the_subnet_and_gateway_of_the_install_ip() -> None:
    out = _detect("    inet 192.0.2.10/26 brd 192.0.2.63 scope global eth0", "default via 192.0.2.1 dev eth0")
    assert "SUBNET=192.0.2.0/26 GATEWAY=192.0.2.1" in out.stdout, out.stdout + out.stderr


def test_a_given_value_that_is_not_a_network_stops_the_install() -> None:
    out = _detect(
        "    inet 192.0.2.10/26 scope global eth0",
        "default via 192.0.2.1 dev eth0",
        env="NETWORK_SUBNET=' ' NETWORK_GATEWAY=192.0.2.1",
    )
    assert out.returncode != 0 and "FATAL: No usable network" in out.stdout, out.stdout + out.stderr


def test_given_values_win_over_detection() -> None:
    out = _detect(
        "    inet 192.0.2.10/26 scope global eth0",
        "default via 192.0.2.1 dev eth0",
        env="NETWORK_SUBNET=198.51.100.0/24 NETWORK_GATEWAY=198.51.100.1",
    )
    assert "SUBNET=198.51.100.0/24 GATEWAY=198.51.100.1" in out.stdout, out.stdout + out.stderr


def test_an_undetectable_network_stops_the_install_instead_of_guessing() -> None:
    out = _detect("    inet 203.0.113.5/24 scope global eth0", "")
    assert out.returncode != 0
    assert "FATAL: No usable network for 192.0.2.10" in out.stdout, out.stdout + out.stderr
    assert "192.0.2.0/24" not in out.stdout, "the old /24-from-the-IP guess came back"


# --- docker-compose.yml + compose_fleet.py: one generated prefix ---


def _compose() -> dict:
    return yaml.safe_load((_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def _compose_hosts() -> dict[str, int]:
    hosts = {}
    for name, svc in _compose()["services"].items():
        addr = ((svc.get("networks") or {}).get("autobot-mgmt") or {}) if isinstance(svc.get("networks"), dict) else {}
        if "ipv4_address" in addr:
            prefix, _, host = addr["ipv4_address"].rpartition(".")
            assert prefix == "${AUTOBOT_DOCKER_MGMT_PREFIX}", (name, addr["ipv4_address"])
            hosts[name] = int(host)
    return hosts


def test_the_management_network_has_no_built_in_range() -> None:
    subnet = _compose()["networks"]["autobot-mgmt"]["ipam"]["config"][0]["subnet"]
    assert subnet.startswith("${AUTOBOT_DOCKER_MGMT_PREFIX:?") and subnet.endswith("}.0/24"), subnet
    assert len(_compose_hosts()) == 8
    assert "172.30." not in (_ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def test_compose_fleet_host_numbers_match_compose() -> None:
    tree = ast.parse((_ROOT / "autobot-slm-backend/services/compose_fleet.py").read_text(encoding="utf-8"))
    fleet = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            pairs = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
            if "id" in pairs and "host" in pairs:
                fleet[pairs["id"].value] = pairs["host"].value
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "_SLM_MGMT_HOST":
            fleet["autobot-slm"] = node.value.value
    assert fleet == _compose_hosts()


# --- docker/pick_mgmt_prefix.py ---


def _picker():
    spec = importlib.util.spec_from_file_location("pick_mgmt_prefix", _ROOT / "docker" / "pick_mgmt_prefix.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_routes_are_read_as_ranges_and_default_is_skipped() -> None:
    lines = [
        "default via 172.30.0.1 dev enp0s4",
        "172.30.0.0/24 dev enp0s4 proto kernel",
        "10.9.9.9 dev tun0",
        "blackhole 10.0.0.0/8",
        "unreachable 10.1.0.0/16 metric 5",
    ]
    expected = ["172.30.0.0/24", "10.9.9.9/32", "10.0.0.0/8", "10.1.0.0/16"]
    assert _picker().routes_in_use(lines) == [ipaddress.ip_network(n) for n in expected]


def test_the_pick_never_overlaps_a_used_range() -> None:
    picker = _picker()
    pool = ipaddress.ip_network("10.200.0.0/22")  # four /24s
    used = [ipaddress.ip_network(n) for n in ("10.200.0.0/24", "10.200.1.0/24", "10.200.3.0/24")]
    for seed in range(20):
        assert picker.pick(used, pool, random.Random(seed)) == "10.200.2"


@pytest.mark.parametrize("pool", ["127.0.0.0/8", "169.254.0.0/16", "8.8.0.0/16", "10.0.0.0/25"])
def test_a_pool_that_is_not_a_private_lan_block_is_refused(pool: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOBOT_DOCKER_MGMT_POOL", pool)
    with pytest.raises(SystemExit, match="AUTOBOT_DOCKER_MGMT_POOL must be"):
        _picker().main()


def test_a_full_pool_is_a_refusal_not_a_collision() -> None:
    picker = _picker()
    pool = ipaddress.ip_network("10.200.0.0/24")
    with pytest.raises(SystemExit, match="set AUTOBOT_DOCKER_MGMT_PREFIX by hand"):
        picker.pick([pool], pool, random.Random(0))
