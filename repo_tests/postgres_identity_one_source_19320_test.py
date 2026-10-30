# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One home for every Postgres database, role and host default (#19320).

``autobot_shared/postgres_identity.py`` is the table. Two rules hold it there:

* **Python derives.** A tracked, non-test Python file may not carry a literal
  default for a Postgres env var (``os.getenv("AUTOBOT_POSTGRES_DB", "autobot")``,
  ``Field(default="autobot", alias=...)``, ``EnvVarSpec(name=..., default=...)``),
  a literal ``postgres_db``/``postgres_user``/``postgres_host`` attribute, a
  literal ``default_user``/``default_db`` for ``assemble_postgres_url``, a
  ``parsed.username or "slm_app"`` fallback, or a literal DSN with a user. It
  imports the identity name instead. The only exemption is a script installed
  standalone (no ``autobot_shared`` on its path), whose literal must EQUAL the
  identity value for that variable.
* **Everything else is pinned.** Ansible, compose, env files, SQL and shell
  cannot import Python, so every literal they give a Postgres key, DSN, psql
  flag, ``CREATE DATABASE`` or uninstall list must be a value the table names
  for that concept.

Before #19320 the backend role had three spellings (``autobot``, ``slm_app``,
``autobot_app``) and the user-management DB two (``autobot``, ``autobot_users``).
The contrast tests rebuild those copies and require each detector to fail.
"""

from __future__ import annotations

import ast
import re

import pytest
import yaml
from repo_tests._paths import repo_root

from autobot_shared import postgres_identity as pg
from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()

_USERS_HOSTS = {pg.USERS_DB_HOST, pg.COMPOSE_DB_HOST}
_SLM_HOSTS = {pg.SLM_DB_HOST, pg.COMPOSE_DB_HOST}
#: Postgres key -> the values the identity table allows for it. AUTOBOT_DB_USER/NAME as
#: literals exist only in compose files, as deprecated aliases (#19408).
KEY_VALUES: dict[str, set[str]] = {
    "AUTOBOT_POSTGRES_DB": {pg.USERS_DB_NAME},
    "AUTOBOT_USERS_DB_NAME": {pg.USERS_DB_NAME},
    "backend_postgres_db": {pg.USERS_DB_NAME},
    "autobot_db_name": {pg.USERS_DB_NAME},
    "AUTOBOT_POSTGRES_USER": {pg.USERS_DB_ROLE},
    "backend_postgres_user": {pg.USERS_DB_ROLE},
    "autobot_db_user": {pg.USERS_DB_ROLE},
    "AUTOBOT_POSTGRES_HOST": _USERS_HOSTS,
    "backend_postgres_host": {pg.USERS_DB_HOST},
    "AUTOBOT_DB_HOST": {pg.USERS_DB_HOST},
    "SLM_POSTGRES_USER": {pg.SLM_DB_ROLE},
    "SLM_DB_USER": {pg.SLM_DB_ROLE},
    "SLM_POSTGRES_DB": {pg.SLM_USERS_DB_NAME},
    "SLM_DB_NAME": {pg.SLM_DB_NAME},
    "SLM_POSTGRES_HOST": _SLM_HOSTS,
    "SLM_DB_HOST": {pg.SLM_DB_HOST},
    "AUTOBOT_DB_USER": {pg.COMPOSE_OWNER_ROLE},
    "AUTOBOT_DB_NAME": {pg.COMPOSE_SLM_DB_NAME},
    "db_user": {pg.SLM_DB_ROLE, pg.USERS_DB_ROLE},
}
#: The same concept with compose's value, allowed in compose files ONLY (ARCHITECTURE_EXCEPTIONS.md, #19408).
COMPOSE_KEY_VALUES: dict[str, set[str]] = {
    "AUTOBOT_POSTGRES_USER": {pg.COMPOSE_OWNER_ROLE},
    "SLM_DB_NAME": {pg.COMPOSE_SLM_DB_NAME},
}
_COMPOSE_PREFIXES = ("docker-compose", "docker/")
_PORT_KEYS = {"AUTOBOT_POSTGRES_PORT", "SLM_POSTGRES_PORT", "SLM_DB_PORT", "AUTOBOT_DB_PORT"}
DBS = {pg.USERS_DB_NAME, pg.SLM_DB_NAME, pg.SLM_USERS_DB_NAME, pg.COMPOSE_SLM_DB_NAME, "postgres"}
ROLES = {pg.USERS_DB_ROLE, pg.SLM_DB_ROLE, pg.COMPOSE_OWNER_ROLE, "postgres"}

#: Installed as a bare script (``/usr/local/bin/autobot-admin``), outside autobot_shared's path.
STANDALONE = {"autobot-slm-backend/scripts/autobot-admin.py"}
_TEST_PATH = re.compile(r"(^|/)tests?/|_test\.py$|(^|/)test_[^/]*\.py$|(^|/)conftest\.py$")
_TEXT_ROOTS = ("autobot-slm-backend/ansible/", "docker/", "autobot-infrastructure/")
_TEXT_FILES = {".env.example", "install.sh", "scripts/uninstall.sh"}
_TEXT_SUFFIXES = (".yml", ".yaml", ".j2", ".sh", ".sql", ".env", ".docker", ".example")


def _tracked(pattern: str) -> list[str]:
    return tracked_paths(_ROOT, pattern)


# --- Python: derive, never copy --------------------------------------------------------------------

_PY_ENV = re.compile(r"^(AUTOBOT|SLM)_(POSTGRES_(DB|USER|HOST|PORT)|DB_(NAME|USER|HOST|PORT))$")
_PY_ATTRS = {"postgres_db", "postgres_user", "postgres_host", "postgres_port"}
_PY_KWARGS = {"default_user", "default_db", "default_host", "default_port"}
#: The URL helper whose ``default_*`` keywords are Postgres identity values.
_ASSEMBLER = "assemble_postgres_url"
_DSN_USER_DB = re.compile(r"postgres(?:ql)?(?:\+\w+)?://([A-Za-z_]\w*)(?::[^@\s]*)?@[^/\s]+/([A-Za-z_]\w*)")


def _literal(node: ast.AST | None) -> object | None:
    """A str/int constant's value; ``None`` for anything derived, and for ``""`` (no default)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int)) and node.value != "":
        return node.value
    return None


