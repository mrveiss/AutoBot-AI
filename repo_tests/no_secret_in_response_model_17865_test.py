# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No FastAPI `response_model` may carry a secret-bearing field (#17865).

`GET /agents/{agent_id}/llm` returned a decrypted provider API key as a
response-model field to any authenticated caller. The schema it returned carried
a docstring reading "LLM config including decrypted API key (for backend only)"
while being the ``response_model`` of a GET -- the docstring recorded an
invariant the code broke, and a comment is not an enforcement mechanism.

Fixing that one route would leave the *class* open, so this guard closes it:
a Pydantic model that declares a plainly secret-named field must never appear
as a ``response_model=``. Server-side code reads secrets through an accessor,
never through a model that a route can return.

The check is deliberately syntactic (AST, no imports): it must run without a
database, settings, or any app import, because a guard that needs the app to
start cannot run in the environment where it matters most.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_ROOT = repo_root()
_BACKENDS = ("autobot-backend", "autobot-slm-backend")

#: A field whose VALUE is a stored credential. Deliberately narrow.
#:
#: The first draft matched any name containing "token" and flagged 27 distinct
#: fields, almost all of them LLM token COUNTS -- `input_tokens`, `llm_max_tokens`,
#: `tokens_spent`. A guard that fires mostly on correct code gets switched off, so
#: breadth here would have cost the guard rather than bought coverage.
#:
#: Auth tokens are excluded on purpose too: `access_token` on a login response is
#: the endpoint's entire job. The class this guard exists for is a STORED
#: THIRD-PARTY CREDENTIAL leaving through a response model.
_SECRET_FIELD_DENY = re.compile(
    r"(api_key|apikey|private_key|sealed_value|client_secret|^password$|^secret$)",
    re.IGNORECASE,
)

#: Names that REFER to a credential without being one. A ref, an id, a ciphertext,
#: a hash, a boolean presence flag, a count or an expiry is what a SAFE response
#: carries -- folding these in would make the guard fire on the correct pattern.
_SECRET_FIELD_EXEMPT = re.compile(
    r"(_ref|_id|_encrypted|_hash|_masked|_type|_warning|_count|_usage|_limit|_at)$|^has_|^total_|^is_",
    re.IGNORECASE,
)

#: (model, field) -> why this one is intentional. A waiver is a WRITTEN REASON,
#: not a suppression: every secret that leaves through a response model must be
#: justified here, and `test_every_waiver_still_describes_a_real_site` fails if a
#: waiver stops matching anything, so they cannot quietly rot into permanent holes.
_WAIVED = {
    ("MFASetupResponse", "secret"): (
        "TOTP enrolment. The shared secret IS the deliverable -- the user cannot "
        "enrol an authenticator without it -- and it is returned once, at setup, "
        "for the CALLER'S OWN account: the handler binds `current_user` and "
        "resolves the row by that username. That is the precise contrast with "
        "#17865, which bound the identity to `_`, discarded it, and served any "
        "agent id to any authenticated caller."
    ),
}


def _is_secret_field(name: str) -> bool:
    return bool(_SECRET_FIELD_DENY.search(name)) and not _SECRET_FIELD_EXEMPT.search(name)


def _python_files(root: Path | None = None) -> list[str]:
    """Backend modules to scan, relative to *root*.

    Takes a root because `declare()` hands `discover` an EMPTY tree to prove the
    floor fires. On such a tree this returns `[]` rather than raising -- the
    refusal belongs to `ReachFloorError`, not to an incidental exception, so the
    meta-test can compare an empty result against the live one.
    """
    base_root = root or _ROOT
    out: list[str] = []
    for backend in _BACKENDS:
        base = base_root / backend
        if not base.is_dir():
            continue
        out += [
            p.relative_to(base_root).as_posix()
            for p in sorted(base.rglob("*.py"))
            if not any(part in {"venv", ".venv", "node_modules", "migrations"} for part in p.parts)
        ]
    return out


REACH = declare(
    "response-model-secret-scan",
    discover=_python_files,
    floor=4600,
    growth=150,
    skips=0,
    what="backend Python modules scanned for response_model= referencing a secret-bearing schema",
)


def _secret_fields(node: ast.ClassDef) -> list[str]:
    """Field names on this class body that are secrets in themselves."""
    found = []
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            if _is_secret_field(stmt.target.id):
                found.append(stmt.target.id)
    return found


