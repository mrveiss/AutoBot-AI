# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20761: secrets are compared through ``secure_compare`` only.

A raw ``compare_digest`` on ``str`` raises ``TypeError`` for non-ASCII input,
which was a 500 on a hostile header. One helper, no second copy.

Out of scope: ``docker/docker-proxy/proxy.py`` (outside the three trees; it
already compares encoded bytes, so it is safe).
"""

import ast
import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint import _parse_cache as parse_cache

_ROOT = repo_root()
_TREES = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
_HELPER = Path("autobot_shared/security/constant_time.py")
# Files another open PR owns; each entry is removed when that PR lands and the
# file is routed through secure_compare. A stale entry fails the test below.
_DEFERRED = {
    "autobot-backend/services/secrets_coordinator.py": "#21011 owns this file; route through secure_compare after it lands",
    "autobot_shared/auth/internal_api_key.py": "#20777 owns this file; it already compares UTF-8 bytes, route through secure_compare after it lands",
}
# Names whose value is a secret; matched case-insensitively against the final name of an operand.
_SECRET_NAME = re.compile(
    r"token|secret|password|passwd|api_?key|signature|digest|hmac|nonce|state|csrf|cookie", re.IGNORECASE
)
_SECRET_NAME_NO_STATE = re.compile(
    r"token|secret|password|passwd|api_?key|signature|digest|hmac|nonce|csrf|cookie", re.IGNORECASE
)
# A trailing word that says the name is an identifier or label *about* a secret, not the secret
# (``secret_id``, ``secret_name``, ``token_alg``); such a name is not a secret operand.
_LABEL_SUFFIX = frozenset({"id", "ids", "name", "type", "alg", "algorithm", "encoding", "scope", "kind", "count"})
# Reviewed ``==`` / ``!=`` hits that are not a secret compare: ``"path::stripped source line"`` -> one-line reason.
_COMPARE_ALLOWLIST: dict[str, str] = {
    'autobot-backend/routers/code_completion.py::CodePattern.signature == pattern_data["signature"],': "SQL predicate on a code-pattern fingerprint, not a credential",
    'autobot-backend/knowledge/document_ingest.py::if record.get("content_digest") != digest:': "content-digest dedupe of documents, not authentication",
    "autobot-backend/knowledge/fact_store.py::found = await session.execute(select(KnowledgeFact.id).where(KnowledgeFact.content_hash == digest).limit(1))": "SQL dedupe predicate on a content hash",
    "autobot-backend/api/auth.py::_owns = (_token_sub and _token_sub == _caller_sub) or (_token_uid and _token_uid == _caller_uid)": "compares decoded identity claims (sub/uid) of a verified JWT, not secret material",
    "autobot-backend/api/chat_shared_links.py::ChatSharedLink.token == token,": "SQL predicate: the share token is looked up through the database index, no in-process secret compare",
    "autobot-backend/services/chunked_upload.py::if expected_sha256 and digest != expected_sha256.lower():": "upload integrity checksum against the client-declared sha256, not an authentication secret",
    'autobot-backend/services/secrets_backup_verifier.py::and record.get("service_type") == _SECRETS': "compares a record type label to a constant",  # pragma: allowlist secret
    'autobot-backend/services/knowledge/doc_index_orphans.py::return {i for i, m in zip(ids, metas) if run_token is None or (m or {}).get("index_run") == run_token}': "index run identifier, not a credential",
    "autobot-backend/user_management/services/session_service.py::if token_hash != except_hash:": "skips the caller's own session when blacklisting; selects entries, authenticates nothing",
    'autobot-backend/llc/adapters/subprocess_support.py::if context.get("agent_api_key") and context["agent_api_key"] != AGENT_API_KEY_PLACEHOLDER:': "comparison against the public placeholder constant",
    "autobot-backend/llc/adapters/subprocess_support.py::if api_key and api_key != AGENT_API_KEY_PLACEHOLDER:": "comparison against the public placeholder constant",
    'autobot-backend/llc/adapters/heartbeat_prompt.py::return bool(key) and key != AGENT_API_KEY_PLACEHOLDER and not context.get("replay")': "comparison against the public placeholder constant",
    "autobot-slm-backend/api/secrets.py::if key == HMAC_PEPPER_KEY:": "compares a secret's name to a key-name constant, not its value",
    "autobot-slm-backend/api/secrets.py::if key != HF_TOKEN_KEY:": "compares a secret's name to a key-name constant, not its value",
    'autobot-slm-backend/services/inventory_builder.py::elif not key.endswith("-") and token == key:': "role-name token from a config string, not a credential",
    "autobot-slm-backend/services/drift_checker.py::if deployed_digest == source_digest:": "file-content digest drift detection, not authentication",
    "autobot_shared/llm_provider_order.py::named = {token for token in order if token != REST}": "provider-name token versus a sentinel, not a credential",
    "autobot_shared/llm_provider_order.py::for name in unnamed if token == REST else [token]:": "provider-name token versus a sentinel, not a credential",
    "autobot_shared/pinned_model_registry.py::if actual_digest != expected_digest:": "integrity digest of a public model artifact, not an authentication secret",
    "autobot-backend/services/command_execution_queue.py::if state_filter is None or cmd.state == state_filter:": "command lifecycle state filter, not a credential",
    "autobot-backend/services/autoresearch/store.py::if old_state is not None and old_state != experiment.state:": "experiment lifecycle state transition, not a credential",
    "autobot-slm-backend/slm/agent/health_collector.py::if prev_state == new_state:": "service state-machine transition check (previous vs new unit state), not a credential",
}
# Allowlist entries are exact: the number of offending lines with this text in the file must equal the count
# (default 1), so a duplicated line cannot ride on an existing entry. Keys absent here count 1.
_ALLOWED_COUNT: dict[str, int] = {
    "autobot-backend/api/chat_shared_links.py::ChatSharedLink.token == token,": 2,  # SQL predicate in two queries
    "autobot-slm-backend/services/drift_checker.py::if deployed_digest == source_digest:": 2,  # two drift checks
}


def _production_files(root: Path = _ROOT):
    for tree in _TREES:
        for path in (root / tree).rglob("*.py"):
            rel = path.relative_to(root)
            name = path.name
            if rel == _HELPER or "tests" in rel.parts or name.startswith("test_") or name.endswith("_test.py"):
                continue
            yield rel, path


def _discover(root: Path) -> list[Path]:
    return [rel for rel, _ in _production_files(root)]


#: Measured at the time of writing: ~3500 production ``.py`` files under the three trees; the floor
#: leaves room for moves without letting an empty enumeration pass.
REACH = declare(
    "single-constant-time-compare",
    discover=_discover,
    floor=3602,  # mid-window: population 3602, window (3602, 3602)
    what="production python files",
    roots=_TREES,
)


def _operand_name(node: ast.AST) -> str | None:
    """Final name of ``x``, ``self.x`` or ``cfg["x"]``; None for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return node.slice.value
    return None