def _env_name(call: ast.Call) -> str | None:
    for arg in [*call.args, *(k.value for k in call.keywords if k.arg in {"name", "alias"})]:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and _PY_ENV.match(arg.value):
            return arg.value
    return None


def _func_name(call: ast.Call) -> str:
    func = call.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def _call_findings(call: ast.Call) -> list[tuple[str, object]]:
    kwargs = [k for k in call.keywords if _func_name(call) == _ASSEMBLER and k.arg in _PY_KWARGS]
    found = [(k.arg, v) for k in kwargs if (v := _literal(k.value)) is not None]
    name = _env_name(call)
    if name is None:
        return found
    rest = [a for a in call.args if _literal(a) != name] + [k.value for k in call.keywords if k.arg == "default"]
    return found + [(name, v) for a in rest if (v := _literal(a)) is not None]


def _node_findings(node: ast.AST, docstrings: set[int]) -> list[tuple[str, object]]:
    if isinstance(node, ast.Call):
        return _call_findings(node)
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in _PY_ATTRS:
        return [(node.target.id, v)] if (v := _literal(node.value)) is not None else []
    if isinstance(node, ast.FunctionDef) and node.name == _ASSEMBLER:
        args = node.args
        pairs = zip(reversed(args.args + args.kwonlyargs), reversed(args.defaults + args.kw_defaults))
        return [(a.arg, v) for a, d in pairs if a.arg in _PY_KWARGS and (v := _literal(d)) is not None]
    if isinstance(node, ast.BoolOp) and isinstance(node.values[0], ast.Attribute):
        v = _literal(node.values[-1])
        return [(node.values[0].attr, v)] if node.values[0].attr == "username" and v in ROLES | DBS else []
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
        names = {n for pair in _DSN_USER_DB.findall(node.value) for n in pair}
        return [("dsn", node.value)] if names & (ROLES | DBS) else []
    return []


