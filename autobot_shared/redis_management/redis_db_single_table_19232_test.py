# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: ONE name -> Redis database number table in production Python (#19232).

``redis-databases.yaml`` (+ ``AUTOBOT_REDIS_DB_*`` overrides) is the table, mirrored only
by ``types._FALLBACK_MAPPING`` for a checkout without the YAML; the mirror is pinned to the
YAML by ``autobot-infrastructure/shared/tests/test_redis_db_ssot.py``. Every other reader
goes through ``database_names.database_number``.

A second table looks like one of the shapes #19232 removed:

* a dict literal mapping two or more database names (or their ``AUTOBOT_REDIS_DB_*``
  variables) to number literals -- ``cache_management.REDIS_DATABASES`` had
  ``sessions: 4`` and ``analytics: 9`` while the client used 6 and 11;
* a class body assigning number literals to two or more database names -- an enum copy;
* a settings field whose alias is an ``AUTOBOT_REDIS_DB_*`` variable and whose default is a
  number -- ``ssot_config.RedisConfig.db_*``, which moved the backend's readers but not the
  canonical client;
* a second redis-databases.yaml path list -- ``types`` and ``RedisConfigLoader`` each had
  one, with different candidates, so the table and the per-database tuning could read
  different files. ``types.resolve_databases_yaml`` is the one resolver;
