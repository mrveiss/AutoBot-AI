# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Ratchet: outbound HTTP calls that carry no egress policy only go down (#17576, AC4).

The earlier enforcement (``knowledge/connectors/egress_policy_test.py``) counted a literal
five-file population, so a call site it was not told about was invisible. This guard
**enumerates**: every tracked non-test ``*.py`` is swept by ``repo_tests/_egress_default.py`` and
each outbound call is classified guarded or unguarded.

Guarded means, on a manager call, ``guard_egress=`` of ``EGRESS_POLICY``, the literal ``False`` or a
canonical policy value from the egress modules (never ``True``, ``None`` or an arbitrary variable); on
a raw client, an earlier ``assert_egress_policy(<the request's URL>)`` in the same function AND
redirects refused (literal ``allow_redirects=False``; httpx unless it opts in; a websocket handshake;
never ``urlopen``). The unguarded population as of
today is recorded in ``egress_unguarded_baseline_17576.json`` (path -> count). The ratchet runs in
both directions: a count above its baseline, or a new path, fails; a count *below* its baseline also
fails, with the instruction to lower it, so the baseline only drops and never carries slack.

Scope: tracked ``*.py`` excluding tests, fixtures, archives, ``docs/`` and ``repo_tests/``, and the
two files that implement the guard (``http_client_manager.py``, ``security/ssrf_guard.py``).
Library-mediated egress the detector cannot see is declared in ``autobot_shared/declared_egress.py``.

Refs #17576, #18229.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from repo_tests._egress_default import outbound_sites, scan_paths
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.declared_egress import DECLARED_EGRESS
from tools.lint._scan_helpers import tracked_paths

UNPARSED = "(UNPARSED)"
BASELINE_FILE = Path(__file__).with_name("egress_unguarded_baseline_17576.json")

#: Implementations of the guard itself -- they construct and drive the session on purpose.
#: The sticky-comment composite action (#12984) is exempt too: it runs on a bare runner with the standard
#: library only (so it cannot import the guard, and ``urlopen`` can never be marked guarded), and it talks
#: only to the runner's own GitHub API root with the job token -- never a user-, LLM- or document-supplied URL.
EXEMPT = frozenset(
    {
        "autobot_shared/http_client_manager.py",
        "autobot_shared/security/ssrf_guard.py",
        ".github/actions/upsert-pr-comment/upsert_pr_comment.py",
    }
)
_SKIP_DIRS = frozenset({"tests", "test", "fixtures", "node_modules", "__pycache__"})
_SKIP_PREFIXES = ("docs/", "repo_tests/")


def _in_scope(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    if path in EXEMPT or path.startswith(_SKIP_PREFIXES):
        return False
    if any(p in _SKIP_DIRS or "archive" in p for p in parts[:-1]):
        return False
    return not (name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py")


def scoped_paths(root: Path) -> list[str]:
    """Tracked, non-test python paths; ``[]`` on a tree git cannot enumerate (the floor then fires)."""
    try:
        return [p for p in tracked_paths(root, "*.py") if _in_scope(p)]
    except RuntimeError:
        return []


def census_by_path(root: Path) -> dict[str, dict[str, int]]:
    """Path -> ``{detected, declared}``: AST-detected calls plus declared library-mediated egress."""
    census = {p: {"detected": len(sites), "declared": 0} for p, sites in scan_paths(root, scoped_paths(root)).items()}
    for entry in DECLARED_EGRESS:
        if not (root / entry.path).is_file():
            continue  # an empty/other tree: the declared entry is not part of ITS census
        census.setdefault(entry.path, {"detected": 0, "declared": 0})["declared"] += 1
    return census


def _files_with_outbound_calls(root: Path) -> list[str]:
    try:
        return sorted(census_by_path(root))
    except FileNotFoundError:
        return []


def _site_total(root: Path) -> int:
    return sum(c["detected"] + c["declared"] for c in census_by_path(root).values())


#: Measured on origin/main at 497f439b46: 468 outbound calls in 186 files plus 2 declared (baseline 454 unguarded in 175 paths). ``roots`` lists every
#: top-level tree the sweep reaches; a new top-level tree with an outbound call fails the scope check
#: loudly (widen it) rather than being swept silently outside the declared scope.
REACH = declare(
    "egress-default-outbound-call-sweep",
    discover=_files_with_outbound_calls,
    floor=150,
    growth=60,
    what="python files making outbound HTTP calls",
    roots=("autobot-", "autobot_shared/", "debug/", "plugins/", "scripts/", "pipeline-scripts/"),
)


def _outbound_call_sites(root: Path) -> list[str]:
    """One id per outbound call SITE (detected + declared), so the population is the site total."""
    return [f"{p}#{i}" for p, c in census_by_path(root).items() for i in range(c["detected"] + c["declared"])]


#: Outbound call SITES (not files) the sweep must find -- the files floor alone cannot see a detector
#: that lost a client kind but still finds one call per file. Migrated from a hand-rolled
#: ``SITE_FLOOR = 400`` (#16147); pinned mid-window from the measured population.
SITES = declare(
    "egress-default-outbound-call-sites",
    discover=_outbound_call_sites,
    floor=443,  # measured: 473 sites, window [413, 473]
    growth=60,
    what="outbound HTTP call sites (detected + declared) in the egress sweep",
    roots=("autobot-", "autobot_shared/", "debug/", "plugins/", "scripts/", "pipeline-scripts/"),
)


def unguarded_counts(root: Path) -> dict[str, int]:
    """Path -> number of outbound calls with no egress policy, for paths with at least one."""
    counts = {p: sum(1 for s in sites if not s.guarded) for p, sites in scan_paths(root, scoped_paths(root)).items()}
    # an unparsable file has no sites, which would read as clean: surface it as one unguarded entry
    return {p: n or 1 if UNPARSED in p else n for p, n in counts.items() if n or UNPARSED in p}


def load_baseline() -> dict[str, int]:
    return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))


def ratchet_verdict(found: dict[str, int], baseline: dict[str, int]) -> tuple[list[str], list[str]]:
    """(grew-or-new, shrank-or-gone) messages. Both lists empty means the baseline is exact."""
    worse = [
        f"{p}: {found[p]} unguarded, baseline {baseline.get(p, 0)}"
        for p in sorted(found)
        if found[p] > baseline.get(p, 0)
    ]
    better = [
        f"{p}: baseline {baseline[p]}, now {found.get(p, 0)}" for p in sorted(baseline) if found.get(p, 0) < baseline[p]
    ]
    return worse, better


# --- the instrument, before any count it produces is read --------------------

_POLICY_IMPORT = "from autobot_shared.http_egress_guard import EGRESS_POLICY, assert_egress_policy\n"
_CONNECTOR_IMPORT = (
    "from knowledge.connectors.base import VENDOR_API_EGRESS, CONTENT_URL_EGRESS, instance_host_egress\n"
)

_FIXTURES_UNGUARDED = {
    "manager": "async def f(u):\n    return await get_http_client().tracked_request('GET', u)\n",
    "manager-none": "async def f(u):\n    return await http_client.get_json(u, guard_egress=None)\n",
    "manager-true": "async def f(u):\n    return await http_client.get_json(u, guard_egress=True)\n",
    "manager-variable": "async def f(u, g):\n    return await http_client.get_json(u, guard_egress=g)\n",
    "manager-kwargs": "async def f(u, **kw):\n    return await http_client.get_json(u, **kw)\n",
    "manager-shadowed-policy": "VENDOR_API_EGRESS = True\nasync def f(u):\n    return await http_client.get_json(u, guard_egress=VENDOR_API_EGRESS)\n",
    "manager-bound": "async def f(u):\n    c = get_http_client()\n    return await c.get(u)\n",
    "session": "import aiohttp\nasync def f(session, u):\n    return await session.get(u)\n",
    "session-with": "import aiohttp\nasync def f(u):\n    async with aiohttp.ClientSession() as http:\n        return await http.post(u)\n",
    "session-from-import": (
        "from aiohttp import ClientSession as CS\nasync def f(u):\n    s = CS()\n    return await s.get(u)\n"
    ),
    "session-tracked": (
        "async def f(u):\n    async with get_http_client().tracked_session() as sess:\n        return await sess.get(u)\n"
    ),
    "httpx": "import httpx\nasync def f(u):\n    return await httpx.AsyncClient().get(u)\n",
    "httpx-with": "import httpx\nasync def f(u):\n    async with httpx.AsyncClient() as ac:\n        return await ac.get(u)\n",
    "httpx-module-call": "import httpx\ndef f(u):\n    return httpx.get(u)\n",
    "requests": "import requests\ndef f(u):\n    return requests.get(u)\n",
    "requests-alias": "import requests as r\ndef f(u):\n    return r.post(u)\n",
    "requests-session": "import requests\ndef f(u):\n    s = requests.Session()\n    return s.get(u)\n",
    "requests-from-import": "from requests import get as g\ndef f(u):\n    return g(u)\n",
    "urllib": "import urllib.request\ndef f(u):\n    return urllib.request.urlopen(u)\n",
    "urllib-alias": "from urllib.request import urlopen as uo\ndef f(u):\n    return uo(u)\n",
    "getattr": "import aiohttp\nasync def f(session, u):\n    return await getattr(session, 'get')(u)\n",
    "partial": "import aiohttp, functools\nasync def f(session, u):\n    return functools.partial(session.get, u)\n",
    "bound-method": "import aiohttp\nasync def f(session, u):\n    g = session.get\n    return await g(u)\n",
    "raw-policy-redirects-default": (
        _POLICY_IMPORT + "import aiohttp\nasync def f(session, u):\n    await assert_egress_policy(u)\n"
        "    return await session.get(u)\n"
    ),
    "raw-policy-redirects-true": (
        _POLICY_IMPORT + "import aiohttp\nasync def f(session, u):\n    await assert_egress_policy(u)\n"
        "    return await session.get(u, allow_redirects=True)\n"
    ),
    "requests-policy-redirects-default": (
        _POLICY_IMPORT + "import requests\nasync def f(u):\n    await assert_egress_policy(u)\n"
        "    return requests.get(u)\n"
    ),
    "httpx-follow-redirects-true": (
        _POLICY_IMPORT + "import httpx\nasync def f(u):\n    await assert_egress_policy(u)\n"
        "    return httpx.get(u, follow_redirects=True)\n"
    ),
    "httpx-client-follows-redirects": (
        _POLICY_IMPORT + "import httpx\nasync def f(u):\n    await assert_egress_policy(u)\n"
        "    async with httpx.AsyncClient(follow_redirects=True) as ac:\n        return await ac.get(u)\n"
    ),
    "urlopen-policy-never-guards": (
        _POLICY_IMPORT + "import urllib.request\ndef f(u):\n    await assert_egress_policy(u)\n"
        "    return urllib.request.urlopen(u)\n"
    ),
    "websocket": "import websockets\nasync def f(u):\n    return websockets.connect(u)\n",
    "ws-no-redirect": (
        "from autobot_shared.ws_no_redirect import connect_no_redirect\nasync def f(u):\n    return connect_no_redirect(u)\n"
    ),
    "ws-no-redirect-alias": (
        "from autobot_shared.ws_no_redirect import connect_no_redirect as c\nasync def f(u):\n    return c(u)\n"
    ),
    "ws-no-redirect-class-attr": (
        "from autobot_shared import ws_no_redirect as w\nasync def f(u):\n    return w.NoRedirectConnect(u)\n"
    ),
    "websocket-asserted-but-follows-redirects": (
        _POLICY_IMPORT + "import websockets\nasync def f(u):\n    await assert_egress_policy(u)\n"
        "    return websockets.connect(u)\n"
    ),
    "conditional-policy-with-a-bool-arm": (
        "from knowledge.connectors.egress import instance_host_egress\n"
        "async def f(u, a):\n    return await http_client.get_json(u, guard_egress=instance_host_egress() if a else True)\n"
    ),
    "websocket-alias": "from websockets.asyncio.client import connect as wsc\nasync def f(u):\n    return wsc(u)\n",
    "websocket-client-attr": "import websockets.client\nasync def f(u):\n    return websockets.client.connect(u)\n",
    "attr-policy-from-base-module": (
        "from knowledge.connectors import base as g\n"
        "async def f(u):\n    return await http_client.get_json(u, guard_egress=g.VENDOR_API_EGRESS)\n"
    ),
    "attr-policy-unbound-receiver": (
        "async def f(u):\n    return await http_client.get_json(u, guard_egress=other.EGRESS_POLICY)\n"
    ),
    "raw-policy-other-url": (
        _POLICY_IMPORT + "import aiohttp\nasync def f(session, u):\n    await assert_egress_policy('https://x.test')\n"
        "    return await session.get(u)\n"
    ),
    "raw-policy-nested-def": (
        _POLICY_IMPORT
        + "import aiohttp\nasync def f(session, u):\n    async def g():\n        await assert_egress_policy(u)\n"
        "    return await session.get(u)\n"
    ),
    "raw-policy-module-level": (
        _POLICY_IMPORT + "import aiohttp\nasync def a(u):\n    await assert_egress_policy(u)\n"
        "async def b(session, u):\n    return await session.get(u)\n"
    ),
    "raw-policy-after": (
        _POLICY_IMPORT + "import aiohttp\nasync def f(session, u):\n    r = await session.get(u)\n"
        "    await assert_egress_policy(u)\n    return r\n"
    ),
}

_FIXTURES_GUARDED = {
    "manager-false": "async def f(u):\n    return await get_http_client().tracked_request('GET', u, guard_egress=False)\n",
    "manager-policy": (
        _POLICY_IMPORT + "async def f(u):\n    return await http_client.post_json(u, guard_egress=EGRESS_POLICY)\n"
    ),
    "manager-vendor": (
        _CONNECTOR_IMPORT
        + "async def f(u):\n    return await http_client.get_json(u, guard_egress=VENDOR_API_EGRESS)\n"
    ),
    "manager-content": (
        _CONNECTOR_IMPORT
        + "async def f(u):\n    return await http_client.get_json(u, guard_egress=CONTENT_URL_EGRESS)\n"
    ),
    "manager-instance": (
        _CONNECTOR_IMPORT
        + "async def f(u):\n    return await http_client.get_json(u, guard_egress=instance_host_egress())\n"
    ),
    "raw-after-policy": (
        _POLICY_IMPORT + "import aiohttp\nasync def f(session, u):\n    await assert_egress_policy(u)\n"
        "    return await session.get(u, allow_redirects=False)\n"
    ),
    "raw-after-policy-request": (
        _POLICY_IMPORT + "import aiohttp\nasync def f(session, u):\n    await assert_egress_policy(u)\n"
        "    return await session.request('GET', u, allow_redirects=False)\n"
    ),
    "httpx-default-no-redirect": (
        _POLICY_IMPORT + "import httpx\nasync def f(c, u):\n    await assert_egress_policy(u)\n"
        "    async with httpx.AsyncClient() as ac:\n        return await ac.get(u)\n"
    ),
    "httpx-explicit-false": (
        _POLICY_IMPORT + "import httpx\ndef f(u):\n    await assert_egress_policy(u)\n"
        "    return httpx.get(u, follow_redirects=False)\n"
    ),
    "requests-no-redirect": (
        _POLICY_IMPORT + "import requests\nasync def f(u):\n    await assert_egress_policy(u)\n"
        "    return requests.get(u, allow_redirects=False)\n"
    ),
    "public-only-raw-session": (
        "import aiohttp\nfrom autobot_shared.http_egress_guard import assert_public_egress\n"
        "async def f(u):\n    await assert_public_egress(u)\n"
        "    async with aiohttp.ClientSession() as s:\n        return await s.get(u, allow_redirects=False)\n"
    ),
    "ws-no-redirect": (
        _POLICY_IMPORT + "from autobot_shared.ws_no_redirect import connect_no_redirect\n"
        "async def f(u):\n    await assert_egress_policy(u)\n    return connect_no_redirect(u)\n"
    ),
    "conditional-policy-both-arms-canonical": (
        "from knowledge.connectors.egress import CONTENT_URL_EGRESS, instance_host_egress\n"
        "async def f(u, a):\n    return await http_client.get_json(\n"
        "        u, guard_egress=instance_host_egress() if a else CONTENT_URL_EGRESS\n    )\n"
    ),
    "wrapper-inner-call-literal-policy": (
        "from knowledge.connectors.egress import VENDOR_API_EGRESS\n"
        "def _vendor_request(method, url, **kw):\n"
        "    return get_http_client().tracked_request(method, url, guard_egress=VENDOR_API_EGRESS, **kw)\n"
    ),
    "attr-policy-from-egress-module": (
        "from autobot_shared import http_egress_guard as g\n"
        "async def f(u):\n    return await http_client.get_json(u, guard_egress=g.EGRESS_POLICY)\n"
    ),
}


@pytest.mark.parametrize("name", sorted(_FIXTURES_UNGUARDED))
def test_each_client_kind_is_detected_as_unguarded(name: str) -> None:
    sites = outbound_sites(_FIXTURES_UNGUARDED[name])
    assert len(sites) == 1 and not sites[0].guarded, f"{name}: {sites}"


@pytest.mark.parametrize("name", sorted(_FIXTURES_GUARDED))
def test_guarded_forms_count_as_guarded(name: str) -> None:
    sites = outbound_sites(_FIXTURES_GUARDED[name])
    assert len(sites) == 1 and sites[0].guarded, f"{name}: {sites}"


_IN_PROCESS = (
    "import httpx\nasync def f(app, p):\n"
    "    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:\n"
    "        return await c.get(p)\n"
)


def test_an_in_process_asgi_client_is_not_an_outbound_call() -> None:
    """#18765: ``ASGITransport`` opens no socket; the same client over the network is still flagged."""
    assert outbound_sites(_IN_PROCESS) == ()
    network = _IN_PROCESS.replace("transport=httpx.ASGITransport(app=app), ", "")
    sites = outbound_sites(network)
    assert len(sites) == 1 and not sites[0].guarded, "contrast: a network httpx client must still be detected"


@pytest.mark.parametrize("name", ["client", "http_client"])
def test_an_in_process_client_is_not_flagged_by_its_receiver_name(name: str) -> None:
    """The binding is honoured before the name fallbacks (``client``) and the manager-name match (``http_client``)."""
    named = _IN_PROCESS.replace(" as c:", f" as {name}:").replace("c.get(p)", f"{name}.get(p)")
    assert named != _IN_PROCESS
    assert outbound_sites(named) == ()
    network = named.replace("transport=httpx.ASGITransport(app=app), ", "")
    assert len(outbound_sites(network)) == 1, "contrast: the same name over the network is still detected"


def test_an_asgi_client_with_network_mounts_is_still_an_outbound_call() -> None:
    """``mounts=`` sends matching URLs to a network transport, so the exemption does not apply."""
    mounted = _IN_PROCESS.replace(
        "transport=httpx.ASGITransport(app=app), ",
        "transport=httpx.ASGITransport(app=app), mounts={'https://': httpx.AsyncHTTPTransport()}, ",
    )
    assert mounted != _IN_PROCESS
    sites = outbound_sites(mounted)
    assert len(sites) == 1 and not sites[0].guarded


def test_known_live_misses_are_now_found() -> None:
    """The review's three live misses: an aliased session under ``with`` and an httpx client."""
    found = scan_paths(repo_root(), ["autobot-backend/api/provider_auth.py", "autobot-backend/content_reach/_http.py"])
    # By kind, not line number: a line pin breaks on every unrelated edit to the file (#17576).
    assert [s.kind for s in found["autobot-backend/api/provider_auth.py"]] == ["session", "session"]
    assert 68 in {s.lineno for s in found["autobot-backend/content_reach/_http.py"]}


def test_declared_registry_is_part_of_the_census() -> None:
    census = census_by_path(repo_root())
    for entry in DECLARED_EGRESS:
        assert census[entry.path]["declared"] >= 1, entry
    assert sum(c["declared"] for c in census.values()) == len(DECLARED_EGRESS)


def test_the_sweep_reaches_a_known_outbound_caller() -> None:
    """A known positive, so an empty sweep cannot read as a clean tree."""
    found = scan_paths(repo_root(), ["autobot-backend/knowledge/connectors/jira.py"])
    assert found, "jira.py makes tracked_request calls; the detector found nothing"


def test_the_sweep_population_floors() -> None:
    assert len(REACH.examined(repo_root())) >= REACH.floor
    assert len(SITES.examined(repo_root())) >= SITES.floor, "the detector found implausibly few outbound calls"


# --- the ratchet --------------------------------------------------------------


def test_no_unparsable_file_hides_in_the_census_or_baseline() -> None:
    bad = [p for p in list(unguarded_counts(repo_root())) + list(load_baseline()) if UNPARSED in p]
    assert not bad, f"file(s) the detector could not parse -- an unparsed file reads as clean, fix the source: {bad}"


def test_unparsed_file_is_surfaced_not_dropped(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("import requests\ndef f(:\n", encoding="utf-8")
    counts = {p: 1 for p in scan_paths(tmp_path, ["broken.py"])}
    assert list(counts) == ["broken.py (UNPARSED)"]


def test_baseline_is_well_formed() -> None:
    baseline = load_baseline()
    assert baseline and all(isinstance(n, int) and n > 0 for n in baseline.values())
    assert all(_in_scope(p) for p in baseline), "baseline names an out-of-scope path"


def test_unguarded_outbound_calls_only_go_down() -> None:
    worse, better = ratchet_verdict(unguarded_counts(repo_root()), load_baseline())
    assert not worse, (
        "Outbound HTTP call(s) without an egress policy (#17576, rule 8). Pass "
        "guard_egress=EGRESS_POLICY (autobot_shared.http_egress_guard) on the manager call, or "
        "`await assert_egress_policy(url)` before a raw client call (a user-, LLM- or document-supplied URL: "
        "guard_egress=False, or `await assert_public_egress(url)`). Do NOT raise the baseline.\n  " + "\n  ".join(worse)
    )
    assert not better, (
        "Unguarded calls were removed but the baseline still records them. Lower the entries in "
        "repo_tests/egress_unguarded_baseline_17576.json so the next author inherits the true "
        "number, not slack.\n  " + "\n  ".join(better)
    )


def test_ratchet_verdict_contrast() -> None:
    assert ratchet_verdict({"a.py": 3}, {"a.py": 2}) == (["a.py: 3 unguarded, baseline 2"], [])
    assert ratchet_verdict({"b.py": 1}, {}) == (["b.py: 1 unguarded, baseline 0"], [])
    assert ratchet_verdict({"a.py": 1}, {"a.py": 2}) == ([], ["a.py: baseline 2, now 1"])
    assert ratchet_verdict({}, {"a.py": 2}) == ([], ["a.py: baseline 2, now 0"])
    assert ratchet_verdict({"a.py": 2}, {"a.py": 2}) == ([], [])


if __name__ == "__main__":  # regenerate: python3 -m repo_tests.egress_default_guard_17576_test
    data = dict(sorted(unguarded_counts(repo_root()).items()))
    BASELINE_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(data)} paths, {sum(data.values())} unguarded calls")
