# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Enumerate which registered routers are gated, and by which mechanism (#15745).

Two sweeps before this one reported 30 ungated routers, then 15, then fewer --
each internally consistent and each wrong, always in the same direction. The
cause was not carelessness: **this codebase gates four different ways**, and a
detector that models three of them reports the fourth as a hole.

  1. router-level   `APIRouter(dependencies=[Depends(X)])` -- gates every route
                    in the file at once, as `api/agent_org.py` does.
  2. per-route      `Depends(X)` in a handler signature, or in the decorator's
                    own `dependencies=[...]`.
  3. inline         called in the handler BODY, never through `Depends`.
                    `api/websockets.py` awaits `enforce_ws_origin(websocket)`.
  4. middleware     whatever surface it actually covers -- see MIDDLEWARE_UNKNOWN.

**The vocabulary is derived, never typed.** The first sweep's regex omitted
`check_admin_permission`, the single most-used auth dependency in the backend
(140 imports), and that one omission produced fifteen false findings. So the
names come from what the auth modules export, measured from the tree.

RESOLUTION DEPTH IS ``MAX_DEPENDENCY_HOPS`` (3), AND THE VERDICT SAYS SO.
An ``UNGATED`` verdict means *not gated within that many dependency hops* -- it is
a claim about this sweep's reach, not a fact about the tree. The sweep has been
wrong four times, each because a gate sat further away than the resolver reached:
defined locally (0 hops), imported from a non-auth path (1), behind a service
chain (2), and mounted in an aggregator that declares no routes at all. Raising
the number treats the symptom; stating it is what stops the next reader mistaking
the two.

This module answers *which routers are gated and how*. It deliberately does not
report a bare count: three counts that disagree are worth less than one table a
reader can check a row of.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = "autobot-backend"
REGISTRY = f"{BACKEND}/initialization/router_registry/core_routers.py"

#: Modules whose exports are candidate auth gates. Used to DISCOVER the
#: vocabulary, not to define it.
_AUTH_MODULE = re.compile(r"^from ([a-z_.]*(?:auth|security|permission|rbac)[a-z_.]*) import ([A-Za-z_, ]+)")

#: Exported names that match `_AUTH_MODULE` but do not gate a request. Path and
#: crypto helpers live in the same modules and would otherwise read as auth --
#: `validate_path` protects a filesystem argument, not an identity.
#:
#: This list exists because "derive the vocabulary" is necessary and not
#: sufficient: derivation gets the NAMES from the tree, and purpose still has to
#: be decided. Each entry is a decision, so each is recorded rather than filtered
#: by a pattern that would also swallow a real gate.
NOT_A_GATE: frozenset[str] = frozenset(
    {
        "_normalise_role",
        "_normalize_for_matching",
        "_peek_alg",
        "build_owner_metadata",
        "canonical_role_permissions",
        "check_dangerous_patterns",
        "check_password_weakness",
        "chroma_client_auth_kwargs",
        "decode_jwt",
        "decode_jwt_no_verify_exp",
        "encode_jwt",
        "get_prompt_injection_detector",
        "hash_password",
        "role_value",
        "router",
        "security_scanner_agent",
        "validate_config_against_schema",
        "validate_path",
        "validate_relative_path",
        "validate_sql_identifier",
    }
)

#: Measured 2026-09-10: each of these appeared in a GATED verdict, and NONE was
#: the sole evidence for any router -- every one co-occurred with a real gate, so
#: no verdict was wrong. They are excluded anyway, because a name that can
#: contribute to a GATED verdict without gating anything is a false-GATED waiting
#: for the file where it appears alone. False GATED is the dangerous direction:
#: it hides a hole, where a false UNGATED merely wastes an investigation.

#: A file that documents an open posture in prose is a DECISION; a file that
#: documents nothing is a hole. The marker is required in the file itself --
#: allowlisting routers by name here would make this module the record, and the
#: record would then drift from the code it describes (#15737).
#:
#: Matched anywhere in the source, NOT only in `#` comments: `api/chat_embed.py`
#: documents its open posture in the module DOCSTRING, and a comment-only pattern
#: read it as undocumented. That is the same defect this module exists to catch --
#: a detector modelling one shape of a thing that has several.
_INTENTIONAL = re.compile(
    r"(?i)\b(public endpoint|publicly accessible|unauthenticated|no auth(?:entication)? (?:required|by design)"
    r"|open by design|intentionally ungated|embed widget|anonymous access)\b"
)


