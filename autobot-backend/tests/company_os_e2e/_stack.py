# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bring-up of the stack the Company OS end-to-end test runs against (#19253).

Postgres and Redis are the service containers CI provides (or any disposable server a developer
points the env vars at). This module creates a throwaway database on the Postgres server, runs the
production migrations on it, seeds one login user, and starts the real backend (_serve.py) as a
subprocess. It imports nothing from the application: the test is an HTTP client.

Isolation, in three layers: the subprocess environment is BUILT from an allowlist (never copied from
the caller), every other service the backend knows is pointed at a closed port, and the run refuses
to start against a Redis that holds data or to use a Postgres superuser.
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import asyncpg
import bcrypt
import httpx
import redis
from sqlalchemy.engine import URL

ENV_PREFIX = "AUTOBOT_COMPANY_OS_E2E_"
PG_HOST_ENV = ENV_PREFIX + "PG_HOST"
REDIS_HOST_ENV = ENV_PREFIX + "REDIS_HOST"
ARTIFACT_DIR_ENV = ENV_PREFIX + "ARTIFACT_DIR"
BOOT_TIMEOUT_SECONDS = float(os.environ.get(ENV_PREFIX + "BOOT_TIMEOUT", "300"))
HTTP_TIMEOUT_SECONDS = float(os.environ.get(ENV_PREFIX + "HTTP_TIMEOUT", "60"))
STOP_TIMEOUT_SECONDS = float(os.environ.get(ENV_PREFIX + "STOP_TIMEOUT", "60"))

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
LOGIN_USERNAME = "e2e-owner"
LOGIN_PASSWORD = secrets.token_urlsafe(24)

# The only variables the caller's environment may contribute. Everything else is dropped, not
# filtered: an exported AUTOBOT_DATABASE_URL, AUTOBOT_REDIS_URL, REDIS_*, POSTGRES_*, PG*, OLLAMA* or
# LLC_* would otherwise steer the scratch server at whatever service the developer's shell names.
ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TZ",
    "USER",
    "LOGNAME",
    "VIRTUAL_ENV",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
)

# Every other service the backend may reach for. Each one's default is this machine's loopback on
# its usual port, where a developer's own install may be listening (loopback is the whole
# 127.0.0.0/8 range, so another loopback ADDRESS would reach it too). Each is pointed instead at one
# port nothing listens on. The vector store host is empty, which selects the embedded store.
DEAD_PORT_ENV = (
    "AUTOBOT_FRONTEND_PORT",
    "AUTOBOT_FRONTEND_HTTP_PORT",
    "AUTOBOT_OLLAMA_PORT",
    "AUTOBOT_VNC_PORT",
    "AUTOBOT_VNC_SERVER_PORT",
    "AUTOBOT_BROWSER_SERVICE_PORT",
    "AUTOBOT_AI_STACK_PORT",
    "AUTOBOT_CHROMADB_PORT",
    "AUTOBOT_NPU_WORKER_PORT",
    "AUTOBOT_NPU_WORKER_WINDOWS_PORT",
    "AUTOBOT_TTS_WORKER_PORT",
    "AUTOBOT_SLM_PORT",
    "AUTOBOT_PROMETHEUS_PORT",
    "AUTOBOT_GRAFANA_PORT",
    "AUTOBOT_CHROME_CDP_PORT",
)
DEAD_ENDPOINT_ENV = (
    "AUTOBOT_OLLAMA_ENDPOINT",
    "AUTOBOT_LLAMAINDEX_LLM_ENDPOINT",
    "AUTOBOT_LLAMAINDEX_EMBEDDING_ENDPOINT",
    "OLLAMA_HOST",
    "LMSTUDIO_HOST",
    "VLLM_HOST",
)


@dataclass(frozen=True)
class Endpoints:
    """Where the disposable Postgres and Redis are; read from env, never from a URL literal."""

    pg_host: str
    pg_port: int
    pg_user: str
    pg_password: str
    redis_host: str
    redis_port: int

    @classmethod
    def from_env(cls) -> "Endpoints":
        env = os.environ
        return cls(
            pg_host=env[PG_HOST_ENV],
            pg_port=int(env.get(ENV_PREFIX + "PG_PORT", "5432")),
            pg_user=env[ENV_PREFIX + "PG_USER"],
            pg_password=env.get(ENV_PREFIX + "PG_PASSWORD", ""),
            redis_host=env[REDIS_HOST_ENV],
            redis_port=int(env.get(ENV_PREFIX + "REDIS_PORT", "6379")),
        )

    def as_role(self, user: str, password: str) -> "Endpoints":
        return dataclasses.replace(self, pg_user=user, pg_password=password)

    def pg_connect_args(self, database: str) -> dict[str, object]:
        return dict(
            host=self.pg_host, port=self.pg_port, user=self.pg_user, password=self.pg_password, database=database
        )

    def sqlalchemy_url(self, database: str) -> str:
        url = URL.create("postgresql+asyncpg", self.pg_user, self.pg_password, self.pg_host, self.pg_port, database)
        return url.render_as_string(hide_password=False)