* a second Redis URL builder -- a ``redis://``/``rediss://`` literal or f-string outside
  ``endpoint.py`` (``NetworkConstants`` ``REDIS_VM``/``REDIS_LOCAL``, a PKI ``rediss://..:6380``);
* a shell/compose/env/Ansible copy -- ``${AUTOBOT_REDIS_DB_CELERY_BROKER:-14}``,
  ``AUTOBOT_REDIS_DB_LOGS=5`` in an installer, or a URL with a literal ``/<db>``.

Each shape is shown FAILING against a deliberately re-added copy before the tree is swept,
so a green sweep is not a detector that matches nothing.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

from autobot_shared.redis_management.database_overrides import LEGACY_ENV_NAMES, env_var_name
from autobot_shared.redis_management.types import _ALIASES, _FALLBACK_MAPPING

_REPO = Path(__file__).resolve().parents[2]
_ROOTS = ("autobot_shared", "autobot-backend", "autobot-slm-backend", "autobot-slm-agent", "autobot-infrastructure")
#: migrations/alembic are history: a past revision is not rewritten (the fork scan skips them too).
_SKIP_DIRS = {"node_modules", ".git", "__pycache__", "venv", ".venv", "tests", "test", "migrations", "alembic"}
#: (repo-relative path, assigned name) of the one allowed literal mirror.
_ALLOWED = {("autobot_shared/redis_management/types.py", "_FALLBACK_MAPPING")}
#: The one file allowed to spell the YAML's file name as a path.
_YAML_RESOLVER = "autobot_shared/redis_management/types.py"
#: Readers that cannot import it, so they read the same file themselves: the Ansible dynamic
#: inventory runs under Ansible's interpreter without autobot_shared (#1086).
_STANDALONE_YAML_READERS = {_YAML_RESOLVER, "autobot-slm-backend/ansible/inventory/dynamic/generate_inventory.py"}
_YAML_NAME = "redis-databases.yaml"

#: The one URL builder, and a validator that checks an env FILE's URL against that file's own
#: host/port (it has no process environment to resolve from).
_URL_BUILDERS = {
    "autobot_shared/redis_management/endpoint.py",
    # Declares the "redis" scheme LABEL of the service catalogue; its base_url() for redis
    # delegates to the resolver (#19232).
    "autobot_shared/service_registry_core.py",
    # SLM fleet inventory: a "redis" protocol label per discovered node service, rendered by the
    # generic api/discovery.py listing. Fleet metadata about remote nodes, not a client endpoint.
    "autobot-slm-backend/services/compose_fleet.py",
}
_REDIS_SCHEMES = ("redis", "rediss")
_CONFIG_SUFFIXES = (".sh", ".yml", ".yaml", ".j2", ".service", ".conf")
#: A DB number pinned in config: `${X:-14}`, `: "${X:=14}"`, `X=14`, `X: 14`.
_CONFIG_DB_LITERAL = re.compile(r"AUTOBOT_REDIS_DB_[A-Z_]+\s*(?::?[-=]|:)\s*['\"]?\d")
#: A generic ``REDIS_DB`` pinned to a number: ``REDIS_DB=0``, ``${REDIS_DB:-0}``.
_GENERIC_DB_LITERAL = re.compile(r"(?<![A-Z_])REDIS_DB\s*(?::?[-=]|:)\s*['\"]?\d")
#: A Redis URL naming its database by number.
_URL_DB_LITERAL = re.compile(r"rediss?://[^\s\"'`]*/\d+\b")

_NAMES = set(_FALLBACK_MAPPING) | set(_ALIASES)
_KEYS = _NAMES | {env_var_name(n) for n in _NAMES} | set(LEGACY_ENV_NAMES)


def _is_number(node: ast.AST | None) -> bool:
    """An int literal, or a string literal of digits (env-file style)."""
    if not isinstance(node, ast.Constant) or isinstance(node.value, bool):
        return False
    return isinstance(node.value, int) or (isinstance(node.value, str) and node.value.isdigit())


def _dict_hits(node: ast.Dict) -> int:
    """How many entries of *node* map a database key to a number literal."""
    return sum(
        1
        for key, value in zip(node.keys, node.values)
        if isinstance(key, ast.Constant) and key.value in _KEYS and _is_number(value)
    )


def _class_hits(node: ast.ClassDef) -> int:
    """How many class-body assignments give a database name a number literal."""
    return sum(
        1
        for stmt in node.body
        if isinstance(stmt, ast.Assign)
        and _is_number(stmt.value)
        and any(isinstance(t, ast.Name) and t.id.lower().removesuffix("_db") in _NAMES for t in stmt.targets)
    )


def _is_db_field(node: ast.Call) -> bool:
    """``Field(default=<number>, alias="AUTOBOT_REDIS_DB_...")``."""
    kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
    alias = kwargs.get("alias")
    is_db_alias = isinstance(alias, ast.Constant) and str(alias.value).startswith("AUTOBOT_REDIS_DB_")
    return is_db_alias and _is_number(kwargs.get("default"))


def _is_yaml_path(node: ast.AST) -> bool:
    """A string literal naming redis-databases.yaml as a file or path (not prose mentioning it)."""
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.split("/")[-1] == _YAML_NAME


def _url_prefix(node: ast.AST) -> str | None:
    """The leading text of a string literal or f-string, else None."""
    if isinstance(node, ast.JoinedStr) and node.values:
        node = node.values[0]
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _is_url_builder(node: ast.AST) -> bool:
    """Code that composes a Redis URL, however it is spelled.

    * a literal longer than the bare scheme, or any f-string, starting ``redis:``/``rediss:``
      (a bare ``"redis://"`` constant is a scheme, as in a prefix check);
    * ``"redis" + "://" + ...`` concatenation;
    * ``scheme``/``protocol`` set to ``"redis"`` -- a dict entry or a keyword -- which some
      generic ``f"{scheme}://{host}:{port}"`` builder turns into a Redis URL.
    """
    prefix = _url_prefix(node)
    if isinstance(node, ast.JoinedStr) and prefix is not None and prefix.startswith(("redis:", "rediss:")):
        return True
    if isinstance(node, ast.Constant) and prefix is not None and prefix.startswith(("redis://", "rediss://")):
        return prefix not in ("redis://", "rediss://")  # "redis:read" is a capability, not a URL
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        parts = [p.value for p in (node.left, node.right) if isinstance(p, ast.Constant) and isinstance(p.value, str)]
        return any(p in _REDIS_SCHEMES or p in ("redis:", "rediss:") for p in parts) and any(
            p.startswith(("://", "//")) for p in parts
        )
    return _names_redis_scheme(node)


def _names_redis_scheme(node: ast.AST) -> bool:
    """``{"scheme": "redis"}`` / ``f(protocol="redis")``."""

    def _is_redis(value: ast.AST | None) -> bool:
        return isinstance(value, ast.Constant) and value.value in _REDIS_SCHEMES

    if isinstance(node, ast.Dict):
        return any(
            isinstance(k, ast.Constant) and k.value in ("scheme", "protocol") and _is_redis(v)
            for k, v in zip(node.keys, node.values)
        )
    if isinstance(node, ast.Call):
        return any(kw.arg in ("scheme", "protocol") and _is_redis(kw.value) for kw in node.keywords)
    return False


def _is_db_number_literal(node: ast.AST) -> bool:
    """``{"db": 2}`` or ``f(db=2)`` -- a Redis database chosen by number, not through the table."""
    if isinstance(node, ast.Dict):
        return any(
            isinstance(k, ast.Constant) and k.value == "db" and _is_number(v) for k, v in zip(node.keys, node.values)
        )
    if isinstance(node, ast.Call):
        return any(kw.arg == "db" and _is_number(kw.value) for kw in node.keywords)
    return False


def _assigned_names(tree: ast.AST) -> dict[int, str]:
    """``{id(dict node): target name}`` for dicts assigned straight to a name."""
    names: dict[int, str] = {}
    for node in ast.walk(tree):
        target = node.targets[0] if isinstance(node, ast.Assign) else getattr(node, "target", None)
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(target, ast.Name):
            names[id(node.value)] = target.id
    return names


def find_tables(source: str, path: str) -> list[str]:
    """``path:line kind`` for every name -> number table in *source* the allowlist does not cover."""
    tree = ast.parse(source)
    assigned = _assigned_names(tree)
    in_fstring = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
    found: list[str] = []
    for node in ast.walk(tree):
        if _is_db_number_literal(node):
            found.append(f"{path}:{node.lineno} db number literal")
        if isinstance(node, ast.Dict) and _dict_hits(node) >= 2:
            if (path, assigned.get(id(node), "")) not in _ALLOWED:
                found.append(f"{path}:{node.lineno} dict {assigned.get(id(node), '<expr>')}")
        elif isinstance(node, ast.ClassDef) and _class_hits(node) >= 2:
            found.append(f"{path}:{node.lineno} class {node.name}")
        elif isinstance(node, ast.Call) and _is_db_field(node):
            found.append(f"{path}:{node.lineno} AUTOBOT_REDIS_DB_* field")
        elif _is_yaml_path(node) and path not in _STANDALONE_YAML_READERS:
            found.append(f"{path}:{node.lineno} yaml path")
        if _is_url_builder(node) and id(node) not in in_fstring and path not in _URL_BUILDERS:
            found.append(f"{path}:{node.lineno} redis url builder")
    return found


def find_config_literals(text: str, path: str) -> list[str]:
    """``path:line`` for every non-comment config line pinning a Redis DB number."""
    found: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if any(rx.search(line) for rx in (_CONFIG_DB_LITERAL, _GENERIC_DB_LITERAL, _URL_DB_LITERAL)):
            found.append(f"{path}:{lineno} config literal")
    return found


def _production_sources() -> list[Path]:
    """Every non-test ``.py`` under the production roots."""
    paths: list[Path] = []
    for root in _ROOTS:
        for dirpath, dirnames, filenames in os.walk(_REPO / root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            paths += [
                Path(dirpath) / f
                for f in filenames
                if f.endswith(".py") and not f.endswith("_test.py") and not f.startswith("test_") and f != "conftest.py"
            ]
    return paths


#: Browser and Node sources: a browser never dials Redis, so a Redis URL or DB number there is
#: a copy by definition (frontend redisUrl/REDIS_VM/DatabaseConstants were retired, #19232).
_SCRIPT_ROOTS = ("autobot-frontend/src", "autobot-slm-frontend/src", "autobot-infrastructure/shared/mcp")
_SCRIPT_SUFFIXES = (".ts", ".js", ".vue", ".cjs", ".mjs")
_SCRIPT_SKIP = ("__tests__", ".spec.", ".test.", ".stories.", "/tests/", "node_modules", "/dist/")
_SCRIPT_PATTERNS = (
    re.compile(r"rediss?://"),
    re.compile(r"(?:protocol|scheme)\s*:\s*['\"]rediss?['\"]"),
    re.compile(r"['\"]rediss?['\"]\s*\+\s*['\"]:?//"),
    re.compile(r"\b[A-Z_]+_DB\s*:\s*\d"),
    re.compile(r"\bdatabase\s*:\s*\d"),
)
#: Known, recorded, and NOT silently excluded: the MCP tracker stores its own data in DB 10,
#: which redis-databases.yaml assigns to the security audit log. Moving that data is a decision
#: (no agent moves stored data on its own), so these stay listed until it is made.
_SCRIPT_KNOWN = {
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/src/index.ts",
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/correlate-unfinished-tasks.cjs",
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/generate-insights.cjs",
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/ingest-conversation.cjs",
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/validate-fixes.cjs",
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/src/real-time-ingestion.ts",
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/src/knowledge-integration.ts",
}


def find_script_literals(text: str, path: str) -> list[str]:
    """``path:line`` for every non-comment TS/JS line composing a Redis URL or pinning a DB number."""
    found: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("//", "*", "/*")):
            continue
        if any(rx.search(line) for rx in _SCRIPT_PATTERNS):
            found.append(f"{path}:{lineno} script literal")
    return found


def _script_sources() -> list[Path]:
    """Every non-test browser/Node source under the script roots."""
    paths: list[Path] = []
    for root in _SCRIPT_ROOTS:
        for dirpath, dirnames, filenames in os.walk(_REPO / root):
            dirnames[:] = [d for d in dirnames if d not in {"node_modules", "dist", "__tests__", "tests"}]
            paths += [Path(dirpath) / f for f in filenames if f.endswith(_SCRIPT_SUFFIXES)]
    return [p for p in paths if not any(s in p.as_posix() for s in _SCRIPT_SKIP)]


def _config_sources() -> list[Path]:
    """Shell, compose, Ansible and env files under the production roots and the repo root."""
    paths = [p for p in _REPO.iterdir() if p.is_file() and (p.name.startswith(".env") or p.suffix in _CONFIG_SUFFIXES)]
    for root in _ROOTS:
        for dirpath, dirnames, filenames in os.walk(_REPO / root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            paths += [Path(dirpath) / f for f in filenames if f.endswith(_CONFIG_SUFFIXES) or f.startswith(".env")]
    return paths


# --- the detector, shown failing on deliberately re-added copies -------------------------

_OLD_SSOT_FIELDS = """
class RedisConfig(BaseSettings):
    db_main: int = Field(default=0, alias="AUTOBOT_REDIS_DB_MAIN")
    db_knowledge: int = Field(default=1, alias="AUTOBOT_REDIS_DB_KNOWLEDGE")
"""

_OLD_CACHE_TABLE = """
REDIS_DATABASES = {"main": 0, "knowledge": 1, "sessions": 4, "analytics": 9, "websockets": 10}
"""

_ENUM_COPY = """
class Databases(Enum):
    MAIN = 0
    KNOWLEDGE = 1
"""

_CONSTANTS_COPY = """
class DatabaseConstants:
    MAIN_DB = 0
    KNOWLEDGE_DB = 1
"""

_SECOND_YAML_RESOLVER = """
possible_paths = ["/app/config/redis-databases.yaml", os.path.join(base, "config/redis-databases.yaml")]
"""

_ENV_TABLE_COPY = """
expected_dbs = {"AUTOBOT_REDIS_DB_MAIN": "0", "AUTOBOT_REDIS_DB_TESTING": "15"}
"""


def test_detector_flags_the_retired_ssot_fields():
    assert len(find_tables(_OLD_SSOT_FIELDS, "x.py")) == 2


def test_detector_flags_the_retired_cache_management_table():
    assert find_tables(_OLD_CACHE_TABLE, "x.py") == ["x.py:2 dict REDIS_DATABASES"]


def test_detector_flags_an_enum_with_literal_numbers():
    assert find_tables(_ENUM_COPY, "x.py") == ["x.py:2 class Databases"]


def test_detector_flags_db_suffixed_constants():
    assert find_tables(_CONSTANTS_COPY, "x.py") == ["x.py:2 class DatabaseConstants"]


def test_detector_flags_a_second_yaml_path_list():
    """The RedisConfigLoader candidate list #19232 collapsed into types.resolve_databases_yaml."""
    assert len(find_tables(_SECOND_YAML_RESOLVER, "x.py")) == 2
    assert find_tables(_SECOND_YAML_RESOLVER, _YAML_RESOLVER) == []


def test_detector_flags_an_env_variable_table():
    assert find_tables(_ENV_TABLE_COPY, "x.py") == ["x.py:2 dict expected_dbs"]


def test_detector_flags_a_second_copy_of_the_fallback_inside_types_py():
    """The allowlist names ONE assignment: the same literal under another name still fails."""
    types_path = "autobot_shared/redis_management/types.py"
    source = (_REPO / types_path).read_text(encoding="utf-8")
    assert find_tables(source, types_path) == [], "the shipped types.py must pass"
    copied = source + "\n_SECOND_TABLE = " + repr(dict(_FALLBACK_MAPPING)) + "\n"
    assert len(find_tables(copied, types_path)) == 1


_SECOND_URL_BUILDERS = """
REDIS_VM = lambda: f"redis://{NetworkConstants.REDIS_VM_IP}:{NetworkConstants.REDIS_PORT}"
TLS = "rediss://10.0.0.1:6380"
PREFIXES = ("redis://", "postgresql://")
"""

_OLD_SHELL_AND_COMPOSE = """
: "${AUTOBOT_REDIS_DB_CELERY_BROKER:=14}"
CELERY_BROKER_DB="${AUTOBOT_REDIS_DB_CELERY_BROKER:-14}"
      - CELERY_BROKER_URL=redis://autobot-redis:6379/${AUTOBOT_REDIS_DB_CELERY_BROKER:-14}
AUTOBOT_REDIS_DB_LOGS=5
    AUTOBOT_REDIS_DB_TESTING: 15
# AUTOBOT_REDIS_DB_MAIN=0 is a comment, and comments are prose
AUTOBOT_REDIS_DB_MAIN="$(autobot_redis_db main)"
REDIS_DB=0
REDIS_DB=${_SLM_REDIS_DB}
"""

_DB_KWARG_COPIES = """
store = RedisVectorStore(schema=schema, redis_kwargs={"db": 2})
client = redis.Redis(host=h, port=p, db=0)
fine = redis.Redis(host=h, port=p, db=database_number("main"))
"""


def test_detector_flags_a_second_url_builder():
    """The f-string and the literal; the bare scheme in a prefix tuple is not a URL."""
    assert sorted(find_tables(_SECOND_URL_BUILDERS, "x.py")) == ["x.py:2 redis url builder", "x.py:3 redis url builder"]
    assert find_tables(_SECOND_URL_BUILDERS, "autobot_shared/redis_management/endpoint.py") == []


def test_detector_flags_shell_compose_env_and_ansible_copies():
    assert [hit.split(" ")[0] for hit in find_config_literals(_OLD_SHELL_AND_COMPOSE, "x")] == [
        "x:2",
        "x:3",
        "x:4",
        "x:5",
        "x:6",
        "x:9",
    ]


def test_detector_flags_a_db_number_kwarg():
    assert sorted(find_tables(_DB_KWARG_COPIES, "x.py")) == ["x.py:2 db number literal", "x.py:3 db number literal"]


_COMPOSED_URL_COPIES = """
a = "redis" + "://" + host
b = f"redis:{host}"
c = {"scheme": "redis", "host": h}
d = build_url(protocol="rediss", host=h)
fine = ("redis://", "http://")
capability = "redis:read"
"""

_SCRIPT_COPIES = """
REDIS_VM: `redis://${NetworkConstants.REDIS_VM_IP}:${NetworkConstants.REDIS_PORT}`,
redis: { host: h, port: p, protocol: 'redis' },
const u = 'redis' + '://' + host
export const DatabaseConstants = { MAIN_DB: 0 }
createClient({ socket: { host }, database: 10 })
// const redisUrl = `redis://${host}` -- a comment is prose
redisHost: config.vm.redis,
"""


def test_detector_flags_composed_url_builders():
    assert sorted(find_tables(_COMPOSED_URL_COPIES, "x.py")) == [f"x.py:{n} redis url builder" for n in (2, 3, 4, 5)]


def test_detector_flags_browser_and_node_copies():
    assert [hit.split(" ")[0] for hit in find_script_literals(_SCRIPT_COPIES, "x")] == [
        "x:2",
        "x:3",
        "x:4",
        "x:5",
        "x:6",
    ]


def test_browser_and_node_sources_build_no_redis_url_and_pin_no_db_number():
    sources = _script_sources()
    assert len(sources) > 300, f"sweep reached only {len(sources)} script files -- the walk is broken"
    hits = [
        h
        for p in sources
        for h in find_script_literals(p.read_text(encoding="utf-8", errors="replace"), p.relative_to(_REPO).as_posix())
    ]
    unknown = [h for h in hits if h.split(":")[0] not in _SCRIPT_KNOWN]
    assert unknown == [], "Redis URL or DB number in browser/Node code (#19232):\n" + "\n".join(unknown)
    stale = _SCRIPT_KNOWN - {h.split(":")[0] for h in hits}
    assert not stale, f"no longer a copy -- drop from _SCRIPT_KNOWN: {sorted(stale)}"


def test_detector_ignores_a_single_value():
    assert find_tables('DB = {"main": 0}\n', "x.py") == []


# --- the sweep ------------------------------------------------------------------------


def test_production_python_has_one_name_to_number_table():
    sources = _production_sources()
    assert len(sources) > 1000, f"sweep reached only {len(sources)} files -- the walk is broken, not the tree clean"
    found = [
        hit
        for path in sources
        for hit in find_tables(path.read_text(encoding="utf-8"), path.relative_to(_REPO).as_posix())
    ]
    assert found == [], "second name -> Redis DB table(s); resolve through database_number():\n" + "\n".join(found)


def test_config_files_pin_no_redis_database_number():
    sources = _config_sources()
    assert len(sources) > 100, f"sweep reached only {len(sources)} config files -- the walk is broken"
    found = [
        hit
        for path in sources
        for hit in find_config_literals(
            path.read_text(encoding="utf-8", errors="replace"), path.relative_to(_REPO).as_posix()
        )
    ]
    assert found == [], "Redis DB number pinned outside redis-databases.yaml (#19232):\n" + "\n".join(found)