def _compare_digest_aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    """(bare names bound to compare_digest, module aliases of hmac/secrets) in ``tree``."""
    funcs, modules = {"compare_digest"}, {"hmac", "secrets"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("hmac", "secrets"):
            funcs.update(a.asname or a.name for a in node.names if a.name == "compare_digest")
        elif isinstance(node, ast.Import):
            modules.update(a.asname for a in node.names if a.name in ("hmac", "secrets") and a.asname)
    return funcs, modules


def _is_digest_call(node: ast.AST, funcs: set[str], modules: set[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    if isinstance(fn, ast.Name):
        return fn.id in funcs
    return (
        isinstance(fn, ast.Attribute)
        and fn.attr == "compare_digest"
        and isinstance(fn.value, ast.Name)
        and fn.value.id in modules
    )


def _is_secret_name(name: str | None) -> bool:
    if name is None or not _SECRET_NAME.search(name):
        return False
    return name.lower().rsplit("_", 1)[-1] not in _LABEL_SUFFIX


def _is_emptiness_check(operands: list[ast.AST]) -> bool:
    """``x == ""`` / ``x != None`` / ``x == 0`` tests presence, it does not compare two secrets."""
    return any(
        isinstance(o, ast.Constant) and (o.value in ("", None) or not isinstance(o.value, str)) for o in operands
    )


def _is_state_label(node: ast.AST) -> bool:
    """A string literal or an UPPER_CASE / ``Enum.MEMBER`` constant: a state-machine label, not a value."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    name = _operand_name(node)
    return name is not None and name.isupper()


def _is_secret_operand(node: ast.AST, others: list[ast.AST]) -> bool:
    """Secret-named operand. A name secret only by ``state`` (not csrf/cookie/token/...) compared to a
    state label is a state-machine check; ``state`` against a variable stays a hit (OAuth CSRF binding)."""
    name = _operand_name(node)
    if not _is_secret_name(name):
        return False
    only_state = not _SECRET_NAME_NO_STATE.search(name)
    if only_state and (name.isupper() or any(_is_state_label(o) for o in others)):
        return False
    return True


def _is_secret_eq(node: ast.AST) -> bool:
    if not isinstance(node, ast.Compare) or not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
        return False
    operands = [node.left, *node.comparators]
    if _is_emptiness_check(operands):
        return False
    return any(_is_secret_operand(o, [x for x in operands if x is not o]) for o in operands)


def _offenders(text: str) -> list[int]:
    """Lines with a raw/aliased ``compare_digest`` call or a ``==``/``!=`` on a secret-named operand."""
    try:
        tree = parse_cache.parse(text)
    except SyntaxError:
        return []
    funcs, modules = _compare_digest_aliases(tree)
    return sorted({n.lineno for n in ast.walk(tree) if _is_digest_call(n, funcs, modules) or _is_secret_eq(n)})


def _allow_key(rel: Path, text: str, n: int) -> str:
    return f"{rel.as_posix()}::{text.splitlines()[n - 1].strip()}"


def _unallowed(rel: Path, text: str, allowlist: dict[str, str] | None = None, counts: dict[str, int] | None = None):
    """Offending lines not covered by an allowlist entry; an entry covers exactly its count of identical lines."""
    allow = _COMPARE_ALLOWLIST if allowlist is None else allowlist
    limit = _ALLOWED_COUNT if counts is None else counts
    seen: dict[str, int] = {}
    out = []
    for n in _offenders(text):
        key = _allow_key(rel, text, n)
        seen[key] = seen.get(key, 0) + 1
        if key not in allow or seen[key] > limit.get(key, 1):
            out.append(n)
    return out


def _allowed_keys(rel: Path, text: str) -> set[str]:
    return {k for n in _offenders(text) if (k := _allow_key(rel, text, n)) in _COMPARE_ALLOWLIST}


def _digest_offenders(text: str) -> list[int]:
    """Lines with a raw/aliased ``compare_digest`` call only (the stale-entry check for _DEFERRED)."""
    tree = parse_cache.parse(text)
    funcs, modules = _compare_digest_aliases(tree)
    return sorted({n.lineno for n in ast.walk(tree) if _is_digest_call(n, funcs, modules)})


def test_no_raw_compare_digest_outside_the_helper() -> None:
    reached = REACH.examined(_ROOT)
    found = []
    seen_allow: set[str] = set()
    for rel in reached:
        if rel.as_posix() in _DEFERRED:
            continue
        text = (_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        found.extend(f"{rel}:{n}" for n in _unallowed(rel, text))
        seen_allow.update(_allowed_keys(rel, text))
    REACH.completed(len(reached), _ROOT)
    stale = set(_COMPARE_ALLOWLIST) - seen_allow
    assert not stale, f"stale _COMPARE_ALLOWLIST entries, drop them: {sorted(stale)}"
    assert found == [], f"use autobot_shared.security.constant_time.secure_compare: {found}"


def test_the_detector_sees_a_planted_call() -> None:
    assert _offenders("ok = hmac.compare_digest(a, b)") == [1]
    assert _offenders("ok = secrets.compare_digest(a, b)") == [1]
    assert _offenders("ok = secure_compare(a, b)") == []


def test_the_detector_sees_aliased_imports() -> None:
    assert _offenders("from hmac import compare_digest as cd\nok = cd(a, b)") == [2]
    assert _offenders("import hmac as h\nok = h.compare_digest(a, b)") == [2]
    assert _offenders("from secrets import compare_digest\nok = compare_digest(a, b)") == [2]
    assert _offenders("import secrets as s\nok = s.compare_digest(a, b)") == [2]


def test_the_detector_sees_secret_named_equality() -> None:
    for snippet in (
        "ok = token == stored",
        "ok = provided != secret",
        "ok = self.token == x",
        'ok = cfg["secret"] == x',
        "ok = x == self.api_key",
        "ok = x == payload.Signature",
        "ok = nonce == y",
        "ok = a == b == password",
    ):
        assert _offenders(snippet) == [1], snippet


def test_the_detector_ignores_an_innocent_equality() -> None:
    for snippet in ('ok = status == "ok"', "ok = count != 0", "ok = secure_compare(a, b)", "ok = token is None"):
        assert _offenders(snippet) == [], snippet


def test_every_deferred_entry_still_has_a_raw_call() -> None:
    for name, reason in _DEFERRED.items():
        text = (_ROOT / name).read_text(encoding="utf-8")
        assert _digest_offenders(
            text
        ), f"{name} no longer has a raw compare_digest call; drop it from _DEFERRED ({reason})"


def test_the_detector_sees_oauth_csrf_and_cookie_compares() -> None:
    for snippet in (
        "ok = cookie_state != state",
        "ok = state == stored_state",
        "ok = csrf == expected",
        "ok = request.csrf_token != x",
        "ok = cookie == y",
        'ok = cfg["state"] == value',
    ):
        assert _offenders(snippet) == [1], snippet


def test_a_state_machine_compare_is_not_flagged() -> None:
    for snippet in ('ok = state == "open"', "ok = self.state != CircuitState.OPEN", "ok = STATE_A == STATE_B"):
        assert _offenders(snippet) == [], snippet


def test_a_duplicated_allowlisted_line_is_still_flagged() -> None:
    line = "if token == other:"
    text = f"{line}\n    pass\n{line}\n    pass\n"
    rel = Path("x.py")
    key = _allow_key(rel, text, 1)
    assert _unallowed(rel, text, {}, {}) == [1, 3]
    assert _unallowed(rel, text, {key: "reviewed"}, {}) == [3]
    assert _unallowed(rel, text, {key: "reviewed"}, {key: 2}) == []
    assert _unallowed(rel, line + "\n", {key: "reviewed"}, {}) == []