@dataclass
class Verdict:
    """One router's gating state, with the evidence that produced it."""

    alias: str
    module: str
    path: str
    mechanisms: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    intentional: bool = False
    unreadable: str = ""

    @property
    def gated(self) -> bool:
        return bool(self.mechanisms)


#: Parsed modules, keyed on resolved path. Chain resolution revisits the same
#: dependency modules for many routers -- `dependencies.py` alone is reached from
#: most of `api/user_management/*` -- so without this the sweep re-parses the same
#: files dozens of times.
#:
#: Measured before adding it: 21.7s for one `enumerate_routers`, and SIX tests call
#: it, which is 130s of identical work against a 128s pre-push budget. The guard
#: was not slow because it does a lot; it was slow because it did the same thing
#: repeatedly (#16182, #16187).
_PARSED: dict[str, ast.Module | None] = {}

#: One enumeration per root, for the same reason: the tests below ask the same
#: question and were each paying for the answer.
_ENUMERATED: dict[str, list["Verdict"]] = {}


def _parse_cached(path: Path) -> ast.Module | None:
    """Parse *path* once per process, returning None if it cannot be read."""
    key = str(path.resolve())
    if key not in _PARSED:
        try:
            _PARSED[key] = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            _PARSED[key] = None
    return _PARSED[key]


def auth_vocabulary(root: Path) -> set[str]:
    """Names exported by auth-ish modules, minus the ones that do not gate.

    Derived from the tree so a rename or a new dependency cannot silently fall
    outside the sweep -- which is exactly how `check_admin_permission` was missed.
    """
    names: set[str] = set()
    for path in (root / BACKEND).rglob("*.py"):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in source.splitlines():
            match = _AUTH_MODULE.match(line)
            if not match:
                continue
            for raw in match.group(2).split(","):
                name = raw.strip()
                if name and name.isidentifier() and not name[0].isupper():
                    names.add(name)
    return names - NOT_A_GATE


def registered_routers(root: Path) -> list[tuple[str, str]]:
    """`(alias, module)` for every router the registry imports."""
    registry = root / REGISTRY
    try:
        source = registry.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError):
        # Absent or unreadable registry -> reached nothing, NOT broken.
        # reach_declarations_test runs every discover() against a scratch
        # directory and requires a TYPED failure -- ReachFloorError from the
        # floor below -- not a FileNotFoundError from discovery itself. A guard
        # that crashes reports "broken" where it should report "reached
        # nothing", and those are different findings (#15745).
        return []
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        for alias in node.names:
            # ANY imported name ending in `router`, not only the literal `router`.
            # A module exporting two APIRouter objects names at most one of them
            # `router`: api/jwks.py exports `auth_router`, api/voice.py exports
            # `realtime_router` ALONGSIDE `router`, and api/voice_bundle_admin.py
            # exports `bundle_admin_router` and `bundle_me_router`. Matching the
            # literal name dropped all four from EVERY bucket -- not gated, not
            # ungated, not documented, not unreadable, simply absent. An
            # enumerator that silently omits its subject is the defect this
            # module exists to detect, in the module itself (#15745).
            if alias.name == "router" or alias.name.endswith("_router"):
                found.append((alias.asname or alias.name, node.module))
    return sorted(set(found))


def _calls_named(node: ast.AST, vocabulary: set[str]) -> set[str]:
    """Auth names invoked anywhere under *node*, however they are spelled.

    Covers `X(...)`, `Depends(X)`, `await X(...)` and `mod.X(...)` alike --
    the mechanism differs but the question here is only "is this name reached".
    """
    hit = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and inner.id in vocabulary:
            hit.add(inner.id)
        elif isinstance(inner, ast.Attribute) and inner.attr in vocabulary:
            hit.add(inner.attr)
    return hit


#: Auth-module names that FETCH something rather than DECIDE anything. Reaching
#: one of these does not make a function a gate.
#:
#: `api/jwks.py:_build_jwks` calls `get_auth_middleware()` to obtain the signing
#: key and publishes a public key set -- it authenticates nobody. One-hop
#: resolution without this exclusion reported `api.jwks` GATED, which is the
#: dangerous direction: a false GATED hides a hole, where a false UNGATED only
#: wastes an investigation.
#:
#: Measured before excluding: `_check_admin` reaches
#: {get_auth_middleware, is_admin_role} and stays a gate on `is_admin_role`;
#: `_build_jwks` reaches {get_auth_middleware} alone and correctly stops being one.
ACCESSOR_NOT_DECISION: frozenset[str] = frozenset({"get_auth_middleware"})


