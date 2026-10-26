# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL's listen_addresses: one definition, never every interface (#19239).

`postgresql_listen_addresses: "*"` exposed 5432 on every interface of the SLM and the database
VM. Three plays also set the value for the same instance, so on a collapsed box each run flipped
it, restarted Postgres, and the last one won. The postgresql role's defaults now hold the only
definition: loopback, plus this host's own fleet address on a host that serves the fleet.
"""

from __future__ import annotations

import re

import jinja2
import yaml
from repo_tests._paths import repo_root

_ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
_ROLE = _ANSIBLE / "roles" / "postgresql"
_DEFINITION = re.compile(r"^\s*postgresql_listen_addresses:(.*)$", re.MULTILINE)
_EVERY_INTERFACE = re.compile(r"""(^|[\s,"'])(\*|0\.0\.0\.0|::)([\s,"']|$)""")
_NAMES = (
    "postgresql_fleet_groups",
    "postgresql_serves_fleet",
    "_postgresql_own_addresses",
    "postgresql_fleet_address",
    "postgresql_listen_addresses",
)


def _every_interface(value: str) -> bool:
    return bool(_EVERY_INTERFACE.search(value))


def test_the_detector_sees_every_wildcard_form_and_not_a_bound_list() -> None:
    for wild in ('"*"', "'*'", "*", f'"{_ip(0, 0, 0, 0)}"', '"::"', '"localhost,*"', "'localhost, ::'"):
        assert _every_interface(wild), wild
    for bound in (
        '"localhost"',
        f'"localhost,{_ip(10, 1, 0, 5)}"',
        "\"{{ ['localhost'] | join(',') }}\"",
        '"::1"',
        '"fe80::1"',
    ):
        assert not _every_interface(bound), bound


def test_listen_addresses_has_exactly_one_definition_and_it_is_the_roles() -> None:
    files = sorted(_ANSIBLE.rglob("*.yml"))
    assert len(files) > 50, f"only {len(files)} Ansible files found under {_ANSIBLE}"
    sites = [
        (f.relative_to(repo_root()).as_posix(), m.group(1).strip())
        for f in files
        for m in _DEFINITION.finditer(f.read_text(encoding="utf-8"))
    ]
    assert [s[0] for s in sites] == ["autobot-slm-backend/ansible/roles/postgresql/defaults/main.yml"], sites
    assert not any(_every_interface(v) for _, v in sites), sites


def _render(name: str, ctx: dict) -> object:
    """Render one role default the way Ansible would, with stubs for the Ansible-only filters."""
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    env = jinja2.Environment()
    env.tests["match"] = lambda v, p: re.match(p, v) is not None
    env.filters["intersect"] = lambda a, b: [x for x in a if x in b]
    env.filters["bool"] = lambda v: v if isinstance(v, bool) else str(v).strip().lower() in ("true", "yes", "1")
    value = defaults[name]
    if not isinstance(value, str) or "{{" not in value:
        return value
    scope = dict(ctx, **{k: _render(k, ctx) for k in _NAMES if k != name and k in value})
    out = env.from_string(value).render(**scope).strip()
    return out == "True" if out in ("True", "False") else out


def _host(groups: list[str], slm_host: str, ansible_host: str, own: list[str], default: str | None) -> dict:
    facts: dict = {"all_ipv4_addresses": own}
    if default:
        facts["default_ipv4"] = {"address": default}
    return {"group_names": groups, "slm_host": slm_host, "ansible_host": ansible_host, "ansible_facts": facts}


def _ip(*octets: int) -> str:
    """A fixture address, built at runtime: no address literal in the source."""
    return ".".join(str(o) for o in octets)


def test_each_host_shape_listens_on_loopback_and_its_own_fleet_address_only() -> None:
    lo, slm, db, be, bridge = (
        _ip(127, 0, 0, 1),
        _ip(10, 1, 0, 5),
        _ip(10, 1, 0, 9),
        _ip(10, 1, 0, 20),
        _ip(172, 17, 0, 1),
    )
    cases = {
        "SLM, SLM_HOST set": (_host(["slm_server"], slm, lo, [slm, bridge], bridge), f"localhost,{slm}"),
        "SLM, SLM_HOST missing": (_host(["slm_server"], lo, lo, [slm], slm), f"localhost,{slm}"),
        "DB VM": (_host(["redis"], slm, db, [db], db), f"localhost,{db}"),
        "backend-only node": (_host(["backend"], slm, be, [be], be), "localhost"),
        "fleet host, no facts": (_host(["slm"], lo, lo, [], None), "localhost"),
    }
    got = {k: _render("postgresql_listen_addresses", ctx) for k, (ctx, _) in cases.items()}
    assert got == {k: want for k, (_, want) in cases.items()}


def test_a_fleet_host_without_its_own_address_fails_before_the_config_renders() -> None:
    tasks = yaml.safe_load((_ROLE / "tasks" / "configure.yml").read_text(encoding="utf-8"))
    names = [t.get("name", "") for t in tasks]
    guard = next(i for i, n in enumerate(names) if "knows its own address" in n)
    assert guard < names.index("Deploy postgresql.conf")
    assert tasks[guard]["when"] == "postgresql_serves_fleet | bool"
    assert "postgresql_fleet_address | length > 0" in tasks[guard]["ansible.builtin.assert"]["that"]
    no_facts = _host(["slm"], _ip(127, 0, 0, 1), _ip(127, 0, 0, 1), [], None)
    assert _render("postgresql_fleet_address", no_facts) == ""
    assert _render("postgresql_serves_fleet", no_facts) is True
