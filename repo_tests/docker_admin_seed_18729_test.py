# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A fresh Docker install has a main-app login (#18729).

The backend seeds its first platform admin from AUTOBOT_ADMIN_PASSWORD (#10199), and the
Docker path never set it: generate-secrets.sh wrote no such key and the backend's compose
`environment:` list did not pass one, so every fresh Docker stack started with no account
anyone could log in with.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._comment_syntax import code_lines, code_text
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_GENERATOR = _ROOT / "docker" / "generate-secrets.sh"


def _backend_env() -> dict[str, str]:
    compose = yaml.safe_load((_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    entries = compose["services"]["autobot-backend"]["environment"]
    return dict(e.split("=", 1) for e in entries)


def _run_generator(tmp: Path) -> tuple[str, dict[str, str]]:
    bash = shutil.which("bash")
    if bash is None or shutil.which("openssl") is None:
        pytest.skip("bash and openssl are needed to run generate-secrets.sh")
    script = tmp / "generate-secrets.sh"
    shutil.copy(_GENERATOR, script)
    env = {**os.environ, "AUTOBOT_DOCKER_MGMT_PREFIX": "10.77.3"}
    out = subprocess.run([bash, str(script)], capture_output=True, text=True, timeout=60, env=env)
    assert out.returncode == 0, out.stderr
    lines = (tmp / ".env.secrets").read_text(encoding="utf-8").splitlines()
    return out.stdout, dict(line.split("=", 1) for line in lines if "=" in line)


def test_generate_secrets_writes_an_admin_password_the_user_policy_accepts() -> None:
    from autobot_shared.user_management.schemas.user import UserCreate

    with tempfile.TemporaryDirectory() as tmp:
        stdout, secrets = _run_generator(Path(tmp))
        password = secrets["AUTOBOT_ADMIN_PASSWORD"]
        assert UserCreate.validate_password(password) == password
        assert password not in stdout, "the admin password was printed"
        assert "AUTOBOT_ADMIN_PASSWORD" in stdout, "the operator is not told where the login is"
        _, again = _run_generator(Path(tmp))
        assert again["AUTOBOT_ADMIN_PASSWORD"] == password, "a re-run replaced the admin password"


def test_the_admin_password_reaches_the_backend_container() -> None:
    env = _backend_env()
    assert re.fullmatch(r"\$\{AUTOBOT_ADMIN_PASSWORD(:-)?\}", env.get("AUTOBOT_ADMIN_PASSWORD", "")), env.get(
        "AUTOBOT_ADMIN_PASSWORD"
    )


def _user_mode_defaults() -> dict[str, str]:
    """{service: its AUTOBOT_USER_MODE default} for every compose service that sets one."""
    compose = yaml.safe_load((_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    found = {}
    for name, service in compose["services"].items():
        env = service.get("environment") or []
        entries = dict(e.split("=", 1) for e in env if "=" in e) if isinstance(env, list) else env
        value = str(entries.get("AUTOBOT_USER_MODE", ""))
        if value:
            match = re.fullmatch(r"\$\{AUTOBOT_USER_MODE:-(\w+)\}", value)
            found[name] = match.group(1) if match else value
    return found


def test_every_compose_user_mode_default_is_a_mode_the_backend_accepts() -> None:
    """Every service, not just the backend: autobot-worker kept the retired default (#18729)."""
    source = (_ROOT / "autobot-backend" / "user_management" / "config.py").read_text(encoding="utf-8")
    enum = re.search(r"class UserManagementMode\(str, Enum\):(.*?)\n\n\n", source, re.S).group(1)
    modes = set(re.findall(r'=\s*"(\w+)"', enum))
    defaults = _user_mode_defaults()
    assert {"autobot-backend", "autobot-worker"} <= set(defaults), defaults
    wrong = {s: d for s, d in defaults.items() if d not in modes}
    assert modes and not wrong, f"not one of {sorted(modes)} -- retired single_user? (#10636): {wrong}"


def runnable_pulls(markdown: str) -> set[str]:
    """Models pulled by uncommented ``ollama pull`` lines inside fenced bash/sh blocks."""
    blocks = re.findall(r"^```(?:bash|sh|shell)\n(.*?)^```", markdown, re.S | re.M)
    return {
        m
        for b in blocks
        for line in code_lines(b, name="block.sh", strip_trailing=True)
        for m in re.findall(r"\bollama pull (\S+)", line.text)
    }


def test_runnable_pulls_contrast() -> None:
    live = "```bash\nollama pull a:1\n```\n"
    assert runnable_pulls(live) == {"a:1"}
    assert runnable_pulls("```bash\n# ollama pull a:1\n```\n") == set()
    assert runnable_pulls("prose: ollama pull a:1\n") == set()


def test_install_md_pulls_the_models_docker_env_names() -> None:
    names = dict(
        line.split("=", 1)
        for line in (_ROOT / "docker" / ".env.docker").read_text(encoding="utf-8").splitlines()
        if line.startswith(("AUTOBOT_DEFAULT_LLM_MODEL=", "AUTOBOT_EMBEDDING_MODEL="))
    )
    pulled = runnable_pulls((_ROOT / "INSTALL.md").read_text(encoding="utf-8"))
    assert len(names) == 2 and set(names.values()) <= pulled, (names, pulled)


#: A default or example naming the retired mode (#10636): `AUTOBOT_USER_MODE=single_user`,
#: `${AUTOBOT_USER_MODE:-single_user}`, or a shell branch on it.
_RETIRED_MODE = re.compile(r"AUTOBOT_USER_MODE(?:=|:-)\s*[\"']?single_user|USER_MODE[\"']?\s*!?=+\s*[\"']?single_user")


def retired_mode_sites(files: dict[str, str]) -> list[str]:
    return sorted(
        f"{p}:{n}"
        for p, text in files.items()
        for n, line in enumerate(text.splitlines(), 1)
        if _RETIRED_MODE.search(line)
    )


def _mode_carriers(root: Path) -> list[str]:
    """Compose files, Docker entrypoints and env templates -- where a user-mode default lives."""
    try:
        return tracked_paths(root, "docker-compose*.yml", "docker/*/*entrypoint*.sh", ".env*", "*/.env*")
    except EmptyEnumeration:
        return []


REACH = declare(
    "user-mode-default-carriers-18729",
    discover=_mode_carriers,
    # Mid-window from REACH.window(): population 15, window (11, 15) -> 13.
    floor=13,
    growth=4,
    what="compose files, Docker entrypoints and env templates",
    roots=(".env", "autobot-frontend/", "autobot-slm-backend/", "docker-compose", "docker/"),
)


def test_no_compose_file_entrypoint_or_env_template_defaults_to_single_user() -> None:
    """01's review of #18804: the entrypoint fallback and .env.example's example kept it too."""
    files = {p: (_ROOT / p).read_text(encoding="utf-8") for p in REACH.examined(_ROOT)}
    assert (
        "docker/backend/entrypoint.sh" in files and ".env.example" in files and "docker-compose.yml" in files
    ), sorted(files)
    assert not retired_mode_sites(files)


def test_the_retired_mode_check_sees_every_shape() -> None:
    shapes = {
        "a": 'USER_MODE="${AUTOBOT_USER_MODE:-single_user}"',
        "b": "# AUTOBOT_USER_MODE=single_user",
        "c": 'if [ "$USER_MODE" != "single_user" ]; then',
        "d": "# single_user is retired (#10636)",
        "e": "AUTOBOT_USER_MODE='single_user'",
        "f": 'AUTOBOT_USER_MODE="single_user"',
        "g": "USER_MODE=\"${AUTOBOT_USER_MODE:-'single_user'}\"",
        "h": "if [ \"$USER_MODE\" != 'single_user' ]; then",
    }
    assert retired_mode_sites(shapes) == ["a:1", "b:1", "c:1", "e:1", "f:1", "g:1", "h:1"]


# --- the entrypoint's migration retry is safe only if non-transactional migrations resume ---

_MIGRATIONS = "autobot-backend/migrations/versions"


def _migrations(root: Path) -> list[str]:
    try:
        return tracked_paths(root, f"{_MIGRATIONS}/*.py")
    except EmptyEnumeration:
        return []


MIGRATIONS_REACH = declare(
    "backend-migrations-resume-safe-18729",
    discover=_migrations,
    floor=97,  # mid-window: population 107, window (87, 107)
    growth=20,
    what="backend alembic migrations",
    roots=(_MIGRATIONS,),
)


_CONCURRENT_SQL = re.compile(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+CONCURRENTLY", re.I)
_DROP_IF_EXISTS = re.compile(r"DROP\s+INDEX\s+(?:CONCURRENTLY\s+)?IF\s+EXISTS", re.I)


def resume_hazards(name: str, source: str) -> list[str]:
    """Why a migration using autocommit_block could not be re-run after a partial failure."""
    if "autocommit_block" not in source:
        return []
    code = code_text(source, name=name if name.endswith(".py") else f"{name}.py", strip_trailing=True)
    hazards = [
        f"{name}: ADD VALUE without IF NOT EXISTS"
        for stmt in re.findall(r"ADD VALUE[^\"']*", code)
        if "IF NOT EXISTS" not in stmt
    ]
    concurrent = "postgresql_concurrently=True" in code or _CONCURRENT_SQL.search(code)
    # IF NOT EXISTS alone is not resumable: it silently keeps an invalid leftover index.
    handles_leftover = "indisvalid" in code or _DROP_IF_EXISTS.search(code)
    if concurrent and not handles_leftover:
        hazards.append(f"{name}: a concurrent index build never drops an invalid leftover")
    return hazards


def test_every_non_transactional_migration_can_resume_after_a_partial_failure() -> None:
    """CodeRabbit on #18827: the entrypoint retries `upgrade head` once, so a migration that ran
    half its autocommit work must be safe to run again."""
    files = {p: (_ROOT / p).read_text(encoding="utf-8") for p in MIGRATIONS_REACH.examined(_ROOT)}
    autocommit = [p for p, s in files.items() if "autocommit_block" in s]
    assert len(autocommit) >= 3, f"read {len(autocommit)} autocommit migrations -- the scan is broken"
    assert not [h for p, s in files.items() for h in resume_hazards(p, s)]


def test_the_resume_check_sees_both_hazards() -> None:
    bad_enum = "with op.get_context().autocommit_block():\n    op.execute(\"ALTER TYPE t ADD VALUE 'x'\")"
    bad_index = "autocommit_block\nop.create_index('i', 't', ['c'], postgresql_concurrently=True)"
    good = "autocommit_block\n# ADD VALUE in a comment\nop.execute(\"ALTER TYPE t ADD VALUE IF NOT EXISTS 'x'\")"
    assert resume_hazards("a", bad_enum) == ["a: ADD VALUE without IF NOT EXISTS"]
    assert resume_hazards("b", bad_index) == ["b: a concurrent index build never drops an invalid leftover"]
    assert resume_hazards("c", good) == []
    raw = "autocommit_block\nop.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS i ON t (c)')"
    raw_unique = "autocommit_block\nop.execute('create unique index concurrently i on t (c)')"
    raw_safe = "autocommit_block\nop.execute('DROP INDEX CONCURRENTLY IF EXISTS i')\nop.execute('CREATE INDEX CONCURRENTLY i ON t (c)')"
    assert resume_hazards("d", raw) == ["d: a concurrent index build never drops an invalid leftover"]
    assert resume_hazards("e", raw_unique) == ["e: a concurrent index build never drops an invalid leftover"]
    assert resume_hazards("f", raw_safe) == []
