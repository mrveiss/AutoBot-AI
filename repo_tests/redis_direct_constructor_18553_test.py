# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No new direct Redis client outside the canonical layer (#18553, parent #17312).

Redis access goes through `autobot_shared.redis_client` (`get_redis_client` /
`get_async_redis_client`), which owns pooling, auth, TLS, the circuit breaker and the named
databases. A module that builds its own client gets none of that and silently diverges
(no password, a raw db number, `decode_responses` guessed). Before this guard nothing
enforced it tree-wide: the `no-direct-redis` pre-commit hook read STAGED product `.py` files
only, honoured a `# noqa: redis` opt-out, skipped `autobot-infrastructure/`, and did not know
`from_url` or a connection pool.

ONE MATCHER, ONE BASELINE: the matcher (what a construction is, which paths are read, how a count is
judged) lives in `tools/lint/check_no_direct_redis.py`, and this file tests it and runs it over the
whole tree. The `no-direct-redis` pre-commit hook and the code-quality CI step run that same module on
the changed files against the same baseline; the regex hook and `# noqa: redis` are retired.

WHAT IS A CONSTRUCTION
    A call whose callee resolves through the file's own `import redis...` / `from redis...
    import ...` bindings to `redis.*` (or the legacy `aioredis.*`) and ends in `Redis`,
    `StrictRedis`, `ConnectionPool`, `BlockingConnectionPool`, `Sentinel`, `RedisCluster`, `from_url`
    or `from_pool`. Resolving the import is what keeps SQLite / Ollama `ConnectionPool` classes out.
    Python is read from the syntax tree, so a comment, docstring or string naming `redis.Redis(` is
    not a site. Shell scripts that embed Python are read line by line with comments removed
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

import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.redis_direct_constructor_baseline_18553 import BASELINE, FROZEN_TOTAL, VERDICTS

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths
from tools.lint.check_no_direct_redis import (
    SCAN_ROOTS,
    count_sites,
    in_scope,
    is_scanned,
    main,
    python_sites,
    shell_sites,
    verdict_problems,
)


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *SCAN_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if is_scanned(rel)]


REACH = declare(
    "redis-direct-constructor-scan",
    discover=_population,
    # Mid-window, from REACH.window(): population 3827 at d050455c7e -> (3527, 3827, 3677).
    floor=3677,
    what="non-test python and shell source",
    roots=SCAN_ROOTS,
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _live() -> dict[str, int]:
    """Per-file site count over the scanned population."""
    return count_sites(repo_root(), list(REACH.examined(repo_root())))


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
    ("sentinel", "import redis\ns = redis.Sentinel([('h', 1)])\n", 1),
    ("sentinel from submodule", "from redis.sentinel import Sentinel\ns = Sentinel([('h', 1)])\n", 1),
    ("cluster", "import redis\nc = redis.RedisCluster(host='h')\n", 1),
    ("cluster from submodule", "from redis.cluster import RedisCluster\nc = RedisCluster(host='h')\n", 1),
    ("from_pool on class", "import redis\nc = redis.Redis.from_pool(p)\n", 1),
    ("from_pool on asyncio alias", "import redis.asyncio as aioredis\nc = aioredis.Redis.from_pool(p)\n", 1),
    ("from_pool on an unrelated class", "from mylib import Client\nc = Client.from_pool(p)\n", 0),
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
        ("s = redis.sentinel.Sentinel(nodes)\n", 1),
        ("c = redis.cluster.RedisCluster(host=h)\n", 1),
        ("c = redis.asyncio.Redis.from_pool(p)\n", 1),
        ("c = Redis.from_pool(p)\n", 1),
        ("# r = redis.Redis(host=h)\n", 0),
        ("r = redis.Redis(host=h)  # kept\nx = 1\n", 1),
        ("echo 'no direct redis'\n", 0),
        # embedded python goes through the SAME predicate as a .py file (#18553)
        ('python -c "from redis import Redis as R; R()"\n', 1),
        ("python3 -c 'import redis as r; r.Redis()'\n", 1),
        ("python3 -c 'from redis import Redis; Redis(host=1)'\n", 1),
        ("python3 -c 'import redis; redis.connection.ConnectionPool()'\n", 1),
        ("python3 -c 'import redis.asyncio; redis.asyncio.connection.ConnectionPool()'\n", 1),
        ("python3 - <<'EOF'\nimport redis as r\nx = 1\nc = r.Redis()\nEOF\n", 1),
        ("python <<-EOF\n\tfrom redis import Redis as R\n\tR()\n\tEOF\n", 1),
        ('python3 -c "import redis\nredis.Redis()"\n', 1),
        ("python3 -c 'import redis; redis.Redis(); redis.from_url(u)'\n", 2),
        ("python3 -c 'print(\"redis.Redis(\")'\n", 0),
        ("python3 -c 'from mylib import Redis; Redis()'\n", 0),
        ("python3 - <<'EOF'\nx = 'redis.Redis('\nEOF\nredis-cli -n 1 ping\n", 0),
        ("python3 - <<EOF\nimport redis\nc = redis.Redis(host='${H}')\nEOF\n", 1),  # unparseable body: regex fallback
        ("#!/bin/sh\nset -e\nredis-cli ping\npython3 -m pytest\n", 0),
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
    assert is_scanned(rel) is expected


def test_the_hook_population_is_the_scan_roots_minus_the_exempt_and_tests() -> None:
    assert in_scope("autobot-infrastructure/shared/scripts/x.py") is True  # the old hook skipped this tree
    assert in_scope("autobot-backend/api/terminal.py") is True
    assert in_scope("docs/x.py") is False  # not under a scan root
    assert in_scope("autobot_shared/redis_client.py") is False
    assert in_scope("autobot-backend/tests/test_x.py") is False


def _run_main_on(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rel: str, source: str) -> int:
    (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / rel).write_text(source, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return main([rel])


def test_the_hook_entry_point_fails_a_new_site_and_passes_a_clean_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The pre-commit hook and the CI step call `main` -- the same matcher and baseline as this guard."""
    rel = "autobot-backend/api/new_module.py"
    assert _run_main_on(monkeypatch, tmp_path, rel, "import redis\nc = redis.from_url('u')\n") == 1
    assert _run_main_on(monkeypatch, tmp_path, rel, "x = 1\n") == 0


def test_the_shell_matcher_reports_embedded_python_at_its_own_line() -> None:
    source = (
        "echo a\npython3 - <<'EOF'\nimport redis\nc = redis.Redis()\nEOF\npython -c 'import redis; redis.Redis()'\n"
    )
    assert shell_sites(source, "x.sh") == [4, 6]


def test_the_hook_fails_closed_on_a_python_file_that_does_not_parse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rel = "scripts/broken_probe.py"
    assert _run_main_on(monkeypatch, tmp_path, rel, "import redis\nc = redis.Redis(\n") == 1
    out = capsys.readouterr().out
    assert f"{rel}: cannot parse (line " in out
    assert "Traceback" not in out


def test_the_hook_entry_point_no_longer_honours_noqa_redis(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rel = "scripts/new_probe.py"
    source = "import redis\nc = redis.Redis()  # noqa: redis\n"
    assert _run_main_on(monkeypatch, tmp_path, rel, source) == 1


def test_a_synthetic_new_construction_in_a_product_module_fails() -> None:
    live = {"autobot-backend/api/new_module.py": 1, "scripts/x.py": 1}
    base = {"scripts/x.py": (1, "EXCEPTION", "why")}
    assert verdict_problems(live, base) == ["NEW autobot-backend/api/new_module.py: 1 direct Redis construction(s)"]


def test_a_second_site_in_a_baselined_file_fails_and_a_removed_site_is_stale() -> None:
    base = {"scripts/x.py": (1, "MIGRATE", "slice")}
    assert verdict_problems({"scripts/x.py": 2}, base) == ["GREW scripts/x.py: 2 sites, baseline allows 1"]
    assert verdict_problems({}, base)[0].startswith("STALE scripts/x.py")
    assert verdict_problems({"scripts/x.py": 1}, base) == []


def test_the_same_construction_in_the_exempt_path_is_not_scanned_or_counted() -> None:
    assert not is_scanned("autobot_shared/redis_client.py")
    assert python_sites("import redis\nc = redis.Redis()\n") == [2]  # the matcher itself still sees it


# --- the live tree ------------------------------------------------------------------------------


def test_the_scan_is_not_vacuous() -> None:
    live = _live()
    # Reach is REACH.floor's job (the scanned population); a count of files WITH findings is not reach,
    # and it falls as sites are drained. Non-vacuity is proven by the named files the scan must reach.
    assert "autobot-npu-worker/resources/windows-npu-worker/app/utils/redis_client.py" in live
    assert "autobot-slm-backend/ansible/deploy-native.sh" in live, "shell-embedded python must be reached"


def test_no_new_direct_redis_client_outside_the_canonical_layer() -> None:
    problems = verdict_problems(_live(), BASELINE)
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
        assert is_scanned(rel), f"{rel} is baselined but the scan would not read it"