def _local_gates(tree: ast.Module, vocabulary: set[str]) -> set[str]:
    """Names defined IN THIS MODULE whose body reaches a known auth primitive.

    The vocabulary is derived from what auth-ish MODULES export, which misses a
    gate defined where it is used: `api/service_messages.py` defines
    `_check_admin`, calls `get_auth_middleware().get_user_from_request()` and
    `is_admin_role()` inside it, and gates all three of its routes with
    `Depends(_check_admin)`. Deriving by import path cannot see that, and the
    first version of this module reported the file UNGATED -- a FALSE finding
    published against a real security surface.

    One hop only, and deliberately: a dependency whose own body calls a
    vocabulary name is a gate. A dependency two modules away is not resolved
    here, and that limit is stated rather than left to be discovered.
    """
    gates = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _calls_named(node, vocabulary) - ACCESSOR_NOT_DECISION:
            gates.add(node.name)
    return gates


#: How many dependency hops resolution follows, and why the number is declared
#: rather than merely chosen.
#:
#: The sweep has been wrong THREE times in the same direction, each time because a
#: gate sat further away than the resolver reached:
#:
#:   0 hops  api/service_messages.py           `_check_admin` defined locally
#:   1 hop   api/user_provider_credentials.py  imported from a non-auth path
#:   2 hops  api/user_management/users.py      route -> get_user_service
#:                                                   -> get_tenant_context
#:                                                   -> get_current_user
#:
#: The first two were caught in review; the third by following up on that fix. So
#: the lesson is not "the number should be bigger" -- it is that an UNGATED verdict
#: must SAY what its reach was, or it reads as a fact about the tree rather than a
#: fact about the sweep. `Verdict.depth_limit` carries it into every report (#16187).
MAX_DEPENDENCY_HOPS = 3


def _resolve_gate_chain(
    name: str,
    module: str | None,
    root: Path,
    vocabulary: set[str],
    seen: set[tuple[str, str]],
    depth: int,
) -> bool:
    """Whether *name* reaches an auth primitive within the remaining depth.

    Follows `Depends(X)` from a route into X's own signature and body, then into
    whatever X depends on, to `MAX_DEPENDENCY_HOPS`.

    `seen` is a cycle guard, and it is not optional: dependency graphs here are
    recursive in practice, and an unbounded walk would HANG the guard rather than
    fail it -- a guard that never returns is worse than one that returns wrong,
    because nothing reports it.
    """
    if depth <= 0:
        return False
    key = (module or "", name)
    if key in seen:
        return False
    seen.add(key)

    candidates: list[Path] = []
    if module:
        candidate = root / BACKEND / (module.replace(".", "/") + ".py")
        if candidate.is_file():
            candidates.append(candidate)

    for path in candidates:
        tree = _parse_cached(path)
        if tree is None:
            continue
        imports = {
            alias.asname or alias.name: node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
            for alias in node.names
        }
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != name:
                continue
            reached = _calls_named(node, vocabulary) - ACCESSOR_NOT_DECISION
            if reached:
                return True
            # Not a gate itself -- follow what IT depends on, one level further.
            for referenced in _depends_names(node):
                if _resolve_gate_chain(referenced, imports.get(referenced, module), root, vocabulary, seen, depth - 1):
                    return True
    return False


def _depends_names(node: ast.AST) -> set[str]:
    """Names appearing inside a `Depends(...)` anywhere under *node*."""
    found = set()
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        if (getattr(inner.func, "id", "") or getattr(inner.func, "attr", "")) != "Depends":
            continue
        for arg in inner.args:
            ident = getattr(arg, "id", "") or getattr(arg, "attr", "")
            if ident:
                found.add(ident)
    return found


