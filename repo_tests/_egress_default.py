# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST detector for outbound HTTP calls and whether each carries an egress policy (#17576, AC4).

Separate from the guard that consumes it, for the reason ``_raw_aiohttp_session.py`` gives: the
matcher and the data it is judged against live in different files.

**What counts as an outbound call** (kind in brackets): manager methods on the shared client
(``manager``), session verbs on an aiohttp session (``session``), and the call surface of ``httpx``,
``requests``, ``urllib.request.urlopen`` and ``websockets`` (incl. ``ws_no_redirect.connect_no_redirect``).
Receivers are recognised by name heuristics **and** by
binding: a name bound by ``with ... as X`` or ``X = aiohttp.ClientSession(...)`` /
``httpx.AsyncClient(...)`` / ``requests.Session()`` / ``get_http_client()`` is a client of that kind.
Import aliases resolve (``import requests as r``, ``from urllib.request import urlopen as uo``).
Indirection is followed where cheap: ``getattr(x, 'get')(u)``, ``functools.partial(x.get, u)`` and
``g = x.get; g(u)``. Bindings are file-wide, not scope-wide: over-matching is a red that names its
file, under-matching is the confident zero this guard exists to prevent.

**What counts as guarded -- and nothing else does:**

- a manager call whose ``guard_egress=`` is ``EGRESS_POLICY``, the literal ``False``, or a canonical
  policy value imported from the egress modules (``instance_host_egress()``, ``VENDOR_API_EGRESS``,
  ``CONTENT_URL_EGRESS``). Not literal ``True``, not an arbitrary variable, not ``None``.
- a raw call preceded, in the SAME function (nested defs excluded), by ``assert_egress_policy(<expr>)``
  (``assert_public_egress(<expr>)`` for a user-supplied URL),
  where ``<expr>`` is the same expression as the request's URL argument. A module-level policy call
  never counts. It also needs redirects refused: a literal ``allow_redirects=False`` (aiohttp,
  requests) or no ``follow_redirects`` opt-in (httpx, whose default is off). ``urlopen`` can never
  be guarded this way; a websocket counts only through ``ws_no_redirect.connect_no_redirect`` (websockets follows
  handshake redirects).
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path
from typing import Iterable, Iterator, NamedTuple

__all__ = ["Site", "outbound_sites", "scan_paths"]

_VERBS = {"get", "post", "put", "delete", "patch", "head", "request", "stream", "ws_connect"}
_MANAGER_ONLY = {"tracked_request", "get_json", "post_json"}
_MANAGER_RECV = re.compile(r"http_client|get_http_client\(\)|http_manager|HTTPClientManager|self\._?http\b")
_SESSION_RECV = re.compile(r"(^|\.)_?(session|sess|client)$", re.I)
_QUICK = re.compile(
    "|".join(
        ("tracked_request", "get_http_client", "HTTPClientManager", "http_client", "ClientSession", "tracked_session")
        + ("aiohttp", "httpx", "authlib", "requests", "urlopen", "get_json", "post_json")
    )
)
#: Raw-client pre-checks: server-chosen URLs use the first, user-/LLM-/document-supplied URLs the second.
_POLICY_CALLS = frozenset({"assert_egress_policy", "assert_public_egress"})
_CTORS = {
    "aiohttp.ClientSession": "session",
    "httpx.AsyncClient": "httpx",
    "httpx.Client": "httpx",
    "requests.Session": "requests",
    "requests.sessions.Session": "requests",
}
#: Canonical policy values and the module leaf names they may be imported from.
_POLICY_VALUES = {"EGRESS_POLICY", "VENDOR_API_EGRESS", "CONTENT_URL_EGRESS", "instance_host_egress"}
_POLICY_MODULES = {"base", "egress", "http_egress_guard"}
_EGRESS_MODULES = {"egress", "http_egress_guard"}
_URL_AT_1 = {"request", "tracked_request", "stream"}
#: The ``websockets`` connect wrapper that refuses handshake redirects: still a websocket outbound call.
_NO_REDIRECT_CONNECTS = frozenset({"connect_no_redirect", "NoRedirectConnect"})


class Site(NamedTuple):
    """One outbound call: 1-based line, client kind, and whether it carries a policy."""

    lineno: int
    kind: str
    guarded: bool


class _Ctx(NamedTuple):
    aliases: dict[str, str]  # local name -> dotted origin
    bound: dict[str, str]  # unparsed receiver -> client kind
    methods: dict[str, tuple[str, str]]  # name bound to ``recv.verb`` -> (recv, verb)
    policies: frozenset[str]  # local names that are canonical policy values
    redirecting: frozenset[str]  # httpx clients constructed with follow_redirects other than literal False
    aiohttp_text: bool