def python_findings(rel: str, source: str) -> list[str]:
    """Every literal Postgres default in one Python file, as ``path:line: key=value``."""
    tree = ast.parse(source)
    docstrings = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
    out = []
    for node in ast.walk(tree):
        for key, value in _node_findings(node, docstrings):
            if rel in STANDALONE and _standalone_ok(key, value):
                continue
            out.append(f"{rel}:{getattr(node, 'lineno', 0)}: {key}={value!r}")
    return out


def _standalone_ok(key: str, value: object) -> bool:
    if key in _PORT_KEYS:
        return str(value) == str(pg.DB_PORT)
    return str(value) in KEY_VALUES.get(key, set())


# --- Ansible / compose / env / SQL / shell: pinned to the table ---------------------------------------

_KEYS = "|".join(sorted(KEY_VALUES, key=len, reverse=True))
_TEXT_RULES = (
    ("jinja", re.compile(rf"\b({_KEYS})\s*\|\s*default\(\s*['\"]([^'\"]*)['\"]")),
    ("interp", re.compile(rf"\$\{{({_KEYS}):?-([^}}$]*)\}}")),
    ("assign", re.compile(rf"^[\s#-]*(?:export\s+)?({_KEYS})\s*[=:]\s*[\"']?([\w.-]+)[\"']?\s*$", re.M)),
)
_DSN = re.compile(r"postgres(?:ql)?(?:\+\w+)?://([A-Za-z_]\w*)(?::[^@\s]*)?@[^/\s]+/([A-Za-z_]\w*)")
_PSQL_FLAG = re.compile(r"\b(?:psql|pg_dump|pg_isready)\b.*?-U\s+([A-Za-z_]\w*)(?:.*?\s-d\s+([A-Za-z_]\w*))?")
_SQL_DB = re.compile(r"CREATE DATABASE\s+(\w+)")
_SHELL_LIST = re.compile(r"\b(DATABASES|DB_ROLES)=\(([^)]*)\)")


def _key_findings(text: str, compose: bool = False) -> tuple[int, list[str]]:
    seen, bad = 0, []
    for _, rule in _TEXT_RULES:
        for m in rule.finditer(text):
            seen += 1
            allowed = KEY_VALUES[m.group(1)] | (COMPOSE_KEY_VALUES.get(m.group(1), set()) if compose else set())
            if m.group(2) and "{{" not in m.group(2) and m.group(2) not in allowed:
                bad.append(f"{m.group(1)}={m.group(2)!r}")
    return seen, bad


def _name_findings(text: str) -> tuple[int, list[str]]:
    pairs = [(u, ROLES) for u, _ in _DSN.findall(text)] + [(d, DBS) for _, d in _DSN.findall(text)]
    for line in text.splitlines():
        if m := _PSQL_FLAG.search(line):
            pairs += [(m.group(1), ROLES)] + ([(m.group(2), DBS)] if m.group(2) else [])
    pairs += [(d, DBS) for d in _SQL_DB.findall(text)]
    for kind, items in _SHELL_LIST.findall(text):
        pairs += [(i, DBS if kind == "DATABASES" else ROLES) for i in items.split()]
    return len(pairs), [f"name {v!r}" for v, allowed in pairs if v not in allowed]


def _yaml_findings(text: str) -> tuple[int, list[str]]:
    """pg_hba entries ({database, user, address}) and ``databases``/``db`` lists name known DBs and roles."""
    seen, bad, stack = 0, [], [d for d in yaml.safe_load_all(text) if d is not None]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
            continue
        if not isinstance(node, dict):
            continue
        stack.extend(node.values())
        checks = _yaml_checks(node)
        seen += len(checks)
        bad += [f"name {v!r}" for v, allowed in checks if v not in allowed]
    return seen, bad


