# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No new direct Redis client outside the canonical layer (#18553, parent #17312).

Redis access goes through `autobot_shared.redis_client` (`get_redis_client` /
`get_async_redis_client`), which owns pooling, auth, TLS, the circuit breaker and the named
databases. A module that builds its own client gets none of that and silently diverges
(no password, a raw db number, `decode_responses` guessed). Before this guard nothing
enforced it tree-wide: the `no-direct-redis` pre-commit hook reads STAGED product `.py` files
only, honours a `# noqa: redis` opt-out, skips `autobot-infrastructure/`, and does not know
`from_url` or a connection pool.

WHAT IS A CONSTRUCTION
    A call whose callee resolves through the file's own `import redis...` / `from redis...
    import ...` bindings to `redis.*` (or the legacy `aioredis.*`) and ends in `Redis`,
    `StrictRedis`, `ConnectionPool`, `BlockingConnectionPool` or `from_url`. Resolving the import
    is what keeps SQLite / Ollama `ConnectionPool` classes out. Python is read from the syntax
    tree, so a comment, docstring or string naming `redis.Redis(` is not a site. Shell scripts
    that embed Python are read line by line with comments removed
    (`tools.lint._comment_syntax`).

BOUNDARY (stated where a reader meets the baseline -- RATCHET_BASELINES.md rule 1)
    * Scanned: tracked `.py` and `.sh` under `SCAN_ROOTS`, minus tests (`*_test.py`, `tests/`,
      `conftest.py`). The manual `analysis/test_*.py` scripts are NOT tests and are scanned.
    * Exempt by design: `autobot_shared/redis*` -- the canonical engine itself.
    * NOT seen: a client built by a library from a URI (LangGraph's checkpointer, Celery
      broker URLs), `getattr`/`__import__` indirection, and Python embedded in file types other
      than `.sh` (YAML, Jinja). Those are separate findings, not exemptions this file grants.
    * `# noqa: redis` exempts nothing here. A site is either in the baseline with a verdict or
      it fails.

THE BASELINE (`redis_direct_constructor_baseline_18553.py`) is a ratchet, not an allowlist:
exact per-file site counts, each with a verdict. A new site fails; a baselined site that left the
tree fails until its entry is lowered or removed; the total may not exceed `FROZEN_TOTAL`.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.redis_direct_constructor_baseline_18553 import BASELINE, FROZEN_TOTAL, VERDICTS

from tools.lint._comment_syntax import code_lines
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

SCAN_ROOTS = (
    "autobot-backend",
    "autobot-slm-backend",
    "autobot_shared",
    "autobot-infrastructure",
    "autobot-npu-worker",
    "autobot-tts-worker",
    "autobot-browser-worker",
    "scripts",
    "pipeline-scripts",
    "tools",
    "plugins",
    "libs",
    "debug",
)
_EXEMPT_PREFIX = "autobot_shared/redis"
_CLIENT_ROOTS = frozenset({"redis", "aioredis"})
_CLIENT_NAMES = frozenset({"Redis", "StrictRedis", "ConnectionPool", "BlockingConnectionPool", "from_url"})
#: Shell scripts embed Python as text; this is the same predicate over code lines.
_SHELL_SITE = re.compile(
    r"\b(?:aioredis|redis(?:\.asyncio)?)\.(?:Redis|StrictRedis|ConnectionPool|BlockingConnectionPool|from_url)\(|"
    r"\bRedis\.from_url\("
)


def _is_scanned(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    if not rel.endswith((".py", ".sh")) or rel.startswith(_EXEMPT_PREFIX):
        return False
    return not (name.endswith("_test.py") or name == "conftest.py" or "/tests/" in rel or "/test/" in rel)


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *SCAN_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_scanned(rel)]


REACH = declare(
    "redis-direct-constructor-scan",
    discover=_population,
    # Mid-window, from REACH.window(): population 3827 at d050455c7e -> (3527, 3827, 3677).
    floor=3677,
    what="non-test python and shell source",
    roots=SCAN_ROOTS,
    growth=300,
)


def _bindings(tree: ast.AST) -> dict[str, str]:
    """Local name -> dotted path for every `redis` import anywhere in the file (nested too)."""
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in _CLIENT_ROOTS:
                    bound[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif (
            isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] in _CLIENT_ROOTS
        ):
            for a in node.names:
                bound[a.asname or a.name] = f"{node.module}.{a.name}"
    return bound


def _dotted(func: ast.AST) -> list[str] | None:
    parts: list[str] = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if not isinstance(func, ast.Name):
        return None
    parts.append(func.id)
    return parts[::-1]


def python_sites(source: str) -> list[int]:
    """Line numbers of direct Redis client constructions in `source`."""
    tree = ast.parse(source)
    bound = _bindings(tree)
    lines: list[int] = []
    for node in ast.walk(tree):
        parts = _dotted(node.func) if isinstance(node, ast.Call) else None
        if not parts or parts[0] not in bound:
            continue
        full = bound[parts[0]].split(".") + parts[1:]
        if full[0] in _CLIENT_ROOTS and full[-1] in _CLIENT_NAMES:
            lines.append(node.lineno)
    return lines


def shell_sites(source: str, name: str) -> list[int]:
    return [cl.lineno for cl in code_lines(source, name=name) if _SHELL_SITE.search(cl.text)]


def sites_in(rel: str, source: str) -> list[int]:
    return python_sites(source) if rel.endswith(".py") else shell_sites(source, rel)


@functools.lru_cache(maxsize=1)
def _live() -> dict[str, int]:
    """Per-file site count over the scanned population."""
    found: dict[str, int] = {}
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        if "edis" not in source:
            continue
        n = len(sites_in(rel, source))
        if n:
            found[rel] = n
    return found


# --- contrast: the matcher, on synthetic sources ------------------------------------------------

_PY_CASES = [
    ("module call", "import redis\nc = redis.Redis(host='h')\n", 1),
    ("asyncio via alias", "import redis.asyncio as aioredis\nc = aioredis.Redis()\n", 1),
    ("asyncio dotted", "import redis.asyncio\nc = redis.asyncio.Redis()\n", 1),
    ("from-import class", "from redis import Redis\nc = Redis()\n", 1),
    ("aliased class", "from redis.asyncio import Redis as R\nc = R()\n", 1),
    ("from_url on module", "import redis\nc = redis.from_url('redis://h/1')\n", 1),
    ("from_url on class", "import redis\nc = redis.Redis.from_url('u')\n", 1),
    ("strict client", "import redis\nc = redis.StrictRedis()\n", 1),
    ("redis pool", "import redis\np = redis.ConnectionPool(host='h')\n", 1),
    ("pool from-import", "from redis.asyncio import ConnectionPool\np = ConnectionPool()\n", 1),
    ("nested import in a function", "def f():\n    import redis\n    return redis.Redis()\n", 1),
    ("sqlite pool is not redis", "class ConnectionPool: ...\np = ConnectionPool()\n", 0),
    ("ollama pool beside a redis import", "import redis\nfrom x import ConnectionPool\np = ConnectionPool()\n", 0),
    ("comment mention", "# redis.Redis(host='h')\nx = 1\n", 0),
    ("docstring mention", 'def f():\n    """uses redis.Redis() directly"""\n', 0),
    ("string mention", "import redis\ns = 'redis.Redis(host=1)'\n", 0),
    ("type annotation only", "import redis\ndef f(c: redis.Redis) -> redis.Redis: ...\n", 0),
    ("canonical client", "from autobot_shared.redis_client import get_redis_client\nc = get_redis_client()\n", 0),
    ("unrelated Redis class", "from mylib import Redis\nc = Redis()\n", 0),
]


@pytest.mark.parametrize(("label", "source", "expected"), _PY_CASES, ids=[c[0] for c in _PY_CASES])
def test_the_python_matcher_tells_a_construction_from_a_mention(label: str, source: str, expected: int) -> None:
    assert len(python_sites(source)) == expected, label


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("r = redis.Redis(host=h)\n", 1),
        ("    r = redis.asyncio.Redis()\n", 1),
        ("r = Redis.from_url(u)\n", 1),
        ("# r = redis.Redis(host=h)\n", 0),
        ("r = redis.Redis(host=h)  # kept\nx = 1\n", 1),
        ("echo 'no direct redis'\n", 0),
    ],
)
def test_the_shell_matcher_reads_code_lines_only(source: str, expected: int) -> None:
    assert len(shell_sites(source, "x.sh")) == expected


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("autobot-backend/api/terminal.py", True),
        ("autobot-slm-backend/ansible/deploy-native.sh", True),
        ("autobot-infrastructure/shared/scripts/analysis/test_redis_direct.py", True),
        ("autobot_shared/redis_client.py", False),
        ("autobot_shared/redis_management/connection_manager.py", False),
        ("autobot_shared/ssot_config.py", True),
        ("autobot-backend/tests/test_x.py", False),
        ("autobot-backend/api/terminal_test.py", False),
        ("autobot-backend/conftest.py", False),
        ("autobot-backend/notes.txt", False),
    ],
)
def test_the_exemption_is_the_canonical_layer_and_tests_only(rel: str, expected: bool) -> None:
    assert _is_scanned(rel) is expected