class _Req(NamedTuple):
    recv: str
    verb: str
    args: list[ast.expr]
    keywords: list[ast.keyword]


def _canon(expr: ast.expr, aliases: dict[str, str]) -> str:
    """Dotted name of *expr* with its first segment resolved through import aliases."""
    try:
        text = ast.unparse(expr)
    except Exception:
        return ""
    head, _, tail = text.partition(".")
    return aliases.get(head, head) + (f".{tail}" if tail else "")


def _import_maps(tree: ast.AST) -> tuple[dict[str, str], frozenset[str]]:
    aliases: dict[str, str] = {}
    policies: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                aliases[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            leaf = (node.module or "").split(".")[-1]
            for a in node.names:
                aliases[a.asname or a.name] = f"{node.module or ''}.{a.name}".lstrip(".")
                if a.name in _POLICY_VALUES and leaf in _POLICY_MODULES:
                    policies.add(a.asname or a.name)
    return aliases, frozenset(policies)


#: httpx transports that call an application object in this process and open no socket (#18765).
_IN_PROCESS_TRANSPORTS = frozenset({"httpx.ASGITransport", "httpx.WSGITransport"})
#: The binding kind of such a client: recorded, so a receiver-name fallback (``client``) never re-flags it.
_IN_PROCESS_KIND = "in-process"


def _in_process(ctor: ast.Call, aliases: dict[str, str]) -> bool:
    """True when an httpx client is built with ``transport=ASGITransport(...)`` and no ``mounts=``.

    ``mounts`` routes chosen URL patterns to other (network) transports, so a client that has
    them is not in-process however its default transport is set.
    """
    keywords = {kw.arg: kw.value for kw in ctor.keywords}
    transport = keywords.get("transport")
    return (
        "mounts" not in keywords
        and None not in keywords  # a **kwargs splat could carry mounts
        and isinstance(transport, ast.Call)
        and _canon(transport.func, aliases) in _IN_PROCESS_TRANSPORTS
    )


def _ctor_kind(expr: ast.expr | None, aliases: dict[str, str]) -> str | None:
    """Client kind produced by constructing/obtaining *expr*, if it is a known client factory."""
    if not isinstance(expr, ast.Call):
        return None
    canon = _canon(expr.func, aliases)
    if canon in _CTORS:
        return _IN_PROCESS_KIND if _in_process(expr, aliases) else _CTORS[canon]
    if canon.endswith(".tracked_session") or canon.endswith("get_http_client.tracked_session"):
        return "session"
    return "manager" if canon.split(".")[-1] == "get_http_client" else None


def _follows_redirects(value: ast.expr | None) -> bool:
    """A constructor call carrying ``follow_redirects=`` that is not the literal ``False``."""
    inner = value.value if isinstance(value, ast.Await) else value
    return isinstance(inner, ast.Call) and any(
        kw.arg == "follow_redirects" and not (isinstance(kw.value, ast.Constant) and kw.value.value is False)
        for kw in inner.keywords
    )


def _bindings(
    tree: ast.AST, aliases: dict[str, str]
) -> tuple[dict[str, str], dict[str, tuple[str, str]], frozenset[str]]:
    bound: dict[str, str] = {}
    methods: dict[str, tuple[str, str]] = {}
    redirecting: set[str] = set()
    for node in ast.walk(tree):
        pairs: list[tuple[ast.expr | None, ast.expr | None]] = []
        if isinstance(node, (ast.With, ast.AsyncWith)):
            pairs = [(i.optional_vars, i.context_expr) for i in node.items]
        elif isinstance(node, ast.Assign):
            pairs = [(t, node.value) for t in node.targets]
        elif isinstance(node, ast.AnnAssign):
            pairs = [(node.target, node.value)]
        for target, value in pairs:
            if target is None or not isinstance(target, (ast.Name, ast.Attribute)):
                continue
            kind = _ctor_kind(value.value if isinstance(value, ast.Await) else value, aliases)
            if kind:
                bound[ast.unparse(target)] = kind
                if _follows_redirects(value):
                    redirecting.add(ast.unparse(target))
            elif isinstance(value, ast.Attribute) and value.attr in _VERBS | _MANAGER_ONLY:
                methods[ast.unparse(target)] = (ast.unparse(value.value), value.attr)
    return bound, methods, frozenset(redirecting)


def _build_ctx(tree: ast.AST, source: str) -> _Ctx:
    aliases, policies = _import_maps(tree)
    bound, methods, redirecting = _bindings(tree, aliases)
    text = "aiohttp" in source or "tracked_session" in source or "http_client" in source
    return _Ctx(aliases, bound, methods, policies, redirecting, text)


def _str_const(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _request(call: ast.Call, ctx: _Ctx) -> _Req | None:
    """Normalise *call* to ``recv.verb(args)``, following getattr / partial / bound-method aliases."""
    func = call.func
    if _canon(func, ctx.aliases) in ("functools.partial", "partial") and call.args:
        inner = call.args[0]
        if isinstance(inner, ast.Attribute):
            return _Req(ast.unparse(inner.value), inner.attr, call.args[1:], call.keywords)
    if isinstance(func, ast.Attribute):
        return _Req(ast.unparse(func.value), func.attr, call.args, call.keywords)
    if isinstance(func, ast.Name) and func.id in ctx.methods:
        recv, verb = ctx.methods[func.id]
        return _Req(recv, verb, call.args, call.keywords)
    if isinstance(func, ast.Call) and _canon(func.func, ctx.aliases) == "getattr" and len(func.args) >= 2:
        verb = _str_const(func.args[1])
        return _Req(ast.unparse(func.args[0]), verb, call.args, call.keywords) if verb else None
    return None


def _is_no_redirect_connect(canon: str) -> bool:
    """``autobot_shared.ws_no_redirect``'s connect wrapper (or its class), however it was imported (#17576)."""
    return canon.startswith("autobot_shared.ws_no_redirect.") and canon.rsplit(".", 1)[-1] in _NO_REDIRECT_CONNECTS


def _kind(call: ast.Call, req: _Req | None, ctx: _Ctx) -> str | None:
    """Client kind of an outbound call, or ``None`` when *call* is not one."""
    canon = _canon(call.func, ctx.aliases)
    head, _, verb = canon.rpartition(".")
    if canon == "urllib.request.urlopen":
        return "urllib"
    if (canon.startswith("websockets.") and verb == "connect") or _is_no_redirect_connect(canon):
        return "websocket"
    if head in ("requests", "httpx") and verb in _VERBS:
        return head
    if req is None or (req.verb not in _VERBS and req.verb not in _MANAGER_ONLY):
        return None
    chained = isinstance(call.func, ast.Attribute) and _ctor_kind(call.func.value, ctx.aliases)
    kind = chained or _receiver_kind(req, ctx)
    return None if kind == _IN_PROCESS_KIND else kind


def _receiver_kind(req: _Req, ctx: _Ctx) -> str | None:
    if req.verb in _MANAGER_ONLY:
        return "manager"
    if not req.args and not req.keywords:
        return None  # ``x.get()`` -- a getter, not a request
    bound = ctx.bound.get(req.recv)
    if bound == _IN_PROCESS_KIND:
        return _IN_PROCESS_KIND  # before the name checks: an ASGI client named `http_client` is still in-process
    if bound == "manager" or _MANAGER_RECV.search(req.recv):
        return "manager"
    if bound:
        return bound
    imported = {v.split(".")[0] for v in ctx.aliases.values()}
    if req.recv.endswith(("session", "Session")) and "requests" in imported and not ctx.aiohttp_text:
        return "requests"
    if imported & {"httpx", "authlib"} and _SESSION_RECV.search(req.recv):
        return "httpx"
    return "session" if ctx.aiohttp_text and _SESSION_RECV.search(req.recv) else None


def _url_arg(call: ast.Call, req: _Req | None) -> ast.expr | None:
    """The expression a call sends its request to, when it can be named."""
    for kw in call.keywords:
        if kw.arg == "url":
            return kw.value
    args = req.args if req is not None else call.args
    idx = 1 if req is not None and req.verb in _URL_AT_1 else 0
    return args[idx] if len(args) > idx else None


def _accepted_policy(value: ast.expr, ctx: _Ctx) -> bool:
    """``False``, ``EGRESS_POLICY`` or a canonical policy value imported from the egress modules."""
    if isinstance(
        value, ast.IfExp
    ):  # ``instance_host_egress() if self.admin else CONTENT_URL_EGRESS``: both arms canonical
        return _accepted_policy(value.body, ctx) and _accepted_policy(value.orelse, ctx)
    if isinstance(value, ast.Constant):
        return value.value is False
    if isinstance(value, ast.Call):
        value = value.func
    if isinstance(value, ast.Name):
        return value.id in ctx.policies
    if isinstance(value, ast.Attribute) and value.attr in _POLICY_VALUES:
        # ``<x>.NAME`` only when x is bound by import to an egress module, not any module named ``base``.
        return _canon(value.value, ctx.aliases).split(".")[-1] in _EGRESS_MODULES
    return False


def _manager_guarded(call: ast.Call, ctx: _Ctx) -> bool:
    return any(kw.arg == "guard_egress" and _accepted_policy(kw.value, ctx) for kw in call.keywords)


def _own_scope_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    """Nodes in *scope*'s own body: nested defs, lambdas and classes are not entered."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(node))


def _literal_false(call: ast.Call, name: str) -> bool:
    return any(
        kw.arg == name and isinstance(kw.value, ast.Constant) and kw.value.value is False for kw in call.keywords
    )


def _redirects_refused(kind: str, call: ast.Call, req: _Req | None, ctx: _Ctx) -> bool:
    """True when a raw call cannot follow a redirect past the pre-check (#17576 review).

    aiohttp and requests follow redirects by default, so only a literal ``allow_redirects=False``
    counts. httpx does not follow by default: refused unless the call or its client opts in.
    ``urlopen`` has no switch at all. A websocket handshake is followed by ``websockets.connect``;
    only the ``ws_no_redirect`` wrapper refuses it.
    """
    if kind == "websocket":  # ``websockets.connect`` follows handshake redirects; only the wrapper refuses them
        return _is_no_redirect_connect(_canon(call.func, ctx.aliases))
    if kind == "httpx":
        opted_in = any(kw.arg == "follow_redirects" for kw in call.keywords)
        if opted_in:
            return _literal_false(call, "follow_redirects")
        return (req.recv if req else "") not in ctx.redirecting
    return kind in ("session", "requests") and _literal_false(call, "allow_redirects")


def _raw_guarded(call: ast.Call, url: ast.expr | None, scope: ast.AST) -> bool:
    """A same-function ``assert_egress_policy(<same url expr>)`` earlier than *call*."""
    if url is None or isinstance(scope, ast.Module):
        return False
    want = ast.dump(url)
    for node in _own_scope_nodes(scope):
        if isinstance(node, ast.Call) and _canon(node.func, {}).split(".")[-1] in _POLICY_CALLS:
            arg = node.args[0] if node.args else None
            if arg is not None and node.lineno < call.lineno and ast.dump(arg) == want:
                return True
    return False


def _calls(node: ast.AST, scope: ast.AST) -> Iterator[tuple[ast.Call, ast.AST]]:
    """Every ``Call`` with its nearest enclosing function (or the module)."""
    for child in ast.iter_child_nodes(node):
        inner = child if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else scope
        if isinstance(child, ast.Call):
            yield child, scope
        yield from _calls(child, inner)


def outbound_sites(source: str) -> tuple[Site, ...]:
    """Every outbound call in *source*. Raises ``SyntaxError`` rather than returning ``()``."""
    tree = ast.parse(source)
    ctx = _build_ctx(tree, source)
    sites = []
    for call, scope in _calls(tree, tree):
        req = _request(call, ctx)
        kind = _kind(call, req, ctx)
        if kind is None:
            continue
        if kind == "manager":
            guarded = _manager_guarded(call, ctx)
        else:
            guarded = _redirects_refused(kind, call, req, ctx) and _raw_guarded(call, _url_arg(call, req), scope)
        sites.append(Site(call.lineno, kind, guarded))
    return tuple(sorted(sites))


@functools.lru_cache(maxsize=None)
def _outbound_sites_cached(source: str) -> tuple[Site, ...]:
    """``outbound_sites`` memoised on the file TEXT: several tests sweep the same tree, and keying
    on content (not path) means an edited file is re-parsed, never served stale. A SyntaxError is
    not cached, so an unparsable file is re-reported every sweep."""
    return outbound_sites(source)


def scan_paths(root: Path, relative_paths: Iterable[str]) -> dict[str, tuple[Site, ...]]:
    """Map each path with outbound calls to them; an unparsable file gets an ``(UNPARSED)`` key."""
    found: dict[str, tuple[Site, ...]] = {}
    for rel in relative_paths:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        if not _QUICK.search(text):
            continue  # speed gate on vocabulary, not a matcher
        try:
            sites = _outbound_sites_cached(text)
        except SyntaxError:
            found[f"{rel} (UNPARSED)"] = ()
            continue
        if sites:
            found[rel] = sites
    return found
