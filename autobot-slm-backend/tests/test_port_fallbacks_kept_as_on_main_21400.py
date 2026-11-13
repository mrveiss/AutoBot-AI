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
_SITES = [
    # The frontend upstream port is one role variable (paired with the proxy scheme, see
    # test_frontend_upstream_port_matches_the_scheme_21400.py); its definition holds the fallback.
    ("roles/frontend/defaults/main.yml", "(backend_port | default(8443))", 2),
    ("roles/frontend/templates/nginx-frontend.conf.j2", "{{ frontend_upstream_backend_port }} max_fails=", 1),
    ("roles/frontend/tasks/main.yml", ":{{ frontend_upstream_backend_port }}", 1),
    ("playbooks/rotate-service-keys.yml", ":{{ backend_nginx_port | default(8443) }}/api/health", 1),
    ("playbooks/toggle-enforcement.yml", ":{{ backend_nginx_port | default(8443) }}/api/health", 1),
    ("playbooks/deploy-backend-remote.yml", ':{{ backend_nginx_port | default(8443) }}"', 1),
    # Read through the backend host's own vars (the host that supplies the address), fallback kept (#21400).
    ("playbooks/health-check.yml", ":{{ hostvars[_backend_host[0]]['backend_nginx_port'] | default(8443) }}/api", 2),
    (
        "playbooks/health-check.yml",
        ":{{ (hostvars[_backend_host[0]]['backend_nginx_port'] | default(8443)) "
        "if _backend_host | length > 0 else 8443 }}/api",
        1,
    ),
]
_BARE_USE = re.compile(r"\{\{\s*backend_(?:nginx_)?port\s*\}\}")


@pytest.mark.parametrize(("rel", "text", "count"), _SITES)
def test_site_keeps_the_fallback_main_had(rel: str, text: str, count: int) -> None:
    content = (_ANSIBLE / rel).read_text(encoding="utf-8")
    assert content.count(text) == count, f"{rel}: expected {count}x {text!r}"
    assert _FALLBACK in text


@pytest.mark.parametrize("rel", sorted({site[0] for site in _SITES}))
def test_site_file_has_no_bare_port_use(rel: str) -> None:
    lines = (_ANSIBLE / rel).read_text(encoding="utf-8").splitlines()
    bare = [f"{rel}:{no}" for no, line in enumerate(lines, 1) if _BARE_USE.search(line)]
    assert bare == [], f"a port read without a fallback would abort on inventories that do not define it: {bare}"