@dataclass
class Stack:
    base_url: str
    database: str
    user_id: str
    stub_log: Path
    server_log: Path
    process: subprocess.Popen
    admin: Endpoints
    run: Endpoints


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _execute(ep: Endpoints, database: str, sql: str) -> None:
    conn = await asyncpg.connect(**ep.pg_connect_args(database))
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


# --- the subprocess environment ----------------------------------------------------------------


def clean_env(source: dict[str, str] | None = None) -> dict[str, str]:
    """The allowlisted slice of ``source`` (default: the process environment); nothing else."""
    src = os.environ if source is None else source
    return {name: src[name] for name in ENV_ALLOWLIST if name in src}


def _python_env(home: Path) -> dict[str, str]:
    env = clean_env()
    env["HOME"] = str(home)  # none of the developer's ~/.config or ~/.cache is read or written
    env["PYTHONPATH"] = f"{BACKEND_ROOT}{os.pathsep}{REPO_ROOT}"
    return env


def _alembic_env(ep: Endpoints, database: str, home: Path) -> dict[str, str]:
    env = _python_env(home)
    env["AUTOBOT_DATABASE_URL"] = ep.sqlalchemy_url(database)
    return env


def _server_env(ep: Endpoints, database: str, port: int, stub_log: Path, home: Path) -> dict[str, str]:
    env = _python_env(home)
    env.update(
        AUTOBOT_DATABASE_URL=ep.sqlalchemy_url(database),
        AUTOBOT_POSTGRES_HOST=ep.pg_host,
        AUTOBOT_POSTGRES_PORT=str(ep.pg_port),
        AUTOBOT_POSTGRES_USER=ep.pg_user,
        AUTOBOT_POSTGRES_PASSWORD=ep.pg_password,
        AUTOBOT_POSTGRES_DB=database,
        AUTOBOT_REDIS_HOST=ep.redis_host,
        AUTOBOT_REDIS_PORT=str(ep.redis_port),
        AUTOBOT_REDIS_URL=f"redis://{ep.redis_host}:{ep.redis_port}",
        REDIS_HOST=ep.redis_host,
        AUTOBOT_SECRETS_ROOT_KEY=base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
        AUTOBOT_JWT_SECRET=secrets.token_urlsafe(48),
        AUTOBOT_COMPANY_OS_E2E_SERVE_HOST="127.0.0.1",
        AUTOBOT_COMPANY_OS_E2E_SERVE_PORT=str(port),
        AUTOBOT_COMPANY_OS_E2E_STUB_LOG=str(stub_log),
        LLC_AGENT_API_BASE_URL=f"http://127.0.0.1:{port}/api",
        AUTOBOT_CHROMADB_HOST="",
        AUTOBOT_BACKEND_HOST="127.0.0.1",
        AUTOBOT_BACKEND_PORT=str(port),
    )
    dead = free_port()  # bound and released: nothing listens on it
    env.update({name: str(dead) for name in DEAD_PORT_ENV})
    env.update({name: f"http://127.0.0.1:{dead}" for name in DEAD_ENDPOINT_ENV})
    return env


# --- the database -------------------------------------------------------------------------------


def migrate(ep: Endpoints, database: str, home: Path) -> None:
    """Run the production migration entrypoint on the fresh database."""
    done = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=_alembic_env(ep, database, home),
        capture_output=True,
        text=True,
        timeout=900,
    )
    if done.returncode != 0:
        raise RuntimeError(f"alembic upgrade head failed:\n{done.stderr[-3000:]}")


