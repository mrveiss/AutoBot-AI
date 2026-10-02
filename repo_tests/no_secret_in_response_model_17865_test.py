# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No FastAPI `response_model` may carry a stored credential (#17865).

`GET /agents/{agent_id}/llm` returned a decrypted provider API key as a
response-model field. The schema it returned carried a docstring reading
"LLM config including decrypted API key (for backend only)" while being the
`response_model` of a GET -- the invariant was written down beside the code
that broke it, and a comment is not an enforcement mechanism.

Fixing that one route would leave the class open, so this guard closes it.

The detector resolves a response model through THREE paths, each of which a
naive version misses and each of which hides a real route in this tree:

* **inheritance** -- the field is usually declared on a parent in another
  module, which is exactly how the original defect was built.
* **nesting** -- `LLMConfigResponse` reaches `LLMProviderConfig.api_key`
  through a field annotation, not through a base class.
* **generic subscripts** -- `DataResponse[SecretCreatedData]` is an
  `ast.Subscript`, so a check reading only `ast.Name` sees nothing at all.

The check is deliberately syntactic (AST, no imports): it must run without a
database, settings, or any app import, because a guard that needs the app to
start cannot run in the environment where it matters most.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_ROOT = repo_root()
_BACKENDS = ("autobot-backend", "autobot-slm-backend")

#: A field whose VALUE is a stored credential.
#:
#: Breadth here is not free. A first draft matched any name containing "token"
#: and flagged 27 distinct fields, almost all LLM token COUNTS -- `input_tokens`,
#: `llm_max_tokens`, `tokens_spent`. A guard that fires mostly on correct code
#: gets switched off, so that would have cost the guard rather than bought
#: coverage. Auth tokens are excluded for the same reason: returning
#: `access_token` is a login endpoint's entire job.
#:
#: `password` and `secret` are matched as SUFFIXES, not whole names, so
#: `webhook_secret` and `service_password` are caught; the exemptions below
#: are what keeps `password_hash` and `secret_type` out, and they do that job
#: whether or not the deny pattern is anchored (CodeRabbit, #17865).
_SECRET_FIELD_DENY = re.compile(
    r"(api_key|apikey|private_key|sealed_value|client_secret|password|secret)",
    re.IGNORECASE,
)

#: Names that REFER to a credential without being one. A ref, an id, a
#: ciphertext, a hash, a boolean presence flag, a count or an expiry is what a
#: SAFE response carries -- folding these in would make the guard fire on the
#: correct pattern, which is how a guard gets disabled.
_SECRET_FIELD_EXEMPT = re.compile(
    r"(_ref|_id|_encrypted|_hash|_masked|_type|_warning|_count|_usage|_limit|_at|_name|_names"
    r"|_staleness|_status|_health|_rotation|_policy|_scope|_version)$"
    r"|^has_|^total_|^is_|^use_|^require_|^enable_|^masked_|^redacted_",
    re.IGNORECASE,
)

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})


def _is_secret_field(name: str) -> bool:
    return bool(_SECRET_FIELD_DENY.search(name)) and not _SECRET_FIELD_EXEMPT.search(name)


@dataclass(frozen=True)
class Route:
    """One `response_model=` site, identified by the route it serves."""

    file: str
    line: int
    method: str
    path: str
    model: str