def _imported_gates(tree: ast.Module, root: Path, vocabulary: set[str]) -> set[str]:
    """Names this module imports that reach a primitive within MAX_DEPENDENCY_HOPS.

    `api/user_provider_credentials.py` gates on `get_current_user_id`, imported
    from `api.user_management.dependencies` -- a path containing none of
    auth/security/permission/rbac, so path-based derivation never saw it.

    `api/user_management/users.py` needs TWO hops: the route depends on
    `get_user_service`, which depends on `get_tenant_context`, which depends on
    `get_current_user`. One-hop resolution reported it ungated, and it is not.
    """
    gates = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        for alias in node.names:
            name = alias.asname or alias.name
            if _resolve_gate_chain(name, node.module, root, vocabulary, set(), MAX_DEPENDENCY_HOPS):
                gates.add(name)
    return gates


def _router_level(tree: ast.Module, vocabulary: set[str]) -> set[str]:
    """Mechanism 1: `APIRouter(dependencies=[...])` at module scope.

    Gates every route in the file at once, which is why a per-route sweep alone
    reports a fully-gated file as ungated -- `api/agent_org.py` has twelve routes
    and not one `Depends` among them.
    """
    hit = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
        if name != "APIRouter":
            continue
        for keyword in node.keywords:
            if keyword.arg == "dependencies":
                hit |= _calls_named(keyword.value, vocabulary)
    return hit


def _per_route(tree: ast.Module, vocabulary: set[str]) -> set[str]:
    """Mechanism 2: `Depends(X)` in a signature, or in a decorator's dependencies."""
    hit = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for default in list(node.args.defaults) + [d for d in node.args.kw_defaults if d]:
            hit |= _calls_named(default, vocabulary)
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                for keyword in decorator.keywords:
                    if keyword.arg == "dependencies":
                        hit |= _calls_named(keyword.value, vocabulary)
    return hit


def _inline(tree: ast.Module, vocabulary: set[str]) -> set[str]:
    """Mechanism 3: called in the handler BODY, never through `Depends`.

    The mechanism every regex-based sweep missed. `api/websockets.py` awaits
    `enforce_ws_origin(websocket)` inside the handler -- a real gate that no
    signature or decorator mentions.
    """
    hit = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(isinstance(d, ast.Call) for d in node.decorator_list):
            continue
        for statement in node.body:
            hit |= _calls_named(statement, vocabulary)
    return hit


#: Mechanism 4 is NOT implemented, and saying so is the point.
#:
#: `initialization/middleware.py`'s audit middleware comments that it assumes
#: `request.state.user` "is already populated" by something upstream -- and
#: #15758 found there is no upstream for the transcriber routes. So middleware
#: may cover nothing, cover some routers, or cover all of them, and this sweep
#: cannot tell which.
#:
#: A router reported UNGATED here is therefore "not gated by mechanisms 1-3",
#: which is a weaker claim than "reachable unauthenticated". Every finding needs
#: that last step confirmed by hand. Stating the boundary is what keeps this from
#: being a fourth sweep that is confidently wrong.
MIDDLEWARE_UNKNOWN = True


#: Names that REGISTER a route when used as a decorator. Only decorator position
#: counts: `.get` is also how every dict in the tree is read, so a bare call scan
#: would report routes in files that have none.
ROUTE_DECORATORS: frozenset[str] = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "trace", "websocket", "api_route"}
)

#: The same registration done as a plain call rather than a decorator. These are
#: unambiguous, so they count wherever they appear.
ROUTE_ADDERS: frozenset[str] = frozenset({"add_api_route", "add_websocket_route"})