@lru_cache(maxsize=1)
def _index() -> tuple[tuple[str, ...], dict[str, list[str]], dict[str, list[str]], tuple[tuple[str, int, str], ...]]:
    """Parse once: (files, own-secret-fields, base-names, response_model sites).

    The whole tree is indexed before anything is judged, because a model usually
    inherits its secret field from a parent in another module -- which is exactly
    how the #17865 defect was built, and what a per-file check would have missed.
    """
    own: dict[str, list[str]] = {}
    bases: dict[str, list[str]] = {}
    routes: list[tuple[str, int, str]] = []
    parsed: list[str] = []

    for rel in _python_files():
        try:
            tree = ast.parse((_ROOT / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        parsed.append(rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                own[node.name] = _secret_fields(node)
                bases[node.name] = [b.id for b in node.bases if isinstance(b, ast.Name)]
            elif isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "response_model" and isinstance(kw.value, ast.Name):
                        routes.append((rel, node.lineno, kw.value.id))
    return tuple(parsed), own, bases, tuple(routes)


def _inherited_fields(name: str, seen: frozenset[str] = frozenset()) -> list[str]:
    """Secret-named fields on *name*, including those it inherits."""
    if name in seen:
        return []
    _, own, bases, _ = _index()
    fields = list(own.get(name, []))
    for base in bases.get(name, []):
        fields += _inherited_fields(base, seen | {name})
    return fields


def _scan() -> tuple[tuple[str, ...], tuple[tuple[str, int, str, str], ...]]:
    """Returns (files_parsed, violations). Violations are (file, line, model, field)."""
    parsed, _, _, routes = _index()
    violations = [
        (rel, line, model, field)
        for rel, line, model in routes
        for field in _inherited_fields(model)
        if (model, field) not in _WAIVED
    ]
    return parsed, tuple(sorted(set(violations)))


@lru_cache(maxsize=1)
def _response_model_names() -> frozenset[str]:
    """Every class name used as `response_model=` anywhere in the backends."""
    names: set[str] = set()
    for rel in _python_files():
        try:
            tree = ast.parse((_ROOT / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg == "response_model" and isinstance(kw.value, ast.Name):
                    names.add(kw.value.id)
    return frozenset(names)


def test_the_scan_reaches_the_backends():
    """The floor fires before any assertion below can pass vacuously.

    `completed`, not just the discovery count: a file that fails to parse is
    skipped by `_index`, and a skip is not a clean file. Without this the floor
    would measure how many files were *available* rather than how many were
    actually examined -- and a tree that stopped parsing would read as a pass.
    """
    REACH.verify_floor(_ROOT)
    parsed, _ = _scan()
    REACH.completed(len(parsed))


def test_no_response_model_carries_a_secret_field():
    parsed, violations = _scan()
    assert parsed, "scanned nothing — the guard did not look, which is not the same as finding nothing"
    assert not violations, "a route returns a model carrying a secret field:\n" + "\n".join(
        f"  {rel}:{line} response_model={model} carries {field!r}" for rel, line, model, field in violations
    )


def test_the_guard_fires_on_the_shape_it_exists_to_catch():
    """The #17865 shape itself: a model inheriting the secret from a parent.

    Without this, a refactor that broke `inherited()` would leave every
    assertion above passing on an empty violation list -- green because it
    stopped looking, which is the failure this guard is built against.
    """
    src = (
        "class Cfg(BaseModel):\n"
        "    llm_model: str | None = None\n"
        "class CfgWithKey(Cfg):\n"
        "    llm_api_key: str | None = None\n"
    )
    classes = {n.name: n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ClassDef)}
    assert _secret_fields(classes["CfgWithKey"]) == ["llm_api_key"]
    assert _secret_fields(classes["Cfg"]) == [], "a non-secret field must not trip the matcher"


def test_every_waiver_still_describes_a_real_site():
    """A waiver that matches nothing is a hole nobody is watching any more.

    If the MFA route is renamed or its field removed, this fails and the waiver
    is deleted -- rather than sitting there silently exempting a name that some
    future model might take.
    """
    served = _response_model_names()
    stale = sorted(
        (model, field) for (model, field) in _WAIVED if model not in served or field not in _inherited_fields(model)
    )
    assert not stale, (
        "waiver(s) no longer describe a real site -- delete them rather than "
        f"leaving a standing exemption for a name a future model could take: {stale}"
    )


@pytest.mark.parametrize(
    "field,flagged",
    [
        ("llm_api_key", True),
        ("api_key", True),
        ("sealed_value", True),
        ("password", True),
        ("secret", True),
        ("client_secret", True),
        # refs and ciphertext -- what a SAFE response carries
        ("api_key_ref", False),
        ("vault_id", False),
        ("llm_api_key_encrypted", False),
        ("password_hash", False),
        ("has_api_key", False),
        # token COUNTS -- the false positives that made the first draft unusable
        ("input_tokens", False),
        ("llm_max_tokens", False),
        ("tokens_spent", False),
        ("total_tokens_used", False),
        # auth tokens -- returning one is the endpoint's job
        ("access_token", False),
        ("refresh_token", False),
        ("llm_model", False),
    ],
)
def test_the_matcher_separates_a_stored_credential_from_everything_near_it(field, flagged):
    assert _is_secret_field(field) is flagged
