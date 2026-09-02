# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every resolvable SLM-frontend API call names a route its service serves (#15236 AC5).

This is the fifth instance of one class of defect — #15198, #15199, #15230, #15236,
#15533 — a frontend that calls a path no router mounts. The button works, the modal
opens, the request 404s, and the caller swallows it.

**Why the obvious guard does not work.** The generated OpenAPI contract is the natural
oracle and it is not sufficient on its own, for two measured reasons:

1. *It omits WebSocket routes.* FastAPI does not put `@router.websocket` handlers in
   `openapi.json`. Checked against the contract alone, this sweep reports 2 genuinely
   served SLM WebSocket paths as unserved — `/api/ws/nodes/{node_id}`
   (`components/fleet/NodeLifecyclePanel.vue`) and `/api/ws/events`
   (`views/settings/APISettings.vue`). So the served set is the contract **unioned with
   the WebSocket routes parsed out of the backend package**.

2. *A path literal alone does not say which service it reaches.* The SLM frontend talks
   to two backends. `getSlmApiBase()` resolves to the SLM; `getBackendUrl()` resolves to
   `/autobot-api`, which the deployed nginx template proxies to the **main** backend's
   `/api/`. `/api/terminal/execute` is served by the main backend (it is in the
   2195-path main contract) and is *not* served by the SLM (0 of its 305 paths are under
   `/api/terminal/`). A guard that checks path literals against one contract cannot tell
   those apart; the previous attempt at this measured 39 false positives that way and was
   deferred rather than shipped.

**So resolution is per call site, and a call site that cannot be resolved is skipped.**
Two things are resolvable and nothing else is:

* a template literal whose leading interpolations include `getSlmApiBase()`,
  `getBackendUrl()`, or a local `const` bound to one of them; and
* a method call on a receiver whose base URL is known in the same file — the
  `slmApiClient` singleton (SLM), or an `axios.create({ baseURL: ... })` instance.

Anything else — a path assembled by string addition, an interpolation that is only part
of a segment (`/cache/clear${params}`, where `params` is a query string), a client whose
base is passed in — is counted as unresolved and asserted on by nothing. Precision is
worth more than reach here: a guard that reddens CI on a path it guessed wrong is worse
than no guard, because the next person deletes it.

**Matching is deliberately permissive in one direction.** A contract `{param}` matches
any call segment, and a call-site `${...}` matches any contract segment. The second half
costs recall: `/api/settings/${section}` is treated as served because the contract has
`/api/settings/backend`, even though a bad `section` would 404. Tightening it — call
params matching only contract params — was measured and flags 35 sites instead of 30,
and 2 of those 5 extra are false: `/api/settings/${section}` really is served, for every
value `section` takes. 0 false positives with known blind spots beats 5.7% false
positives with better reach.

**The baseline is exact and shrink-only**, like
`repo_tests/python_file_size_ratchet_baseline.py`. Every entry is a call that is broken
today, with the issue that fixes it. Removing one without doing the work fails, and so
does doing the work without removing the entry.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SLM_SRC = _REPO_ROOT / "autobot-slm-frontend" / "src"

_SERVICES = {
    "slm": (
        _REPO_ROOT / "autobot-slm-frontend" / "src" / "types" / "generated" / "api.ts",
        _REPO_ROOT / "autobot-slm-backend",
    ),
    "main": (
        _REPO_ROOT / "autobot-frontend" / "src" / "types" / "generated" / "api.ts",
        _REPO_ROOT / "autobot-backend",
    ),
}

# Lower when a sweep genuinely covers less; never lower it to make a red run pass.
# Measured on Dev_new_gui at the time of writing: 126 resolved, 8 unresolved-and-skipped.
_RESOLVED_FLOOR = 115

# (repo-relative file, service, normalised path) — exact, shrink-only.
# #15536 covers every `useAutobotApi.ts` entry; #15236/#15230 covers the terminal one.
_KNOWN_UNSERVED = frozenset(
    {
        ("autobot-slm-frontend/src/composables/useAutobotApi.ts", "main", p)
        for p in (
            "/api/agents",
            "/api/batch/status",
            "/api/files/write",
            "/api/llm-providers/fallback-status",
            "/api/mcp/servers",
            "/api/mcp/servers/{param}",
            "/api/mcp/servers/{param}/restart",
            "/api/mcp/servers/{param}/start",
            "/api/mcp/servers/{param}/stop",
            "/api/monitoring/hardware",
            "/api/monitoring/system",
            "/api/npu-workers",
            "/api/npu-workers/load-balancing/config",
            "/api/npu-workers/{param}",
            "/api/npu-workers/{param}/pair",
            "/api/npu-workers/{param}/restart",
            "/api/npu-workers/{param}/test",
            "/api/permissions/rules/{param}",
            "/api/users",
            "/api/users/{param}",
            "/api/voice/config",
        )
    }
    | {("autobot-slm-frontend/src/views/tools/admin/TerminalTool.vue", "slm", "/api/terminal/ws/ssh")}
)

