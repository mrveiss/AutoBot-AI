# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every nginx location that injects the internal service key must gate it (#16374).

``autobot-slm.conf.j2``'s ``location /autobot-api/`` used to forward
``X-Internal-API-Key`` — which ``autobot-backend/auth_middleware.py`` treats as
admin — to whichever caller reached the SLM host's nginx, with no session check
in front of it. The owner's contain-first fix is an ``auth_request`` subrequest
against the caller's SLM session, run before the key is added, so a request
with no valid session gets nginx's own 401/403 and never reaches ``proxy_pass``.

This guard encodes the invariant directly: **every** ``location`` in **every**
nginx-shaped Jinja template that sets ``X-Internal-API-Key`` must also declare
``auth_request`` pointed at a location marked ``internal;`` in the same
``server`` block. Templates are discovered dynamically (any ``.j2`` file
that declares an nginx ``location`` block) rather than off a hand-maintained
list, so a new template that reintroduces this pattern is caught without
anyone remembering to add it here — the same lesson #13604 encoded in
``nginx_websocket_proxy_test.py``, which this module borrows its Jinja/location
parsing from.

The tests are static — they read the templates as text. No nginx and no
running backend is involved, so they hold in CI.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root

REPO_ROOT = repo_root()

_KEY_HEADER = "X-Internal-API-Key"


class _Location:
    """One nginx ``location`` block: its modifier/pattern and raw body text."""

    def __init__(self, modifier: str, pattern: str, body: str) -> None:
        self.modifier = modifier
        self.pattern = pattern
        self.body = body

    @property
    def is_internal(self) -> bool:
        return bool(re.search(r"(?:^|[\s;{])internal\s*;", self.body))

    @property
    def injects_key(self) -> bool:
        return _KEY_HEADER in self.body

    @property
    def auth_request_target(self) -> str | None:
        match = re.search(r"auth_request\s+([^\s;]+)\s*;", self.body)
        return match.group(1) if match else None

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"location {self.modifier} {self.pattern}".replace("  ", " ")


def _strip_jinja(text: str) -> str:
    """Drop Jinja markers, keeping the nginx structure they wrap.

    Mirrors ``nginx_websocket_proxy_test.py``: conditional arms are all
    reachable on some host, so they are kept rather than evaluated.
    """
    text = re.sub(r"\{%.*?%\}", "", text, flags=re.DOTALL)
    return re.sub(r"\{\{.*?\}\}", "X", text, flags=re.DOTALL)


def _block_end(text: str, start: int) -> int:
    """Index just past the ``}`` closing the block opened before *start*."""
    depth, i = 1, start
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return i


def _locations_in(body: str) -> list[_Location]:
    """Every ``location`` block directly inside one server body."""
    found: list[_Location] = []
    for match in re.finditer(r"location\s+([=~^*]*)\s*([^\s{]+)\s*\{", body):
        end = _block_end(body, match.end())
        found.append(_Location(match.group(1).strip(), match.group(2), body[match.end() : end - 1]))
    return found


def _server_blocks(text: str) -> list[list[_Location]]:
    """Every ``server`` block's locations, kept separate (#16374).

    ``auth_request`` targets a location by name, and location names are scoped
    to their enclosing ``server`` block — resolving a target against the
    wrong server would either miss a real gap or invent one.
    """
    out: list[list[_Location]] = []
    for server in re.finditer(r"\bserver\s*\{", text):
        body = text[server.end() : _block_end(text, server.end()) - 1]
        out.append(_locations_in(body))
    return out


def find_ungated_key_injections(text: str) -> list[str]:
    """Every ``location`` in *text* that sets the internal key unsafely.

    A location is safe when it declares ``auth_request`` pointed at a location
    in the same server block that is itself ``internal;`` — nginx then answers
    a failed check with that subrequest's own status (401/403) and never runs
    ``proxy_pass`` in the gated location (fail-closed by construction).
    """
    violations: list[str] = []
    for locations in _server_blocks(_strip_jinja(text)):
        internal_names = {loc.pattern for loc in locations if loc.is_internal}
        for loc in locations:
            if not loc.injects_key:
                continue
            target = loc.auth_request_target
            if target is None:
                violations.append(f"{loc!r}: sets {_KEY_HEADER} with no auth_request directive")
            elif target not in internal_names:
                violations.append(
                    f"{loc!r}: auth_request {target} does not name an `internal;` " "location in the same server block"
                )
    return violations


