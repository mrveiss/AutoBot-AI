# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bring-up of the stack the Company OS end-to-end test runs against (#19253).

Postgres and Redis are the service containers CI provides (or any disposable server a developer
points the two env vars at). This module creates a throwaway database on the Postgres server,
runs the production migrations on it, seeds one login user, and starts the real backend
(_serve.py) as a subprocess. It imports nothing from the application: the test is an HTTP client.
"""

from __future__ import annotations

import asyncio
import base64
import os
import secrets
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
from sqlalchemy.engine import URL

ENV_PREFIX = "AUTOBOT_COMPANY_OS_E2E_"
PG_HOST_ENV = ENV_PREFIX + "PG_HOST"
REDIS_HOST_ENV = ENV_PREFIX + "REDIS_HOST"
BOOT_TIMEOUT_SECONDS = float(os.environ.get("AUTOBOT_COMPANY_OS_E2E_BOOT_TIMEOUT", "300"))
HTTP_TIMEOUT_SECONDS = float(os.environ.get("AUTOBOT_COMPANY_OS_E2E_HTTP_TIMEOUT", "60"))
STOP_TIMEOUT_SECONDS = float(os.environ.get("AUTOBOT_COMPANY_OS_E2E_STOP_TIMEOUT", "60"))

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
LOGIN_USERNAME = "e2e-owner"
LOGIN_PASSWORD = secrets.token_urlsafe(24)


# Every other service the backend may reach for. Each one's default is this machine's loopback on
# its usual port, where a developer's own install may be listening (loopback is the whole
# 127.0.0.0/8 range, so another loopback ADDRESS would reach it too). Each is pointed instead at one
# port nothing listens on, so the run cannot read or write a service it was not given. The vector
# store host is empty, which selects the embedded store.
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


def migrate(ep: Endpoints, database: str) -> None:
    """Run the production migration entrypoint on the fresh database."""
    env = dict(os.environ)
    env["AUTOBOT_DATABASE_URL"] = ep.sqlalchemy_url(database)
    env["PYTHONPATH"] = f"{BACKEND_ROOT}{os.pathsep}{REPO_ROOT}"
    done = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
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


def _server_env(ep: Endpoints, database: str, port: int, stub_log: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        AUTOBOT_POSTGRES_HOST=ep.pg_host,
        AUTOBOT_POSTGRES_PORT=str(ep.pg_port),
        AUTOBOT_POSTGRES_USER=ep.pg_user,
        AUTOBOT_POSTGRES_PASSWORD=ep.pg_password,
        AUTOBOT_POSTGRES_DB=database,
        AUTOBOT_REDIS_HOST=ep.redis_host,
        AUTOBOT_REDIS_PORT=str(ep.redis_port),
        AUTOBOT_SECRETS_ROOT_KEY=base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
        AUTOBOT_JWT_SECRET=secrets.token_urlsafe(48),
        AUTOBOT_COMPANY_OS_E2E_SERVE_HOST="127.0.0.1",
        AUTOBOT_COMPANY_OS_E2E_SERVE_PORT=str(port),
        AUTOBOT_COMPANY_OS_E2E_STUB_LOG=str(stub_log),
        LLC_AGENT_API_BASE_URL=f"http://127.0.0.1:{port}/api",
        # Empty host selects the embedded ChromaDB the knowledge base falls back to, so the run
        # never reaches for a vector service of the machine it happens to run on.
        AUTOBOT_CHROMADB_HOST="",
        AUTOBOT_BACKEND_HOST="127.0.0.1",
        AUTOBOT_BACKEND_PORT=str(port),
        REDIS_HOST=ep.redis_host,
        PYTHONPATH=f"{BACKEND_ROOT}{os.pathsep}{REPO_ROOT}",
    )
    dead = free_port()  # bound and released: nothing listens on it
    env.update({name: str(dead) for name in DEAD_PORT_ENV})
    env.update({name: f"http://127.0.0.1:{dead}" for name in DEAD_ENDPOINT_ENV})
    return env


def _wait_healthy(base_url: str, process: subprocess.Popen, log: Path) -> None:
    deadline = time.monotonic() + BOOT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            tail = log.read_text(encoding="utf-8", errors="replace")[-4000:]
            raise RuntimeError(f"backend exited during boot (rc={process.returncode}):\n{tail}")
        try:
            if httpx.get(f"{base_url}/api/health", timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    tail = log.read_text(encoding="utf-8", errors="replace")[-4000:]
    raise RuntimeError(f"backend not healthy after {BOOT_TIMEOUT_SECONDS}s:\n{tail}")


def start(ep: Endpoints, workdir: Path) -> Stack:
    database = f"co_e2e_{uuid.uuid4().hex[:12]}"
    asyncio.run(_execute(ep, "postgres", f'CREATE DATABASE "{database}"'))
    migrate(ep, database)
    user_id = asyncio.run(_seed_user(ep, database))
    port = free_port()
    stub_log, server_log = workdir / "stub.jsonl", workdir / "server.log"
    stub_log.touch()
    with open(server_log, "wb") as out:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("_serve.py"))],
            cwd=workdir,  # relative data/ paths (embedded vector store, logs) land here, not in the repo
            env=_server_env(ep, database, port, stub_log),
            stdout=out,
            stderr=subprocess.STDOUT,
        )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_healthy(base_url, process, server_log)
    except Exception:
        process.kill()
        raise
    return Stack(base_url, database, user_id, stub_log, server_log, process)


def stop(stack: Stack, ep: Endpoints) -> None:
    stack.process.terminate()
    try:
        stack.process.wait(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        stack.process.kill()
    asyncio.run(_execute(ep, "postgres", f'DROP DATABASE IF EXISTS "{stack.database}" WITH (FORCE)'))
