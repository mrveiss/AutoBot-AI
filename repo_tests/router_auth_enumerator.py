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


def _imported_gates(tree: ast.Module, root: Path, vocabulary: set[str]) -> set[str]:
    """Names imported from ANY module whose definition there reaches a primitive.

    `api/user_provider_credentials.py` gates every route with
    `Depends(get_current_user_id)`, imported from `api.user_management.dependencies`
    -- a path containing none of auth/security/permission/rbac. That function's own
    signature is `Depends(get_current_user)` and it raises 401. Reported UNGATED by
    the first version, and singled out in the issue as wanting attention first,
    because the import PATH was the filter rather than the behaviour.
    """
    gates = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        candidate = root / BACKEND / (node.module.replace(".", "/") + ".py")
        if not candidate.is_file():
            continue
        try:
            source = ast.parse(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        wanted = {a.asname or a.name for a in node.names}
        for defined in ast.walk(source):
            if not isinstance(defined, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if defined.name in wanted and (_calls_named(defined, vocabulary) - ACCESSOR_NOT_DECISION):
                gates.add(defined.name)
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


def classify(root: Path, alias: str, module: str, vocabulary: set[str]) -> Verdict:
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
    """Every registered router, classified. The table, not a count."""
    vocabulary = auth_vocabulary(root)
    return [classify(root, alias, module, vocabulary) for alias, module in registered_routers(root)]
