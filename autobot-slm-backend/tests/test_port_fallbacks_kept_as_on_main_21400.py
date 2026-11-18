# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21400: the sites that rendered a port with a fallback on ``main`` still do.

The static inventories (``inventory.yml``, ``inventory/hosts.yml``, ``hosts-router.yml``, ``slm-nodes.yml``) define
neither ``backend_port`` nor ``backend_nginx_port``; where they should learn them is an open owner decision on the
issue. Until then a play that used to render a value with ``| default(8443)`` must keep doing so, or it aborts on
those inventories. The list below is explicit: each entry is (file, exact text, expected occurrences).
"""

import re
from pathlib import Path

import pytest

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_FALLBACK = "default(8443)"
# Two kinds of site. "own": the site carries its own `| default(8443)` (its text is that literal expression).
# "shared": the site reads the scheme-matched variable, whose single definition holds the fallback.
_OWN, _SHARED = "own", "shared"
_SITES = [
    # The scheme-paired backend port is defined once (see test_frontend_upstream_port_matches_the_scheme_21400.py);
    # its definition holds the fallback, and its consumers read the variable.
    ("_shared/vars/backend_scheme_port.yml", "(backend_port | default(8443))", 2, _OWN),
    ("playbooks/rotate-service-keys.yml", ":{{ backend_scheme_port }}/api/health", 1, _SHARED),
    ("roles/frontend/templates/nginx-frontend.conf.j2", "{{ frontend_upstream_backend_port }} max_fails=", 1, _SHARED),
    ("roles/frontend/tasks/main.yml", ":{{ frontend_upstream_backend_port }}", 1, _SHARED),
    ("playbooks/toggle-enforcement.yml", ":{{ backend_nginx_port | default(8443) }}/api/health", 1, _OWN),
    ("playbooks/deploy-backend-remote.yml", ':{{ backend_nginx_port | default(8443) }}"', 1, _OWN),
    # Read through the backend host's own vars (the host that supplies the address), fallback kept (#21400).
    (
        "playbooks/health-check.yml",
        ":{{ hostvars[_backend_host[0]]['backend_nginx_port'] | default(8443) }}/api",
        2,
        _OWN,
    ),
    (
        "playbooks/health-check.yml",
        ":{{ (hostvars[_backend_host[0]]['backend_nginx_port'] | default(8443)) "
        "if _backend_host | length > 0 else 8443 }}/api",
        1,
        _OWN,
    ),
]
_BARE_USE = re.compile(r"\{\{\s*backend_(?:nginx_)?port\s*\}\}")


def _rendered_shared_fallback() -> str:
    """The shared definition rendered with no port variable defined: what main rendered."""
    import jinja2
    import yaml

    shared = yaml.safe_load((_ANSIBLE / "_shared" / "vars" / "backend_scheme_port.yml").read_text(encoding="utf-8"))
    return jinja2.Environment().from_string(shared["backend_scheme_port"]).render()


@pytest.mark.parametrize(("rel", "text", "count", "kind"), _SITES)
def test_site_keeps_the_fallback_main_had(rel: str, text: str, count: int, kind: str) -> None:
    content = (_ANSIBLE / rel).read_text(encoding="utf-8")
    assert content.count(text) == count, f"{rel}: expected {count}x {text!r}"
    if kind == _OWN:
        assert _FALLBACK in text, f"{rel}: an own-fallback site must spell its `{_FALLBACK}`"
        return
    # A shared site reads the single definition: it spells no fallback of its own, and that definition renders
    # 8443 when nothing is defined (the shared file's own rows above pin the literal).
    assert _FALLBACK not in text, f"{rel}: reads the shared variable, so it must not carry a second fallback"
    assert any(name in text for name in ("backend_scheme_port", "frontend_upstream_backend_port")), rel
    assert _rendered_shared_fallback() == "8443"


def test_a_site_that_switches_kind_fails_the_pin() -> None:
    """Control: an own-fallback expression is not a shared site and a shared reference is not an own one."""
    own = next(site for site in _SITES if site[3] == _OWN and "toggle" in site[0])
    shared = next(site for site in _SITES if site[3] == _SHARED and "rotate" in site[0])
    assert _FALLBACK in own[1] and _FALLBACK not in shared[1]
    assert _rendered_shared_fallback() == "8443"


@pytest.mark.parametrize("rel", sorted({site[0] for site in _SITES}))
def test_site_file_has_no_bare_port_use(rel: str) -> None:
    lines = (_ANSIBLE / rel).read_text(encoding="utf-8").splitlines()
    bare = [f"{rel}:{no}" for no, line in enumerate(lines, 1) if _BARE_USE.search(line)]
    assert bare == [], f"a port read without a fallback would abort on inventories that do not define it: {bare}"