def _nginx_template_paths() -> list[Path]:
    """Every ``.j2`` template that declares an nginx ``location`` block.

    Discovered by content, not a hand-maintained path list — a config-shaped
    template (a ``location`` block exists) is in scope regardless of where it
    lives, so a new proxy vhost is covered without a matching edit here.
    """
    paths = []
    for path in sorted(REPO_ROOT.glob("**/*.j2")):
        if "node_modules" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"location\s+[=~^*]*\s*[^\s{]+\s*\{", text):
            paths.append(path)
    return paths


def test_every_nginx_template_gates_its_internal_key_injections() -> None:
    """No discovered template may forward X-Internal-API-Key unchecked."""
    templates = _nginx_template_paths()
    assert templates, "no nginx-shaped .j2 template found — the discovery glob is broken"

    all_violations: list[str] = []
    for path in templates:
        violations = find_ungated_key_injections(path.read_text(encoding="utf-8"))
        rel = path.relative_to(REPO_ROOT)
        all_violations.extend(f"{rel}: {v}" for v in violations)

    assert not all_violations, (
        "these locations forward the trusted internal-service key without a "
        "fail-closed session check in front of them (#16374): " + "; ".join(all_violations)
    )


def test_autobot_slm_conf_is_among_the_scanned_templates() -> None:
    """Guard the discovery glob itself: the template #16374 was filed against."""
    rels = {p.relative_to(REPO_ROOT).as_posix() for p in _nginx_template_paths()}
    assert (
        "autobot-slm-backend/ansible/roles/slm_manager/templates/autobot-slm.conf.j2" in rels
    ), f"expected autobot-slm.conf.j2 among {len(rels)} discovered templates"


# ---------------------------------------------------------------------------
# Planted self-test: the detector must actually fire, and only on the bug.
# ---------------------------------------------------------------------------

_UNGATED = """
server {
    listen 443 ssl;
    location /autobot-api/ {
        proxy_pass http://backend/api/;
        proxy_set_header X-Internal-API-Key "{{ autobot_internal_api_key }}";
    }
}
"""

_AUTH_REQUEST_TARGETS_NON_INTERNAL_LOCATION = """
server {
    listen 443 ssl;
    location = /check {
        proxy_pass http://backend/api/auth/me;
    }
    location /autobot-api/ {
        auth_request /check;
        proxy_pass http://backend/api/;
        proxy_set_header X-Internal-API-Key "{{ autobot_internal_api_key }}";
    }
}
"""

_PROPERLY_GATED = """
server {
    listen 443 ssl;
    location = /check {
        internal;
        proxy_pass http://backend/api/auth/me;
    }
    location /autobot-api/ {
        auth_request /check;
        proxy_pass http://backend/api/;
        proxy_set_header X-Internal-API-Key "{{ autobot_internal_api_key }}";
    }
}
"""


def test_self_ungated_injection_is_detected() -> None:
    """A location setting the key with no auth_request at all must fail."""
    violations = find_ungated_key_injections(_UNGATED)
    assert violations, "planted defect (no auth_request) was not detected"
    assert "no auth_request directive" in violations[0]


def test_self_auth_request_to_a_non_internal_location_is_detected() -> None:
    """auth_request must point at an `internal;` location, not just exist."""
    violations = find_ungated_key_injections(_AUTH_REQUEST_TARGETS_NON_INTERNAL_LOCATION)
    assert violations, "planted defect (auth_request to a non-internal location) was not detected"
    assert "internal" in violations[0]


def test_self_properly_gated_location_passes() -> None:
    """The detector must not flag the shape #16374 actually ships."""
    assert find_ungated_key_injections(_PROPERLY_GATED) == []