def _yaml_checks(node: dict) -> list[tuple[str, set[str]]]:
    lit = [str(v) for v in (node.get("databases") if isinstance(node.get("databases"), list) else [])]
    checks = [(v, DBS | {"all"}) for v in lit if not v.isdigit() and "{{" not in v]
    if isinstance(node.get("db"), str) and "{{" not in node["db"]:
        checks.append((node["db"], DBS))
    if {"database", "user", "address"} <= node.keys():
        checks += [(str(node["database"]), DBS | {"all"}), (str(node["user"]), ROLES | {"all"})]
    return [(v, allowed) for v, allowed in checks if "{{" not in v]


def text_findings(rel: str, text: str) -> tuple[int, list[str]]:
    """(sites examined, conflicting literals) for one non-Python provisioning file."""
    results = [_key_findings(text, rel.startswith(_COMPOSE_PREFIXES)), _name_findings(text)]
    if rel.endswith((".yml", ".yaml")) and rel.startswith("autobot-slm-backend/ansible/"):
        results.append(_yaml_findings(text))
    return sum(n for n, _ in results), [f"{rel}: {b}" for _, found in results for b in found]


def _text_paths() -> list[str]:
    paths = [p for p in _tracked("*") if p in _TEXT_FILES or p.startswith("docker-compose")]
    paths += [p for p in _tracked("*") if p.startswith(_TEXT_ROOTS) and p.endswith(_TEXT_SUFFIXES)]
    return sorted({p for p in paths if not _TEST_PATH.search(p)})


def _python_paths() -> list[str]:
    own = {"autobot_shared/postgres_identity.py"}
    return [p for p in _tracked("*.py") if not _TEST_PATH.search(p) and p not in own and not p.startswith("docs/")]


# --- live tree --------------------------------------------------------------------------------------


def test_no_python_file_carries_a_literal_postgres_default() -> None:
    paths, found = _python_paths(), []
    for rel in paths:
        found += python_findings(rel, (_ROOT / rel).read_text(encoding="utf-8"))
    # Floor (#19660): 4009 tracked non-test Python files on main at c1312f2eec; a sweep that read
    # almost nothing is a broken enumeration, not a clean tree.
    assert len(paths) >= 3000, f"only {len(paths)} Python files swept -- the enumeration lost its reach"
    assert found == [], "import the value from autobot_shared.postgres_identity:\n" + "\n".join(found)


def test_every_provisioning_literal_is_a_value_the_identity_table_names() -> None:
    examined, found = 0, []
    for rel in _text_paths():
        n, bad = text_findings(rel, (_ROOT / rel).read_text(encoding="utf-8"))
        examined, found = examined + n, found + bad
    # Floor: the pinned population is ~70 sites (ansible, compose, env files, SQL, shell); a sweep
    # that matched almost nothing is a broken detector, not a clean tree.
    assert examined >= 50, f"only {examined} Postgres sites examined -- the detector lost its reach"
    assert found == [], "conflicts with autobot_shared/postgres_identity.py:\n" + "\n".join(found)


def test_the_standalone_exemption_still_names_an_existing_script() -> None:
    assert all((_ROOT / rel).is_file() for rel in STANDALONE)


# --- contrast: each detector fails on the copies #19320 removed ---------------------------------------


