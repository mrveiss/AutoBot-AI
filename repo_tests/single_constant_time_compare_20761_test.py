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

import pytest
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
    floor=3621,  # mid-window: population 3621, window (3621, 3621)
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
    return _getter_key(node)


_GETTERS = frozenset({"get", "pop", "getenv", "getlist", "getfirst"})


def _getter_key(node: ast.AST) -> str | None:
    """The literal key of ``d.get("api_key")`` / ``os.getenv("API_KEY")``; None for any other call."""
    if not (isinstance(node, ast.Call) and node.args):
        return None
    fn = node.func
    fn_name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else None
    first = node.args[0]
    if fn_name in _GETTERS and isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
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


def _is_state_constant(name: str) -> bool:
    """A compound UPPER_CASE module constant (``STATE_ACTIVE``, ``HEALTH_STATE_KEY``) is a label; a bare ``STATE`` is not."""
    return name.isupper() and "_" in name


def _is_secret_operand(node: ast.AST, others: list[ast.AST]) -> bool:
    """Secret-named operand. A name secret only by ``state`` (not csrf/cookie/token/...) compared to a
    state label is a state-machine check; ``state`` (any case) against a variable stays a hit (OAuth CSRF binding)."""
    name = _operand_name(node)
    if not _is_secret_name(name):
        return False
    only_state = not _SECRET_NAME_NO_STATE.search(name)
    if only_state and (_is_state_constant(name) or any(_is_state_label(o) for o in others)):
        return False
    return True


def _is_secret_edge(left: ast.AST, right: ast.AST) -> bool:
    """One ``left ==/!= right`` edge: a presence test is not a secret compare, a secret-named side is."""
    if _is_emptiness_check([left, right]):
        return False
    return _is_secret_operand(left, [right]) or _is_secret_operand(right, [left])


def _is_secret_eq(node: ast.AST) -> bool:
    """Any ``==``/``!=`` edge of the chain is a secret compare (each edge judged alone, ``a == b != None``)."""
    if not isinstance(node, ast.Compare):
        return False
    operands = [node.left, *node.comparators]
    return any(
        isinstance(op, (ast.Eq, ast.NotEq)) and _is_secret_edge(operands[i], operands[i + 1])
        for i, op in enumerate(node.ops)
    )


def _offenders(text: str) -> list[int]:
    """Lines with a raw/aliased ``compare_digest`` call or a ``==``/``!=`` on a secret-named operand."""
    tree = parse_cache.parse(text)  # a SyntaxError propagates: an unparsable file must fail the guard, not read clean
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


def _allowed_counts(rel: Path, text: str, allowlist: dict[str, str] | None = None) -> dict[str, int]:
    """How many offending lines in *text* carry each allowlist key."""
    allow = _COMPARE_ALLOWLIST if allowlist is None else allowlist
    out: dict[str, int] = {}
    for n in _offenders(text):
        key = _allow_key(rel, text, n)
        if key in allow:
            out[key] = out.get(key, 0) + 1
    return out


def _count_mismatches(
    observed: dict[str, int], allowlist: dict[str, str] | None = None, counts: dict[str, int] | None = None
) -> list[str]:
    """Allowlist entries whose observed count is not EXACTLY the recorded one (absent = stale, lower = stale)."""
    allow = _COMPARE_ALLOWLIST if allowlist is None else allowlist
    limit = _ALLOWED_COUNT if counts is None else counts
    return [
        f"{key} (recorded {limit.get(key, 1)}, observed {observed.get(key, 0)})"
        for key in sorted(allow)
        if observed.get(key, 0) != limit.get(key, 1)
    ]


def _digest_offenders(text: str) -> list[int]:
    """Lines with a raw/aliased ``compare_digest`` call only (the stale-entry check for _DEFERRED)."""
    tree = parse_cache.parse(text)
    funcs, modules = _compare_digest_aliases(tree)
    return sorted({n.lineno for n in ast.walk(tree) if _is_digest_call(n, funcs, modules)})


def test_no_raw_compare_digest_outside_the_helper() -> None:
    reached = REACH.examined(_ROOT)
    found, unparsable = [], []
    observed: dict[str, int] = {}
    parsed = 0
    for rel in reached:
        if rel.as_posix() in _DEFERRED:
            continue
        text = (_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        try:
            found.extend(f"{rel}:{n}" for n in _unallowed(rel, text))
        except SyntaxError as exc:
            unparsable.append(f"{rel}: {exc}")
            continue
        parsed += 1
        for key, count in _allowed_counts(rel, text).items():
            observed[key] = observed.get(key, 0) + count
    REACH.completed(parsed, _ROOT)  # the floor binds the files actually inspected, not the ones listed
    assert not unparsable, f"files the guard could not parse, so did not inspect: {unparsable}"
    stale = _count_mismatches(observed)
    assert not stale, f"_COMPARE_ALLOWLIST / _ALLOWED_COUNT entries out of date, make them exact: {stale}"
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
    single = f"{line}\n    pass\n"
    assert _unallowed(rel, single, {key: "reviewed"}, {}) == []
    assert _unallowed(rel, single, {}, {}) == [1]  # contrast: the same single line, no allowlist entry


def test_an_unparsable_file_fails_instead_of_reading_clean() -> None:
    with pytest.raises(SyntaxError):
        _offenders("if token == other:\n")


def test_a_reduced_or_missing_allowlist_count_is_stale() -> None:
    allow = {"k": "reviewed"}
    assert _count_mismatches({"k": 2}, allow, {"k": 2}) == []
    assert _count_mismatches({"k": 1}, allow, {"k": 2}) == ["k (recorded 2, observed 1)"]
    assert _count_mismatches({}, allow, {}) == ["k (recorded 1, observed 0)"]
    assert _count_mismatches({"k": 2}, allow, {}) == ["k (recorded 1, observed 2)"]


def test_each_chain_edge_is_judged_alone() -> None:
    assert _offenders("ok = token == expected != None") == [1]
    assert _offenders("ok = None != expected == token") == [1]  # contrast: the secret edge is the second one
    assert _offenders("ok = token != None") == []  # contrast: a lone presence test stays exempt
    assert _offenders("ok = x is not None != y") == []


def test_getter_calls_and_uppercase_state_names_are_secret_operands() -> None:
    for snippet in (
        'ok = data.get("api_key") == x',
        'ok = os.getenv("API_TOKEN") != x',
        "ok = STATE == user_state",
        "ok = x == STATE",
    ):
        assert _offenders(snippet) == [1], snippet
    for snippet in (
        'ok = data.get("mode") == x',
        "ok = STATE == OTHER_STATE",
        "ok = state == STATE_ACTIVE",
        'ok = data.get("api_key") == ""',
    ):
        assert _offenders(snippet) == [], snippet  # contrasts