_VERBS = "get|post|put|patch|delete"
_WHOLE_SEGMENT = re.compile(r"^\$\{[^{}]*\}$")


def _contract_paths(contract: Path) -> set[str]:
    """Return the path keys of an `openapi-typescript` generated `paths` interface."""
    source = contract.read_text(encoding="utf-8")
    block = re.search(r"export interface paths \{(.*?)\n\}\n", source, re.S)
    if block is None:
        return set()
    return set(re.findall(r'^    "([^"]+)":', block.group(1), re.M))


def _websocket_routes(package: Path) -> set[str]:
    """Return `/api`-prefixed WebSocket routes the OpenAPI contract leaves out."""
    routes: set[str] = set()
    for module in package.rglob("*.py"):
        text = module.read_text(encoding="utf-8", errors="ignore")
        if ".websocket(" not in text:
            continue
        routers = re.findall(r"APIRouter\(([^)]*)\)", text, re.S)
        if len(routers) != 1:
            continue  # cannot say which router carries the handler
        prefix = re.search(r'prefix="([^"]*)"', routers[0])
        if prefix is None:
            continue  # cannot say where the router is mounted
        for route in re.findall(r'@(?:router|app)\.websocket\(\s*"([^"]*)"', text):
            routes.add("/api" + prefix.group(1) + route)
    return routes


@lru_cache(maxsize=None)
def _served(service: str) -> frozenset[str]:
    """Return the paths *service* serves: its contract plus its WebSocket routes."""
    contract, package = _SERVICES[service]
    return frozenset(_contract_paths(contract) | _websocket_routes(package))


def _segments(path: str) -> list[str]:
    return [segment for segment in path.split("/") if segment]


def _reaches(path: str, service: str, is_prefix: bool) -> bool:
    """True when *path* matches a route *service* serves, `{...}` matching one segment."""
    call = _segments(path)
    for route in _served(service):
        served = _segments(route)
        if is_prefix:
            if len(served) < len(call):
                continue
            served = served[: len(call)]
        elif len(served) != len(call):
            continue
        if all(a.startswith("{") or b == "{param}" or a == b for a, b in zip(served, call)):
            return True
    return False


def _normalise(literal: str) -> tuple[str, bool] | None:
    """Return (`/api`-prefixed path, is_prefix), or None when the literal is unresolvable."""
    raw = literal.split("?")[0].split("#")[0]
    if not raw.startswith("/"):
        return None
    out: list[str] = []
    for segment in _segments(raw):
        if _WHOLE_SEGMENT.match(segment):
            out.append("{param}")
        elif "${" in segment or "+" in segment:
            return None  # partial interpolation: the segment is not a path segment
        else:
            out.append(segment)
    path = "/" + "/".join(out)
    if not path.startswith("/api"):
        path = "/api" + path
    return path, raw.endswith("/") and raw != "/"


def _bases(text: str) -> dict[str, str]:
    """Map local `const` names bound to a base-URL helper to their service."""
    pattern = r"const\s+(\w+)\s*=\s*(getSlmApiBase|getBackendUrl)\(\)"
    return {
        match.group(1): ("slm" if match.group(2) == "getSlmApiBase" else "main")
        for match in re.finditer(pattern, text)
    }


def _receivers(text: str) -> dict[str, str]:
    """Map HTTP-client identifiers in *text* to the service their base URL reaches."""
    found: dict[str, str] = {}
    if re.search(r"import\s*\{[^}]*\bslmApiClient\b[^}]*\}\s*from\s*'[^']*ApiClient'", text):
        found["slmApiClient"] = "slm"
    axios_create = r"(?:const|let)\s+(\w+)[^=\n]*=\s*axios\.create\(\{[^}]*baseURL:\s*(getSlmApiBase|getBackendUrl)\(\)"
    for match in re.finditer(axios_create, text, re.S):
        found[match.group(1)] = "slm" if match.group(2) == "getSlmApiBase" else "main"
    return found


def _template_pattern(bases: dict[str, str]) -> re.Pattern[str]:
    """Match a template literal whose leading interpolations name a base-URL helper."""
    heads = [r"getSlmApiBase\(\)", r"getBackendUrl\(\)"] + [re.escape(name) for name in bases]
    return re.compile(r"`(?:\$\{[^{}]*\})*\$\{(" + "|".join(heads) + r")\}([^`]*)`")


