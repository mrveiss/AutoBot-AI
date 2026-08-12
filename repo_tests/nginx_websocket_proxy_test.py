# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Every ``@router.websocket`` route must upgrade through the nginx proxy (#13604).

A WebSocket-only route reached over plain HTTP gets a 404 from Starlette, because
there is no HTTP handler on it.  So when nginx forwards the handshake without the
``Upgrade``/``Connection`` headers, the browser sees ``404`` and blames the
backend — while the route itself is perfectly fine and answers ``101`` when
called directly.

That shipped three times (#1144, #1460, #13604).  Each was closed by appending
one more ``location`` block to a hand-maintained allowlist, so the next route
added broke exactly the same way.  These tests encode the invariant the allowlist
was standing in for: *the block nginx actually selects for a WebSocket path sets
the upgrade headers*, whichever block that turns out to be.

The tests are static — they read the Jinja templates and the route decorators.
No nginx and no running backend is involved, so they hold in CI.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "autobot-backend"
REGISTRY_DIR = BACKEND / "initialization" / "router_registry"

# app_factory.py:77 mounts every registry router as f"/api{prefix}".
API_MOUNT = "/api"

TEMPLATES = (
    "autobot-slm-backend/ansible/roles/frontend/templates/nginx-frontend.conf.j2",
    "autobot-slm-backend/ansible/roles/backend/templates/nginx-backend.conf.j2",
    "autobot-slm-backend/ansible/roles/slm_manager/templates/autobot-slm.conf.j2",
)

# The blocks a request falls through to when nothing more specific matches.  If
# these upgrade, a new WebSocket route works without touching nginx at all —
# which is the entire point of #13604.
CATCH_ALL_PREFIXES = ("/api/", "/slm/api/", "/")


def _declares_upgrade(body: str) -> bool:
    return "proxy_set_header Upgrade" in re.sub(r"[ \t]+", " ", body)


class Location:
    """One nginx ``location`` block, reduced to what matching needs.

    *server_sets_upgrade* is the enclosing ``server`` block's answer.  It
    matters because ``proxy_set_header`` is **replace, not merge**: a location
    that declares any ``proxy_set_header`` of its own discards every inherited
    one, and a location that declares none inherits the whole server-level set.
    Modelling that is the difference between reading this config correctly and
    flagging a working ``location /`` that inherits the headers from above.
    """

    def __init__(self, modifier: str, pattern: str, body: str, server_sets_upgrade: bool) -> None:
        self.modifier = modifier
        self.pattern = pattern
        self.body = body
        self.server_sets_upgrade = server_sets_upgrade

    @property
    def proxies(self) -> bool:
        return "proxy_pass" in self.body

    @property
    def sets_upgrade(self) -> bool:
        if "proxy_set_header" in self.body:
            return _declares_upgrade(self.body)
        return self.server_sets_upgrade

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"location {self.modifier} {self.pattern}".replace("  ", " ")


def _strip_jinja(text: str) -> str:
    """Drop Jinja markers, keeping the nginx structure they wrap.

    ``{% if %}``/``{% endif %}`` lines are removed rather than evaluated: a
    conditional block still declares real directives, and for matching purposes
    the conditional arms are all reachable on some host.
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


def _parse_locations(text: str) -> list[Location]:
    """Extract every ``location`` block, tagged with its server's header state.

    Locations are collected per ``server`` block so each one knows whether the
    server above it sets the upgrade headers.
    """
    out: list[Location] = []
    for server in re.finditer(r"\bserver\s*\{", text):
        body = text[server.end() : _block_end(text, server.end()) - 1]
        server_level = re.sub(
            r"location\s+[=~^*]*\s*[^\s{]+\s*\{.*?\n    \}", "", body, flags=re.DOTALL
        )
        out.extend(_locations_in(body, _declares_upgrade(server_level)))
    return out


def _locations_in(body: str, server_sets_upgrade: bool) -> list[Location]:
    """Every ``location`` block directly inside one server body."""
    found: list[Location] = []
    for match in re.finditer(r"location\s+([=~^*]*)\s*([^\s{]+)\s*\{", body):
        end = _block_end(body, match.end())
        found.append(
            Location(
                match.group(1).strip(),
                match.group(2),
                body[match.end() : end - 1],
                server_sets_upgrade,
            )
        )
    return found


def _select(locations: list[Location], path: str) -> Location | None:
    """Pick the block nginx would use for *path*, following its precedence.

    Exact ``=`` wins; then the longest ``^~`` prefix (which suppresses regex);
    then regexes in declaration order; then the longest plain prefix.
    """
    for loc in locations:
        if loc.modifier == "=" and loc.pattern == path:
            return loc
    prefixes = [
        loc for loc in locations if loc.modifier in ("", "^~") and path.startswith(loc.pattern)
    ]
    best = max(prefixes, key=lambda loc: len(loc.pattern), default=None)
    if best is not None and best.modifier == "^~":
        return best
    for loc in locations:
        if loc.modifier.startswith("~") and re.search(loc.pattern, path):
            return loc
    return best


def _registry_prefixes() -> dict[str, str]:
    """Map ``api.<module>`` -> mount prefix from the router registry tuples."""
    prefixes: dict[str, str] = {}
    for path in sorted(REGISTRY_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Tuple) or len(node.elts) < 2:
                continue
            head, prefix = node.elts[0], node.elts[1]
            if not (isinstance(head, ast.Constant) and isinstance(prefix, ast.Constant)):
                continue
            if isinstance(head.value, str) and str(prefix.value).startswith("/"):
                prefixes.setdefault(head.value, prefix.value)
    return prefixes


def _websocket_routes() -> list[tuple[str, str]]:
    """Return ``(source_ref, full_path)`` for every ``@router.websocket`` route."""
    prefixes = _registry_prefixes()
    routes: list[tuple[str, str]] = []
    for module, prefix in sorted(prefixes.items()):
        source = BACKEND / (module.replace(".", "/") + ".py")
        if not source.exists():
            continue
        for lineno, sub in _websocket_decorators(source):
            full = f"{API_MOUNT}{prefix}{sub}".replace("//", "/")
            routes.append((f"{source.relative_to(REPO_ROOT)}:{lineno}", full))
    return routes


def _websocket_decorators(source: Path) -> list[tuple[int, str]]:
    """Every ``@router.websocket("<path>")`` in *source*, as (lineno, path)."""
    found: list[tuple[int, str]] = []
    for match in re.finditer(
        r"@router\.websocket\(\s*[\"']([^\"']+)[\"']", source.read_text(encoding="utf-8")
    ):
        lineno = source.read_text(encoding="utf-8")[: match.start()].count("\n") + 1
        found.append((lineno, match.group(1)))
    return found


def _locations_for(template: str) -> list[Location]:
    path = REPO_ROOT / template
    if not path.exists():  # pragma: no cover - template moved
        pytest.skip(f"{template} not found")
    return _parse_locations(_strip_jinja(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("template", TEMPLATES)
def test_catch_all_proxy_blocks_set_the_upgrade_headers(template: str) -> None:
    """The fall-through blocks must upgrade, so a NEW route needs no nginx edit.

    This is the regression test for the recurring class.  Adding a WebSocket
    route to the backend must not require anyone to remember to add a location
    block; if this passes, forgetting is harmless.
    """
    locations = _locations_for(template)
    catch_alls = [
        loc
        for loc in locations
        if loc.modifier == "" and loc.pattern in CATCH_ALL_PREFIXES and loc.proxies
    ]
    assert catch_alls, f"{template}: no catch-all proxy block found to check"
    missing = [repr(loc) for loc in catch_alls if not loc.sets_upgrade]
    assert not missing, (
        f"{template}: these fall-through blocks do not set 'proxy_set_header Upgrade', "
        f"so any WebSocket route landing in them reaches the backend as a plain GET "
        f"and is answered 404: {missing}"
    )


@pytest.mark.parametrize("template", TEMPLATES)
def test_every_websocket_route_lands_in_an_upgrading_block(template: str) -> None:
    """For each real WS route, the block nginx selects must set the headers.

    Catches the subtler variant of the bug: a regex location beats every prefix
    location, so a route can be shadowed by a block that was never meant to
    handle WebSockets at all.
    """
    locations = _locations_for(template)
    routes = _websocket_routes()
    assert routes, "no @router.websocket routes discovered — the parser is broken"

    broken = []
    for ref, path in routes:
        chosen = _select(locations, path)
        if chosen is None or not chosen.proxies:
            continue  # not served by this vhost
        if not chosen.sets_upgrade:
            broken.append(f"{path} -> {chosen!r} (declared at {ref})")
    assert not broken, (
        f"{template}: these WebSocket routes resolve to a block that strips the "
        f"upgrade, so their handshake returns 404: {broken}"
    )


def test_the_route_parser_finds_the_route_from_the_original_report() -> None:
    """Guard the parser itself: #13604 was reported against /api/quality/ws."""
    paths = {path for _, path in _websocket_routes()}
    assert "/api/quality/ws" in paths, (
        "expected /api/quality/ws (api/analytics_quality.py, mounted at /quality) — "
        f"parser returned {len(paths)} routes"
    )
