# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A new audit store writer cannot appear outside the known set (#17225).

#6475 closed on three audit systems; #17225 counted eight and a behaviour sweep found more.
D2/D3/D6 of docs/developer/AUDIT_SYSTEMS.md routed five of them through the canonical service,
whose Redis projection (`services/audit/projection.py`) is now the only module that writes an
`audit:` key. Every other module below writes a store the owner has not yet decided on; it is
pinned so a new one is a deliberate, recorded act: route the record through
`services.audit.audit` (emit/record), or add the module here AND to the inventory.

A "writer" is a non-test module that
  * has a store-write call (`zadd`, `lpush`, ...) AND a string literal that starts with an audit
    key prefix, or
  * constructs an audit ORM row (`AuditLog`, `WorkflowAuditLog`) or calls `audit_row`, or
  * holds an `INSERT INTO <...>audit` SQL literal, or
  * opens a file in a write mode (`open`, `aiofiles.open`) whose path names "audit", or in a
    module that binds an audit path (`audit_base_path`, `audit_log_file`).
"""

import ast
import functools
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = "autobot-backend/services/audit/projection.py"
_SYSTEM_OF_RECORD = "autobot-backend/services/audit/store.py"
_ROW_BUILDER = "autobot_shared/user_management/audit_rows.py"

#: Module -> why it may write. Shrinks as the open decisions in AUDIT_SYSTEMS.md land.
_KNOWN_WRITERS: dict[str, str] = {
    _CANONICAL: "canonical: the Redis projection of the audit trail",
    _SYSTEM_OF_RECORD: "canonical: audit_logs rows, through audit_rows.audit_row (D1)",
    _ROW_BUILDER: "the one constructor of an audit_logs row (D1)",
    "autobot_shared/user_management/middleware/rbac_middleware.py": "audit_logs via audit_row (D1)",
    "autobot_shared/user_management/organization_service.py": "audit_logs via audit_row (D1)",
    "autobot_shared/user_management/team_service.py": "audit_logs via audit_row (D1)",
    # #18267 made this the one UserService both backends use.
    "autobot_shared/user_management/user_service_base.py": "audit_logs via audit_row (D1)",
    "autobot-backend/services/workflow_permission_service.py": "workflow_audit_log (Postgres), moves to the service in #18284",
    "autobot-backend/services/secrets_audit_store.py": "secrets_audit (SQLite), moves to the service in #18284",
    "autobot-backend/a2a/trust_score.py": "trust_audit (SQLite), a domain history table -- #18285",
    "autobot-backend/security/enterprise/compliance_manager.py": "encrypted JSONL files, wired through the service in #18286",
    "autobot-slm-backend/api/security.py": "SLM slm_node_audit_logs, a separate table",
    # Not an audit record: code-audit daemon state sharing the `audit:` prefix (D4, needs a key move).
    "autobot-backend/workers/audit_tasks.py": "daemon state, D4 pending a key move",
}
#: Deleted by #17225 D2 and never to come back. A tombstone, censused as one by
#: `stranded_recorder_entries_test.TOMBSTONE_LEDGERS`, which fails if any reappears.
_RETIRED_MODULES = (
    "autobot-backend/services/audit/audit_log.py",
    "autobot-backend/services/event_log.py",
    "autobot-backend/knowledge/audit_log.py",
)
#: Kept by #17225 D3/D6 as adapters onto the canonical service; must not write a store again.
_RETIRED_WRITERS = (
    "autobot-backend/services/audit_logger.py",
    "autobot-backend/security_layer.py",
)
_WRITE_VERBS = frozenset({"zadd", "lpush", "rpush", "xadd", "sadd", "hset", "setex", "set", "append"})
_KEY_PREFIXES = ("audit:", "audit_log:", "autobot:event_log")
_WRITE_MODES = ("a", "w", "ab", "wb", "a+", "w+")
#: ORM rows that ARE audit records, and `audit_row`, the one constructor of an
#: `audit_logs` row (#17225 D1). A view class whose name merely ends in
#: "AuditLog" (KnowledgeAuditLog) is not one -- it records through the service.
_AUDIT_ORM_CLASSES = ("WorkflowAuditLog", "AuditLog", "SlmNodeAuditLog", "audit_row")
_PATH_WORDS = ("path", "file", "dir", "root")
_AUDIT_INSERT = re.compile(r"\binsert\s+into\s+\w*audit", re.IGNORECASE)


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _has_key_literal(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(_KEY_PREFIXES):
            return True
        if isinstance(node, ast.JoinedStr) and node.values:
            head = node.values[0]
            if isinstance(head, ast.Constant) and str(head.value).startswith(_KEY_PREFIXES):
                return True
    return False


def _names_audit(expr: ast.AST) -> bool:
    return any(
        (isinstance(n, ast.Attribute) and "audit" in n.attr.lower())
        or (isinstance(n, ast.Name) and "audit" in n.id.lower())
        for n in ast.walk(expr)
    )


def _mode_of(call: ast.Call) -> str | None:
    arg = call.args[1] if len(call.args) > 1 else next((k.value for k in call.keywords if k.arg == "mode"), None)
    return arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None


def _is_file_write(node: ast.AST) -> bool:
    """`open(p, "a")` or `aiofiles.open(p, "a")` -- any write mode."""
    is_open = _is_call(node, name="open") or _is_call(node, attr_in=frozenset({"open"}))
    return is_open and bool(node.args) and _mode_of(node) in _WRITE_MODES


def _target_names(node: ast.AST) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
    return [t.id if isinstance(t, ast.Name) else t.attr for t in targets if isinstance(t, (ast.Name, ast.Attribute))]


def _assigns_audit_path(nodes: list[ast.AST]) -> bool:
    """The module binds a name like `audit_base_path` / `audit_log_file`: its file writes are audit writes.

    A one-hop path argument (`storage_path = self.audit_base_path / ...`, passed to a helper that
    opens it) does not name "audit" at the open() call, which is how a file-backed audit store
    went unseen by the first version of this guard.
    """
    for node in nodes:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            for name in _target_names(node):
                low = name.lower()
                if "audit" in low and any(part in low for part in _PATH_WORDS):
                    return True
    return False


def _is_call(node: ast.AST, *, attr_in: frozenset[str] = frozenset(), name: str = "") -> bool:
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    return (isinstance(f, ast.Attribute) and f.attr in attr_in) or (isinstance(f, ast.Name) and f.id == name)


def _has_audit_insert(tree: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Constant) and isinstance(n.value, str) and _AUDIT_INSERT.search(n.value)
        for n in ast.walk(tree)
    )


def is_audit_writer(source: str) -> bool:
    """True when `source` writes an audit store by one of the shapes in the module doc."""
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    if any(_is_call(n, name=orm) for n in nodes for orm in _AUDIT_ORM_CLASSES):
        return True
    if _has_audit_insert(tree):
        return True
    audit_path_module = _assigns_audit_path(nodes)
    for n in nodes:
        if _is_file_write(n) and (audit_path_module or _names_audit(n.args[0])):
            return True
    return any(_is_call(n, attr_in=_WRITE_VERBS) for n in nodes) and _has_key_literal(tree)


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("redis zadd on an audit key", 'async def f(r):\n    await r.zadd("audit:x", {"a": 1})\n', True),
        (
            "f-string audit key via a variable",
            'def f(r, u):\n    k = f"audit_log:{u}"\n    r.zadd(k, {"a": 1})\n',
            True,
        ),
        ("orm row", "def f(s):\n    s.add(WorkflowAuditLog(user_id=1))\n", True),
        ("jsonl append", 'def f(self):\n    open(self.audit_log_file, "a")\n', True),
        ("reads an audit key only", 'def f(r):\n    return r.zrange("audit:x", 0, -1)\n', False),
        ("writes an unrelated key", 'def f(r):\n    r.zadd("queue:x", {"a": 1})\n', False),
        ("reads an audit file", 'def f(self):\n    open(self.audit_log_file, "r")\n', False),
        ("appends to an unrelated file", 'def f():\n    open("out.txt", "a")\n', False),
        ("audit orm row", "def f(s):\n    s.add(AuditLog(action='x'))\n", True),
        ("the shared row constructor", "def f(s):\n    s.add(audit_row(action='x', resource_type='r'))\n", True),
        ("a view class named like a row", "def f(r):\n    return KnowledgeAuditLog(r)\n", False),
        (
            "sql insert into an audit table",
            'def f(c):\n    c.execute("INSERT INTO secrets_audit (id) VALUES (?)")\n',
            True,
        ),
        ("sql read of an audit table", 'def f(c):\n    c.execute("SELECT id FROM secrets_audit")\n', False),
        (
            "aiofiles append in a module binding an audit path",
            "class C:\n    def __init__(self, p):\n        self.audit_base_path = p\n"
            '    async def w(self, path):\n        async with aiofiles.open(path, "a") as f:\n            pass\n',
            True,
        ),
        (
            "aiofiles append with no audit path",
            'async def w(path):\n    async with aiofiles.open(path, "a"):\n        pass\n',
            False,
        ),
    ],
)
def test_the_matcher_tells_a_writer_from_a_reader(label: str, source: str, expected: bool) -> None:
    assert is_audit_writer(source) is expected, label


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend", "autobot-slm-backend", "autobot_shared")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "audit-writer-single-source",
    discover=_population,
    # Mid-window, from REACH.window(): window (2697, 2997, 2847) at authoring.
    floor=3221,  # re-pinned mid-window (train 73): population 3371, window [3071, 3371] (#17844)
    what="non-test python source",
    roots=("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _writers() -> tuple[str, ...]:
    root = repo_root()
    found = []
    for rel in REACH.examined(root):
        text = (root / rel).read_text(encoding="utf-8")
        if "audit" in text or "event_log" in text:
            if is_audit_writer(text):
                found.append(rel)
    return tuple(sorted(found))


def test_no_audit_writer_outside_the_known_set() -> None:
    new = sorted(set(_writers()) - set(_KNOWN_WRITERS))
    assert not new, (
        f"#17225: {new} write an audit store. Route the record through services.audit.audit "
        "(emit/record) instead of a new store, or, if a new store is a recorded decision, add the "
        "module to _KNOWN_WRITERS and docs/developer/AUDIT_SYSTEMS.md."
    )


def test_every_known_writer_still_writes() -> None:
    """A writer that stopped writing, or moved, must leave the set; a stale entry hides a new one."""
    gone = sorted(set(_KNOWN_WRITERS) - set(_writers()))
    assert not gone, f"#17225: {gone} no longer match as audit writers; remove them from _KNOWN_WRITERS."


def test_a_retired_writer_does_not_come_back() -> None:
    """D2/D3/D6: the five retired stores are gone or record through the service."""
    back = sorted(set(_RETIRED_MODULES + _RETIRED_WRITERS) & set(_writers()))
    assert not back, f"#17225: {back} write an audit store again; record through services.audit.audit."


def test_a_deleted_audit_module_stays_deleted() -> None:
    """D2: a recreated legacy module is a second store waiting for a caller."""
    root = repo_root()
    back = [rel for rel in _RETIRED_MODULES if (root / rel).exists()]
    assert not back, f"#17225: {back} exist again; record through services.audit.audit."


def _redis_key_writers() -> list[str]:
    root = repo_root()
    found = []
    for rel in _writers():
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        if any(_is_call(n, attr_in=_WRITE_VERBS) for n in ast.walk(tree)) and _has_key_literal(tree):
            found.append(rel)
    return found


def test_the_projection_is_the_only_redis_audit_writer() -> None:
    """One Redis audit store: anything else writing an `audit:` key is a second one."""
    others = sorted(set(_redis_key_writers()) - {_CANONICAL, "autobot-backend/workers/audit_tasks.py"})
    assert not others, f"#17225: {others} write `audit:` keys; only {_CANONICAL} may."


_RETIRED_IMPORTS = re.compile(
    r"^\s*(?:from|import)\s+(?:services\.event_log|services\.audit\.audit_log|knowledge\.audit_log)\b"
    r"|^\s*from\s+(?:services|knowledge)\s+import\s+(?:[^#\n]*\b)?(?:event_log|audit_log)\b",
    re.MULTILINE,
)


def test_the_import_matcher_tells_an_import_from_prose() -> None:
    """Contrast pair: without it, a clean result could mean a matcher that never fires."""
    assert _RETIRED_IMPORTS.search("from services.event_log import emit\n")
    assert _RETIRED_IMPORTS.search("    from knowledge import audit_log\n")
    assert not _RETIRED_IMPORTS.search('"""was ``services.event_log.query_events``"""\n')


def test_nothing_imports_a_retired_module() -> None:
    """Behaviour, not symbols: an import of a retired module is a caller left half-migrated."""
    root = repo_root()
    hits = [rel for rel in REACH.examined(root) if _RETIRED_IMPORTS.search((root / rel).read_text(encoding="utf-8"))]
    assert not hits, f"#17225: {hits} still import a retired audit module; use services.audit.audit."


#: The only modules that construct `AuditLog(...)`: the one row builder, and the SLM API, whose
#: `AuditLog` is its own `slm_node_audit_logs` model, not this table.
#: The SLM's security.py builds `SlmNodeAuditLog` (#17312 rename), a separate table, not an audit_logs row.
_DIRECT_ROW_CONSTRUCTORS = frozenset({_ROW_BUILDER})


def test_audit_logs_rows_have_one_constructor() -> None:
    """D1: one schema means one mapping onto it -- a new direct `AuditLog(...)` is a second one."""
    root = repo_root()
    direct = sorted(
        rel
        for rel in _writers()
        if any(_is_call(n, name="AuditLog") for n in ast.walk(ast.parse((root / rel).read_text(encoding="utf-8"))))
    )
    assert set(direct) == _DIRECT_ROW_CONSTRUCTORS, f"#17225: build audit_logs rows with audit_rows.audit_row: {direct}"