def _defines_routes(tree: ast.Module) -> bool:
    """Whether this module registers any route of its OWN.

    A separate question from "does a gate appear here", and the aggregator branch
    used to answer the second and act on the first. A module that mounts sub-routers
    and also registers an ungated route of its own looked exactly like a pure
    aggregator, was judged by what it mounts, and reported GATED with its own route
    standing open -- and false GATED hides a hole (#16189 review).
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                if isinstance(target, ast.Attribute) and target.attr in ROUTE_DECORATORS:
                    return True
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr in ROUTE_ADDERS:
                return True
    return False


def _included_modules(tree: ast.Module) -> set[str]:
    """Modules whose routers this one mounts via `include_router`.

    `api/user_management/router.py` is 24 lines that mount four sub-routers and
    define NO routes of their own. Classifying it alone finds no gates -- correctly,
    since it has nothing to gate -- and the sweep reported UNGATED for a module with
    zero routes.

    That is the fourth distinct way a gate has escaped this sweep, and the most
    misleading: the others missed a gate that existed, this one reported on a file
    where neither routes nor gates live (#16187).
    """
    mounted = set()
    imports = {
        alias.asname or alias.name: node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if (getattr(node.func, "attr", "") or getattr(node.func, "id", "")) != "include_router":
            continue
        for arg in node.args:
            ident = getattr(arg, "id", "") or getattr(arg, "attr", "")
            if ident in imports:
                mounted.add(imports[ident])
    return mounted


def classify(root: Path, alias: str, module: str, vocabulary: set[str], seen: frozenset[str] = frozenset()) -> Verdict:
    """Decide one router, recording which mechanism produced the verdict."""
    relative = f"{BACKEND}/{module.replace('.', '/')}.py"
    verdict = Verdict(alias=alias, module=module, path=relative)
    path = root / relative
    if not path.is_file():
        verdict.unreadable = "module not found on disk"
        return verdict
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        verdict.unreadable = f"{type(exc).__name__}: {exc}"
        return verdict

    verdict.intentional = bool(_INTENTIONAL.search(source))
    # Widen the vocabulary with gates this module DEFINES or IMPORTS whose bodies
    # reach a known primitive, before asking which mechanism gates the routes.
    # Without this, a gate is invisible whenever it is spelled locally or lives
    # behind an import path that does not contain an auth-ish word (#15745).
    local = vocabulary | _local_gates(tree, vocabulary) | _imported_gates(tree, root, vocabulary)

    # What this module MOUNTS, and whether it also registers routes itself. Both
    # are asked, because a module can do both and the two need different verdicts
    # (#16187 found the aggregator case; #16189 review found the mixed one).
    included = _included_modules(tree)
    if included:
        # `seen` bounds the mount graph. `_resolve_gate_chain` documents why an
        # unbounded walk HANGS the guard rather than failing it; the same applies
        # here, and this recursion had no guard at all (#16189 review).
        sub = [
            classify(root, alias, name, vocabulary, seen | {module}) for name in sorted(included) if name not in seen
        ]
        readable = [v for v in sub if not v.unreadable]
        ungated = [v.module for v in readable if not v.gated]
        if not _defines_routes(tree):
            # A pure aggregator IS its mounts: it has nothing else to gate.
            if readable:
                if ungated:
                    verdict.mechanisms = []
                    verdict.evidence = [f"aggregator: mounted router(s) UNGATED -- {', '.join(ungated)}"]
                else:
                    verdict.mechanisms = ["aggregator"]
                    verdict.evidence = [
                        f"aggregator: {len(readable)}/{len(readable)} mounted routers gated "
                        f"({', '.join(v.module.rsplit('.', 1)[-1] for v in readable)})"
                    ]
                return verdict
        elif ungated:
            # Mounts AND registers its own routes. RECORDED, NOT COLLAPSED into this
            # module's verdict, and the distinction is deliberate: `api/knowledge.py`
            # gates its own 40 routes and mounts six sub-routers, two of which
            # (`knowledge_vectorization`, `knowledge_maintenance`, 37 routes between
            # them) `core_routers.py` never registers -- so the sweep has never
            # examined them. Reporting the PARENT ungated would put a well-gated
            # module on a list that means "no gate of any detectable kind", and would
            # still not say which mount is open.
            #
            # How the sweep should represent a router reachable only through a mount
            # is a design question this PR cannot settle, so the gap is STATED here
            # and filed rather than answered with a verdict that reads clean about
            # the wrong subject (#16194).
            verdict.evidence.append(f"mounts UNGATED router(s), not separately swept -- {', '.join(ungated)}")

    for label, found in (
        ("router-level", _router_level(tree, local)),
        ("per-route", _per_route(tree, local)),
        ("inline", _inline(tree, local)),
    ):
        if found:
            verdict.mechanisms.append(label)
            verdict.evidence.append(f"{label}: {', '.join(sorted(found))}")
    return verdict


def enumerate_routers(root: Path) -> list[Verdict]:
    """Every registered router, classified. The table, not a count.

    Memoised per root: six tests ask this question and each was paying 21.7s for
    the same answer, which alone exceeded the pre-push budget (#16182).
    """
    key = str(root.resolve())
    if key not in _ENUMERATED:
        vocabulary = auth_vocabulary(root)
        _ENUMERATED[key] = [classify(root, alias, module, vocabulary) for alias, module in registered_routers(root)]
    return _ENUMERATED[key]