def test_python_detector_flags_each_removed_copy() -> None:
    src = (
        "import os\nfrom pydantic import Field\n"
        'a = os.getenv("AUTOBOT_POSTGRES_DB", "autobot")\n'
        'b = Field(default="autobot", alias="AUTOBOT_POSTGRES_USER")\n'
        'c = EnvVarSpec(name="AUTOBOT_POSTGRES_USER", type=str, default="slm_app")\n'
        'class D:\n    postgres_db: str = "autobot"\n'
        'def assemble_postgres_url(source, default_user: str = "autobot"):\n    return parsed.username or "slm_app"\n'
        'URL = "postgresql+asyncpg://slm_app@127.0.0.1:5432/slm"\n'
    )
    keys = [line.split(": ", 1)[1].split("=")[0] for line in python_findings("x.py", src)]
    expected = ["AUTOBOT_POSTGRES_DB", "AUTOBOT_POSTGRES_USER", "AUTOBOT_POSTGRES_USER", "postgres_db"]
    assert sorted(keys) == sorted(expected + ["default_user", "username", "dsn"])


def test_python_detector_passes_derived_defaults_and_a_matching_standalone_literal() -> None:
    src = (
        'import os\nx = os.getenv("AUTOBOT_POSTGRES_DB", pg.USERS_DB_NAME)\ny = os.getenv("AUTOBOT_DB_HOST", "")\n'
        'r = redis.username or "default"\nprobe(default_port=6379)\nP = "Database URLs: postgresql://user:pass@host/db"\n'  # pragma: allowlist secret
    )
    assert python_findings("x.py", src) == []
    script = 'n = env.get("SLM_DB_NAME", "slm")\nu = env.get("SLM_DB_USER", "autobot")\n'
    assert python_findings(next(iter(STANDALONE)), script) == [f"{next(iter(STANDALONE))}:2: SLM_DB_USER='autobot'"]


def test_text_detector_flags_each_removed_copy() -> None:
    text = (
        'backend_postgres_user: "autobot"\n'
        "AUTOBOT_POSTGRES_USER={{ backend_postgres_user | default('slm_app') }}\n"
        "DUMP=${AUTOBOT_POSTGRES_DB:-autobot}\n"
        "# AUTOBOT_POSTGRES_DB=autobot\n"
        "URL=postgresql://autobot@127.0.0.1:5432/autobot\n"
        "CREATE DATABASE autobot;\n"
    )
    _, bad = text_findings("autobot-slm-backend/ansible/x.yml.j2", text)
    assert len(bad) == 6, bad


def test_text_detector_passes_the_identity_values() -> None:
    text = (
        f'backend_postgres_user: "{pg.USERS_DB_ROLE}"\n'
        f"AUTOBOT_POSTGRES_DB={{{{ backend_postgres_db | default('{pg.USERS_DB_NAME}') }}}}\n"
        f"- AUTOBOT_POSTGRES_USER=${{AUTOBOT_DB_USER:-{pg.COMPOSE_OWNER_ROLE}}}\n"
        f"psql -h 127.0.0.1 -U {pg.SLM_DB_ROLE} -d {pg.SLM_DB_NAME}\n"
    )
    n, bad = text_findings("docker-compose.yml", text)
    assert bad == [] and n >= 5, (n, bad)


def test_yaml_detector_flags_a_wrong_pg_hba_role() -> None:
    rel = "autobot-slm-backend/ansible/playbooks/x.yml"
    text = "pg_hba_remote_access:\n  - database: autobot_users\n    user: autobot_svc\n    address: 10.0.0.0/24\n"
    n, bad = text_findings(rel, text)
    assert n >= 2 and bad == [f"{rel}: name 'autobot_svc'"], (n, bad)


@pytest.mark.parametrize(
    "line", [f"AUTOBOT_POSTGRES_USER={pg.COMPOSE_OWNER_ROLE}", f"SLM_DB_NAME={pg.COMPOSE_SLM_DB_NAME}"]
)
def test_a_compose_value_passes_in_compose_and_fails_on_the_fleet(line: str) -> None:
    """#19408: the allowance is scoped to the file, or a fleet template could adopt compose's value."""
    assert text_findings("docker/.env.docker", line + "\n")[1] == []
    rel = "autobot-slm-backend/ansible/roles/x/templates/x.env.j2"
    assert text_findings(rel, line + "\n")[1] != []