def _verdict_problems(live: dict[str, int], baseline: dict[str, tuple[int, str, str]]) -> list[str]:
    out: list[str] = []
    for rel, n in sorted(live.items()):
        if rel not in baseline:
            out.append(f"NEW {rel}: {n} direct Redis construction(s)")
        elif n > baseline[rel][0]:
            out.append(f"GREW {rel}: {n} sites, baseline allows {baseline[rel][0]}")
    for rel, (count, _verdict, _why) in sorted(baseline.items()):
        if live.get(rel, 0) < count:
            out.append(f"STALE {rel}: baseline {count}, tree {live.get(rel, 0)} -- lower or remove the entry")
    return out


def test_a_synthetic_new_construction_in_a_product_module_fails() -> None:
    live = {"autobot-backend/api/new_module.py": 1, "scripts/x.py": 1}
    base = {"scripts/x.py": (1, "EXCEPTION", "why")}
    assert _verdict_problems(live, base) == ["NEW autobot-backend/api/new_module.py: 1 direct Redis construction(s)"]


def test_a_second_site_in_a_baselined_file_fails_and_a_removed_site_is_stale() -> None:
    base = {"scripts/x.py": (1, "MIGRATE", "slice")}
    assert _verdict_problems({"scripts/x.py": 2}, base) == ["GREW scripts/x.py: 2 sites, baseline allows 1"]
    assert _verdict_problems({}, base)[0].startswith("STALE scripts/x.py")
    assert _verdict_problems({"scripts/x.py": 1}, base) == []