async def _seed_user(ep: Endpoints, database: str) -> str:
    """One ordinary (non-admin) user, as a person who signed up would be."""
    user_id = str(uuid.uuid4())
    hashed = bcrypt.hashpw(LOGIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conn = await asyncpg.connect(**ep.pg_connect_args(database))
    try:
        await conn.execute(
            "INSERT INTO users (id, email, username, password_hash, is_active, is_verified, "
            "mfa_enabled, is_platform_admin) VALUES ($1, $2, $3, $4, true, true, false, false)",
            uuid.UUID(user_id),
            f"{LOGIN_USERNAME}@example.test",
            LOGIN_USERNAME,
            hashed,
        )
    finally:
        await conn.close()
    return user_id


# --- preconditions on the services we are handed -----------------------------------------------


async def _is_superuser(ep: Endpoints) -> bool:
    conn = await asyncpg.connect(**ep.pg_connect_args("postgres"))
    try:
        return bool(await conn.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname = current_user"))
    finally:
        await conn.close()


def redis_is_empty(ep: Endpoints) -> bool:
    """True when no logical database on the target holds a key (``INFO keyspace`` is empty)."""
    client = redis.Redis(host=ep.redis_host, port=ep.redis_port)
    try:
        return not client.info("keyspace")
    finally:
        client.close()


def require_scratch_services(ep: Endpoints) -> None:
    """Refuse to run against a Redis that holds data: it is somebody's, not ours to fill."""
    if not redis_is_empty(ep):
        raise RuntimeError(
            f"refusing to start: the Redis at {ep.redis_host}:{ep.redis_port} is not empty, "
            "so it is not a disposable service"
        )


async def _make_run_role(ep: Endpoints) -> Endpoints:
    """The role the run uses: never a superuser.

    A CI service container's POSTGRES_USER is a superuser by construction, so refusing outright
    would make the test unrunnable there. Instead the given (admin) role creates a throwaway role
    with only LOGIN and CREATEDB, and the application, the migrations and the seed all use that
    one. A given role that is not a superuser is used as it is.
    """
    if not await _is_superuser(ep):
        return ep
    role, password = f"co_e2e_{uuid.uuid4().hex[:10]}", secrets.token_urlsafe(18)
    await _execute(ep, "postgres", f"CREATE ROLE \"{role}\" LOGIN CREATEDB PASSWORD '{password}'")
    return ep.as_role(role, password)


# --- lifecycle ---------------------------------------------------------------------------------


def keep_logs(server_log: Path, stub_log: Path) -> None:
    """Copy the server log and the stub's dispatch log where CI uploads artifacts from."""
    target = os.environ.get(ARTIFACT_DIR_ENV)
    if not target:
        return
    Path(target).mkdir(parents=True, exist_ok=True)
    for source in (server_log, stub_log):
        if source.exists():
            shutil.copy(source, Path(target) / source.name)


def _end_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=STOP_TIMEOUT_SECONDS)


def _remove_database(admin: Endpoints, database: str | None) -> None:
    if database:
        asyncio.run(_execute(admin, "postgres", f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))


def _remove_role(admin: Endpoints, run: Endpoints) -> None:
    if run.pg_user != admin.pg_user:
        asyncio.run(_execute(admin, "postgres", f'DROP ROLE IF EXISTS "{run.pg_user}"'))


def _teardown(admin: Endpoints, run: Endpoints, database: str | None, process, logs: tuple[Path, Path]) -> None:
    """Every step runs even if an earlier one raises; the first error is re-raised at the end."""
    errors: list[BaseException] = []
    for action in (
        lambda: _end_process(process),
        lambda: keep_logs(*logs),
        lambda: _remove_database(admin, database),
        lambda: _remove_role(admin, run),
    ):
        try:
            action()
        except BaseException as exc:  # noqa: BLE001 - collected, and the first re-raised below
            errors.append(exc)
    if errors:
        raise errors[0]


def _wait_healthy(base_url: str, process: subprocess.Popen, log: Path) -> None:
    deadline = time.monotonic() + BOOT_TIMEOUT_SECONDS
    tail = lambda: log.read_text(encoding="utf-8", errors="replace")[-4000:]  # noqa: E731
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"backend exited during boot (rc={process.returncode}):\n{tail()}")
        try:
            if httpx.get(f"{base_url}/api/health", timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError(f"backend not healthy after {BOOT_TIMEOUT_SECONDS}s:\n{tail()}")


def _launch(run: Endpoints, database: str, workdir: Path, logs: tuple[Path, Path]) -> tuple[subprocess.Popen, str]:
    home = workdir / "home"
    port = free_port()
    with open(logs[0], "wb") as out:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("_serve.py"))],
            cwd=workdir,
            env=_server_env(run, database, port, logs[1], home),
            stdout=out,
            stderr=subprocess.STDOUT,
        )
    return process, f"http://127.0.0.1:{port}"


def start(admin: Endpoints, workdir: Path) -> Stack:
    require_scratch_services(admin)
    run = asyncio.run(_make_run_role(admin))
    logs = (workdir / "server.log", workdir / "stub.jsonl")
    for log in logs:
        log.touch()
    database, process = f"co_e2e_{uuid.uuid4().hex[:12]}", None
    try:
        asyncio.run(_execute(run, "postgres", f'CREATE DATABASE "{database}"'))
        (workdir / "home").mkdir(exist_ok=True)
        migrate(run, database, workdir / "home")
        user_id = asyncio.run(_seed_user(run, database))
        process, base_url = _launch(run, database, workdir, logs)
        _wait_healthy(base_url, process, logs[0])
    except BaseException:
        _teardown(admin, run, database, process, logs)
        raise
    return Stack(base_url, database, user_id, logs[1], logs[0], process, admin, run)


def stop(stack: Stack) -> None:
    _teardown(stack.admin, stack.run, stack.database, stack.process, (stack.server_log, stack.stub_log))