def _python_files(root: Path | None = None) -> list[str]:
    """Backend modules to scan, relative to *root*.

    Takes a root because `declare()` hands `discover` an EMPTY tree to prove the
    floor fires. On such a tree this returns `[]` rather than raising -- the
    refusal belongs to `ReachFloorError`, not to an incidental exception.
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
    what="backend Python modules scanned for response_model= reaching a stored credential",
)


def _model_names(expr: ast.expr) -> list[str]:
    """Every class name mentioned in a `response_model=` expression.

    `DataResponse[SecretCreatedData]` is an `ast.Subscript`; `list[X]` and
    `Union[X, Y]` nest further. Reading only `ast.Name` made four existing
    secret-bearing routes invisible to this guard (CodeRabbit, #17865), so the
    extraction recurses rather than widening the matcher to compensate.
    """
    if isinstance(expr, ast.Name):
        return [expr.id]
    if isinstance(expr, ast.Attribute):
        return [expr.attr]
    if isinstance(expr, ast.Subscript):
        return _model_names(expr.value) + _model_names(expr.slice)
    if isinstance(expr, ast.Tuple):
        return [n for e in expr.elts for n in _model_names(e)]
    if isinstance(expr, ast.BinOp):  # X | Y
        return _model_names(expr.left) + _model_names(expr.right)
    return []


def _annotation_names(expr: ast.expr | None) -> list[str]:
    """Class names a field annotation refers to — the nesting edge."""
    return _model_names(expr) if expr is not None else []


def _route_of(node: ast.Call) -> tuple[str, str] | None:
    """(method, path) for a FastAPI route decorator call, else None."""
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr.lower() not in _HTTP_METHODS:
        return None
    path = ""
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        path = node.args[0].value
    return func.attr.upper(), path


@dataclass(frozen=True)
class Index:
    files: tuple[str, ...]
    failures: tuple[tuple[str, str], ...]
    own: dict[str, list[str]]
    bases: dict[str, list[str]]
    nested: dict[str, list[str]]
    routes: tuple[Route, ...]


def _build_index(root: Path) -> Index:
    """Parse every backend module once and record what each class reaches.

    The whole tree is indexed before anything is judged: a model usually
    inherits or nests its secret field from another module, which a per-file
    check cannot see.
    """
    own: dict[str, list[str]] = {}
    bases: dict[str, list[str]] = {}
    nested: dict[str, list[str]] = {}
    routes: list[Route] = []
    parsed: list[str] = []
    failures: list[tuple[str, str]] = []

    for rel in _python_files(root):
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError) as exc:
            # NOT skipped silently. A skip that the floor absorbs is exactly the
            # "did not look" that reads as "nothing found" (CodeRabbit, #17865).
            failures.append((rel, f"{type(exc).__name__}: {exc}"))
            continue
        parsed.append(rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                secrets, refs = [], []
                for stmt in node.body:
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                        if _is_secret_field(stmt.target.id):
                            secrets.append(stmt.target.id)
                        refs += _annotation_names(stmt.annotation)
                own.setdefault(node.name, [])
                own[node.name] = sorted(set(own[node.name] + secrets))
                bases[node.name] = sorted(set(bases.get(node.name, []) + [b for b in _model_names_of_bases(node)]))
                nested[node.name] = sorted(set(nested.get(node.name, []) + refs))
            elif isinstance(node, ast.Call):
                route = _route_of(node)
                for kw in node.keywords:
                    if kw.arg != "response_model":
                        continue
                    method, path = route or ("", "")
                    for name in _model_names(kw.value):
                        routes.append(Route(rel, node.lineno, method, path, name))
    return Index(tuple(parsed), tuple(failures), own, bases, nested, tuple(routes))


def _model_names_of_bases(node: ast.ClassDef) -> list[str]:
    return [n for b in node.bases for n in _model_names(b)]


@lru_cache(maxsize=4)
def _index(root: Path | None = None) -> Index:
    return _build_index(root or _ROOT)


def _reached_fields(model: str, idx: Index, seen: frozenset[str] = frozenset()) -> list[str]:
    """Secret-named fields reachable from *model* by inheritance OR nesting."""
    if model in seen or model not in idx.own:
        return []
    seen = seen | {model}
    fields = list(idx.own.get(model, []))
    for other in idx.bases.get(model, []) + idx.nested.get(model, []):
        fields += _reached_fields(other, idx, seen)
    return sorted(set(fields))


#: (model, field, METHOD, path) -> why this one is intentional.
#:
#: Keyed by the ROUTE, not by the model. `_WAIVED` keyed on (model, field)
#: alone would exempt every future route that reuses the model, including one
#: with a different authorisation posture (CodeRabbit, #17865). A waiver is a
#: written reason for ONE endpoint, not a property of a schema.
_WAIVED: dict[tuple[str, str, str, str], str] = {
    ("MFASetupResponse", "secret", "POST", "/setup"): (
        "TOTP enrolment. The shared secret IS the deliverable -- the user cannot "
        "enrol an authenticator without it -- returned once, at setup, for the "
        "CALLER'S OWN account: the handler binds `current_user` and resolves the "
        "row by that username. That is the precise contrast with #17865, which "
        "bound the identity to `_` and discarded it."
    ),
}


#: PRE-EXISTING sites, frozen so the guard can be introduced without pretending
#: they are fine. This is NOT a waiver list: a waiver says "audited, intentional,
#: here is why"; this says "present before the guard existed and NOT YET AUDITED".
#: Conflating the two is how a baseline becomes a permanent exemption.
#:
#: The widened detector found these only once it followed generic subscripts and
#: nesting -- they were invisible to the first version, which is the whole reason
#: CodeRabbit's finding mattered. Draining this set is tracked separately; the
#: ratchet below means it can only shrink.
_UNAUDITED_BASELINE: dict[tuple[str, str, str, str], str] = {
    ("autobot-backend/api/llm.py", "GET /config", "LLMConfigResponse", "api_key"): (
        "Not yet audited. Needs the call site checked for masking or omission."
    ),
    ("autobot-slm-backend/api/llm_config.py", "GET", "LLMConfigResponse", "api_key"): (
        "Masked at llm_config.py:196 (`provider.api_key = _mask_api_key(...)`), and "
        "being changed from masking to omission by PR #17846, which OWNS this file. "
        "Not touched here: same file, one PR, one agent."
    ),
    ("autobot-slm-backend/api/llm_config.py", "PUT", "LLMConfigResponse", "api_key"): (
        "Same model and same file as the GET above; #17846 territory."
    ),
    ("autobot-backend/api/secrets.py", "POST /", "SecretCreatedData", "secret"): (
        "`secret: Dict[str, Any]` -- an UNTYPED dict, so this guard cannot tell "
        "whether the value travels in it. That unauditability is itself the finding."
    ),
    ("autobot-backend/api/secrets.py", "GET /{secret_id}", "SecretCreatedData", "secret"): (
        "Same untyped `Dict[str, Any]` as above."
    ),
    ("autobot-backend/api/secrets.py", "PUT /{secret_id}", "SecretCreatedData", "secret"): (
        "Same untyped `Dict[str, Any]` as above."
    ),
    ("autobot-backend/api/secrets.py", "DELETE /{secret_id}", "SecretCreatedData", "secret"): (
        "Same untyped `Dict[str, Any]` as above."
    ),
    ("autobot-backend/api/secrets.py", "GET /", "SecretsListData", "secrets"): (
        "`secrets: List[Dict[str, Any]]` -- untyped elements; same limit as above."
    ),
}


def _violations(idx: Index) -> list[tuple[str, int, str, str, str]]:
    out = []
    for route in idx.routes:
        for field in _reached_fields(route.model, idx):
            if (route.model, field, route.method, route.path) in _WAIVED:
                continue
            if (route.file, f"{route.method} {route.path}".strip(), route.model, field) in _UNAUDITED_BASELINE:
                continue
            out.append((route.file, route.line, f"{route.method} {route.path}".strip(), route.model, field))
    return sorted(set(out))


# --------------------------------------------------------------------------
# the guard
# --------------------------------------------------------------------------


def test_every_discovered_module_parsed():
    """A module that would not parse was NOT scanned, and must say so.

    `REACH.completed()` compares a count against a floor, and with a floor of
    4600 a handful of unparseable modules disappear into the margin. Discovered
    and parsed are compared directly here so "could not look" can never be
    reported as "found nothing".
    """
    idx = _index()
    assert not idx.failures, "modules discovered but not parsed:\n" + "\n".join(
        f"  {rel}: {err}" for rel, err in idx.failures
    )


def test_the_scan_reaches_the_backends():
    """The floor fires before any assertion below can pass vacuously."""
    REACH.verify_floor(_ROOT)
    REACH.completed(len(_index().files))


def test_no_response_model_reaches_a_stored_credential():
    idx = _index()
    assert idx.files, "scanned nothing — the guard did not look, which is not finding nothing"
    found = _violations(idx)
    assert not found, "a route returns a model reaching a stored credential:\n" + "\n".join(
        f"  {f}:{line} [{route}] response_model={model} reaches {field!r}" for f, line, route, model, field in found
    )


def test_every_waiver_still_describes_a_real_route():
    """A waiver matching nothing is a hole nobody is watching any more."""
    idx = _index()
    live = {(r.model, r.method, r.path) for r in idx.routes}
    stale = sorted(
        (model, field, method, path)
        for (model, field, method, path) in _WAIVED
        if (model, method, path) not in live or field not in _reached_fields(model, idx)
    )
    assert not stale, (
        "waiver(s) no longer describe a real route -- delete them rather than leaving "
        f"a standing exemption a future route could inherit: {stale}"
    )


# --------------------------------------------------------------------------
# contrast pairs — each runs the WHOLE detector over a fixture tree
# --------------------------------------------------------------------------


def _fixture_tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, src in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "name,files,expect_hit",
    [
        (
            # THE #17865 SHAPE: secret inherited from a parent in ANOTHER module.
            "inherited-across-modules",
            {
                "autobot-slm-backend/models/s.py": (
                    "class Cfg(BaseModel):\n    llm_model: str | None = None\n"
                    "class CfgWithKey(Cfg):\n    llm_api_key: str | None = None\n"
                ),
                "autobot-slm-backend/api/r.py": ("@router.get('/x', response_model=CfgWithKey)\ndef h(): ...\n"),
            },
            True,
        ),
        (
            # The same route returning the PARENT is clean.
            "inherited-across-modules-clean",
            {
                "autobot-slm-backend/models/s.py": (
                    "class Cfg(BaseModel):\n    llm_model: str | None = None\n"
                    "class CfgWithKey(Cfg):\n    llm_api_key: str | None = None\n"
                ),
                "autobot-slm-backend/api/r.py": "@router.get('/x', response_model=Cfg)\ndef h(): ...\n",
            },
            False,
        ),
        (
            # NESTING, not inheritance: reached through a field annotation.
            "nested-model",
            {
                "autobot-slm-backend/models/s.py": (
                    "class Provider(BaseModel):\n    api_key: str | None = None\n"
                    "class Outer(BaseModel):\n    providers: list[Provider] = []\n"
                ),
                "autobot-slm-backend/api/r.py": "@router.get('/x', response_model=Outer)\ndef h(): ...\n",
            },
            True,
        ),
        (
            # A GENERIC SUBSCRIPT -- invisible to an ast.Name-only reader.
            "generic-subscript",
            {
                "autobot-slm-backend/models/s.py": "class Data(BaseModel):\n    api_key: str | None = None\n",
                "autobot-slm-backend/api/r.py": (
                    "@router.post('/x', response_model=DataResponse[Data])\ndef h(): ...\n"
                ),
            },
            True,
        ),
        (
            "generic-subscript-clean",
            {
                "autobot-slm-backend/models/s.py": "class Data(BaseModel):\n    api_key_ref: str | None = None\n",
                "autobot-slm-backend/api/r.py": (
                    "@router.post('/x', response_model=DataResponse[Data])\ndef h(): ...\n"
                ),
            },
            False,
        ),
        (
            # A waived model REUSED on a different route must still be reported.
            "waiver-does-not-follow-the-model",
            {
                "autobot-slm-backend/models/s.py": (
                    "class MFASetupResponse(BaseModel):\n    secret: str | None = None\n"
                ),
                "autobot-slm-backend/api/r.py": (
                    "@router.get('/elsewhere', response_model=MFASetupResponse)\ndef h(): ...\n"
                ),
            },
            True,
        ),
        (
            # ...while the waived route itself stays clean.
            "waiver-applies-to-its-own-route",
            {
                "autobot-slm-backend/models/s.py": (
                    "class MFASetupResponse(BaseModel):\n    secret: str | None = None\n"
                ),
                "autobot-slm-backend/api/r.py": (
                    "@router.post('/setup', response_model=MFASetupResponse)\ndef h(): ...\n"
                ),
            },
            False,
        ),
    ],
)
def test_the_detector_end_to_end(tmp_path, name, files, expect_hit):
    """Drives `_build_index` + `_violations`, not just the field matcher.

    The repository itself only ever supplies the NEGATIVE result for `_scan`,
    so without these a refactor that broke route discovery or reachability
    would leave every assertion above passing on an empty list -- green because
    it stopped looking.
    """
    idx = _build_index(_fixture_tree(tmp_path, files))
    hits = _violations(idx)
    assert bool(hits) is expect_hit, f"{name}: expected hit={expect_hit}, got {hits}"


def test_a_module_that_does_not_parse_is_reported_not_skipped(tmp_path):
    tree = _fixture_tree(tmp_path, {"autobot-slm-backend/api/broken.py": "def (:\n"})
    idx = _build_index(tree)
    assert idx.failures, "an unparseable module must be reported, never silently skipped"
    assert "broken.py" in idx.failures[0][0]


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("X", ["X"]),
        ("DataResponse[Secret]", ["DataResponse", "Secret"]),
        ("list[Inner]", ["list", "Inner"]),
        ("Union[A, B]", ["Union", "A", "B"]),
        ("A | B", ["A", "B"]),
    ],
)
def test_generic_response_models_are_unwrapped(expr, expected):
    assert _model_names(ast.parse(expr, mode="eval").body) == expected


@pytest.mark.parametrize(
    "field,flagged",
    [
        ("llm_api_key", True),
        ("api_key", True),
        ("sealed_value", True),
        ("password", True),
        ("secret", True),
        ("client_secret", True),
        # the suffix cases the anchored first draft missed
        ("webhook_secret", True),
        ("service_password", True),
        # refs and ciphertext -- what a SAFE response carries
        ("api_key_ref", False),
        ("vault_id", False),
        ("llm_api_key_encrypted", False),
        ("password_hash", False),
        ("secret_type", False),
        ("has_api_key", False),
        ("total_secrets", False),
        ("secret_name", False),
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


def test_the_unaudited_baseline_only_shrinks():
    """A frozen entry that no longer fires must be DELETED, not left standing.

    This is what separates a baseline from an exemption. An entry that stops
    matching has either been fixed or moved; either way leaving it behind
    silently re-licenses the next route that lands on the same shape.
    """
    idx = _index()
    live = {
        (r.file, f"{r.method} {r.path}".strip(), r.model, field)
        for r in idx.routes
        for field in _reached_fields(r.model, idx)
    }
    stale = sorted(set(_UNAUDITED_BASELINE) - live)
    assert not stale, "baseline entries no longer fire -- remove them, the ratchet only turns down:\n" + "\n".join(
        f"  {e}" for e in stale
    )


def test_the_baseline_is_not_silently_growing():
    """Pins the size, so adding a route to the baseline is a visible decision."""
    assert (
        len(_UNAUDITED_BASELINE) <= 8
    ), f"the unaudited baseline grew to {len(_UNAUDITED_BASELINE)}; it may only shrink"