def test_the_same_construction_in_the_exempt_path_is_not_scanned_or_counted() -> None:
    assert not _is_scanned("autobot_shared/redis_client.py")
    assert python_sites("import redis\nc = redis.Redis()\n") == [2]  # the matcher itself still sees it


# --- the live tree ------------------------------------------------------------------------------


def test_the_scan_is_not_vacuous() -> None:
    live = _live()
    assert len(live) >= 20, f"only {len(live)} files with sites found; the scan is blind"
    assert "autobot-npu-worker/resources/windows-npu-worker/app/utils/redis_client.py" in live
    assert "autobot-slm-backend/ansible/deploy-native.sh" in live, "shell-embedded python must be reached"


def test_no_new_direct_redis_client_outside_the_canonical_layer() -> None:
    problems = _verdict_problems(_live(), BASELINE)
    assert not problems, (
        "#18553: use `autobot_shared.redis_client.get_redis_client` / `get_async_redis_client` "
        "(named database, pooled, authenticated).\n  " + "\n  ".join(problems)
    )


def test_the_baseline_only_shrinks() -> None:
    total = sum(count for count, _v, _w in BASELINE.values())
    assert total <= FROZEN_TOTAL, f"baseline sums to {total}, above the frozen ceiling {FROZEN_TOTAL}"
    assert total == FROZEN_TOTAL, f"baseline sums to {total}; lower FROZEN_TOTAL to {total} (it may only shrink)"


def test_every_baseline_entry_has_a_verdict_and_a_reason() -> None:
    for rel, (count, verdict, why) in BASELINE.items():
        assert count >= 1 and verdict in VERDICTS and why.strip(), rel
        assert (repo_root() / rel).is_file(), f"{rel} is baselined but not in the tree"
        assert _is_scanned(rel), f"{rel} is baselined but the scan would not read it"