def _call_pattern(receivers: dict[str, str]) -> re.Pattern[str] | None:
    """Match `<client>.<verb>('<literal>'` for the clients resolved in this file."""
    if not receivers:
        return None
    names = "|".join(re.escape(name) for name in receivers)
    return re.compile(
        r"\b(" + names + r")\.(?:" + _VERBS + r")(?:<[^>(]*>)?\(\s*(['\"`])([^'\"`]*)\2"
    )


def _service_of(head: str, bases: dict[str, str]) -> str:
    if head == "getSlmApiBase()":
        return "slm"
    if head == "getBackendUrl()":
        return "main"
    return bases[head]


def _sites_in(path: Path) -> list[tuple[str, int, str, str, bool]]:
    """Return every resolvable (file, line, service, path, is_prefix) call site in *path*."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    relative = path.relative_to(_REPO_ROOT).as_posix()
    bases, receivers = _bases(text), _receivers(text)
    template, call = _template_pattern(bases), _call_pattern(receivers)
    found: list[tuple[str, int, str, str, bool]] = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in template.finditer(line):
            resolved = _normalise(match.group(2))
            if resolved is not None:
                found.append((relative, number, _service_of(match.group(1), bases), *resolved))
        for match in call.finditer(line) if call else ():
            resolved = _normalise(match.group(3))
            if resolved is not None:
                found.append((relative, number, receivers[match.group(1)], *resolved))
    return found


@lru_cache(maxsize=None)
def _call_sites() -> tuple[tuple[str, int, str, str, bool], ...]:
    """Every resolvable API call site in the SLM frontend's shipped source."""
    files = sorted(
        candidate
        for pattern in ("*.ts", "*.vue")
        for candidate in _SLM_SRC.rglob(pattern)
        if ".test." not in candidate.name and ".spec." not in candidate.name
    )
    return tuple(site for path in files for site in _sites_in(path))


def _assert_population_floor() -> tuple[tuple[str, int, str, str, bool], ...]:
    """Guard the sweep itself: a collapsed population must fail by name, not read clean."""
    sites = _call_sites()
    assert len(sites) >= _RESOLVED_FLOOR, (
        f"FIX THE SWEEP: resolved only {len(sites)} SLM-frontend call sites, "
        f"floor is {_RESOLVED_FLOOR}. The extractor stopped matching, so a clean "
        "result here means nothing. Fix the sweep before touching the floor."
    )
    return sites


def _unserved() -> set[tuple[str, str, str]]:
    return {
        (relative, service, path)
        for relative, _line, service, path, is_prefix in _assert_population_floor()
        if not _reaches(path, service, is_prefix)
    }


def test_the_sweep_still_resolves_a_population_worth_asserting_on() -> None:
    """The floor fires on its own, so a collapsed sweep is named rather than green."""
    assert len(_assert_population_floor()) >= _RESOLVED_FLOOR


def test_both_services_contribute_routes_including_websockets() -> None:
    """A served set missing WebSocket routes reports served paths as unserved."""
    _assert_population_floor()
    assert len(_served("slm")) > 300, "SLM served set collapsed — the contract did not parse"
    assert len(_served("main")) > 2000, "main served set collapsed — the contract did not parse"
    assert "/api/ws/events" in _served("slm"), "SLM WebSocket routes are missing from the oracle"
    assert "/api/terminal/execute" in _served("main"), "main contract did not parse"
    assert not any(p.startswith("/api/terminal/") for p in _served("slm"))


def test_every_resolved_call_site_reaches_a_route_its_service_serves() -> None:
    """The substantive assertion — evaluated only after the population floor holds."""
    _assert_population_floor()
    new = sorted(_unserved() - _KNOWN_UNSERVED)
    assert not new, (
        "SLM-frontend call sites name routes their service does not serve:\n"
        + "\n".join(f"  {f} -> [{service}] {path}" for f, service, path in new)
        + "\n\nEither point the call at a served route, or build the route. Do not add "
        "it to _KNOWN_UNSERVED: that baseline only shrinks."
    )


def test_the_known_unserved_baseline_is_exact() -> None:
    """Fails in both directions: unrecorded growth, and a fix that leaves its entry behind."""
    _assert_population_floor()
    fixed = sorted(_KNOWN_UNSERVED - _unserved())
    assert not fixed, (
        "These baseline entries no longer name an unserved route. Remove them from "
        "_KNOWN_UNSERVED in the commit that fixed them:\n"
        + "\n".join(f"  {f} -> [{service}] {path}" for f, service, path in fixed)
    )
