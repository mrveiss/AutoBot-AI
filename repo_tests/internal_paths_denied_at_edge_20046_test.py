# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20046: the service-to-service routes are denied at every public nginx edge.

``/api/internal/`` carries the SSH-password proposal and claim (backend) and deletion (SLM) routes. They are
authenticated by the shared internal key, and ``autobot-slm.conf.j2`` injects that key for admin sessions on
``/autobot-api/``; so unless the edge refuses these paths, an admin's browser session reaches them with the key
attached. Every config below must carry a ``location ^~`` deny for each public prefix it proxies.
"""

from __future__ import annotations

import re
from pathlib import Path

from autobot_shared.slm_credential_deletion import PROPOSAL_PATH, claim_path, delete_path

_ROOT = Path(__file__).resolve().parent.parent
_CONFIGS = (
    "docker/nginx/nginx-locations.conf",
    "docker/nginx/nginx-slm-locations.conf",
    "autobot-infrastructure/shared/config/nginx/slm-site.conf",
    "autobot-slm-backend/ansible/roles/frontend/templates/nginx-frontend.conf.j2",
    "autobot-slm-backend/ansible/roles/slm_manager/templates/autobot-slm.conf.j2",
)
#: A proxied public prefix and the internal prefix under it that must be denied.
_PUBLIC_TO_DENY = {
    "/api/": "/api/internal/",
    "/slm/api/": "/slm/api/internal/",
    "/autobot-api/": "/autobot-api/internal/",
}


def _text(relative: str) -> str:
    return (_ROOT / relative).read_text(encoding="utf-8")


def _denied(text: str, prefix: str) -> bool:
    return re.search(rf"location\s+\^~\s+{re.escape(prefix)}\s*\{{\s*return\s+404;", text) is not None


def _proxies(text: str, public: str) -> bool:
    return re.search(rf"location\s+{re.escape(public)}\s*\{{", text) is not None


def test_each_config_denies_the_internal_prefix_under_every_public_prefix_it_proxies() -> None:
    checked = 0
    for relative in _CONFIGS:
        text = _text(relative)
        proxied = [public for public in _PUBLIC_TO_DENY if _proxies(text, public)]
        assert proxied, f"{relative}: no proxied /api/ prefix found, so this test read nothing"
        for public in proxied:
            checked += 1
            assert _denied(
                text, _PUBLIC_TO_DENY[public]
            ), f"{relative} proxies {public} but does not deny {_PUBLIC_TO_DENY[public]}"
    assert checked >= len(_CONFIGS)


def test_the_edge_covers_the_key_injecting_prefix() -> None:
    text = _text("autobot-slm-backend/ansible/roles/slm_manager/templates/autobot-slm.conf.j2")
    assert "X-Internal-API-Key" in text and _proxies(text, "/autobot-api/")
    assert _denied(text, "/autobot-api/internal/")


def test_the_routes_sit_under_the_denied_prefixes() -> None:
    internal = tuple(_PUBLIC_TO_DENY["/api/"] for _ in (0,))
    assert PROPOSAL_PATH.startswith(internal)
    assert claim_path("x").startswith(internal)
    assert delete_path("n").startswith(internal)


def test_contrast_a_config_without_the_deny_is_caught() -> None:
    assert not _denied("location /api/ { proxy_pass http://x; }", "/api/internal/")
    assert _denied("location ^~ /api/internal/ {\n    return 404;\n}", "/api/internal/")
