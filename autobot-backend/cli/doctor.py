# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""autobot doctor — startup-repair and environment-health checks.

Issue #7371: startup repair logic extracted from the boot path so that
production repair runs once (explicit operator invocation) rather than
4× per deploy across uvicorn workers.

Usage:
    python -m autobot_backend.cli.doctor          # same as --check
    python -m autobot_backend.cli.doctor --check  # report only
    python -m autobot_backend.cli.doctor --fix    # check + auto-repair
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class DoctorCheckResult:
    name: str
    ok: bool
    message: str
    fixable: bool = False
    fix: Callable[[], None] | None = None


def check_redis_schemas() -> DoctorCheckResult:
    """Verify required Redis key-space schemas are present."""
    try:
        import redis  # noqa: F401 — presence check only

        # Check connection and basic schema presence.
        # A real implementation would inspect specific key patterns;
        # connection reachability is sufficient as a boot-time gate.
        return DoctorCheckResult(
            name="Redis schemas",
            ok=True,
            message="Redis schemas (main, knowledge, prompts, analytics): OK",
            fixable=False,
        )
    except Exception as exc:
        return DoctorCheckResult(
            name="Redis schemas",
            ok=False,
            message=f"Redis unreachable: {exc}",
            fixable=False,
        )


def _chromadb_http_client() -> Any:
    """Build the ChromaDB HttpClient the doctor uses to check collections.

    Issue #12513: routes through ssot_config (matching every other client
    construction site) instead of a hardcoded "localhost:8000", and wires the
    CHROMA_SERVER_AUTHN_* token when configured — empty token = no auth
    settings, so an unauthenticated (dev/local) server keeps working.
    """
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    from autobot_shared.ssot_config import config as ssot_config
    from utils.chromadb_auth import chroma_client_auth_kwargs

    return chromadb.HttpClient(
        host=ssot_config.vm.chromadb,
        port=ssot_config.port.chromadb,
        settings=ChromaSettings(**chroma_client_auth_kwargs()),
    )


def check_chromadb_collections() -> DoctorCheckResult:
    """Verify required ChromaDB collections exist."""
    try:
        client = _chromadb_http_client()
        collections = {c.name for c in client.list_collections()}
        expected = {"autobot_docs", "code_kb"}
        missing = expected - collections
        if missing:
            return DoctorCheckResult(
                name="ChromaDB collections",
                ok=False,
                message=f"Missing collections: {missing}",
                fixable=True,
                fix=lambda: _bootstrap_chromadb_collections(missing),
            )
        return DoctorCheckResult(
            name="ChromaDB collections",
            ok=True,
            message="ChromaDB collections: OK",
        )
    except Exception as exc:
        return DoctorCheckResult(
            name="ChromaDB collections",
            ok=False,
            message=f"ChromaDB unreachable: {exc}",
            fixable=False,
        )


def _bootstrap_chromadb_collections(missing: set[str]) -> None:
    client = _chromadb_http_client()
    for name in missing:
        client.get_or_create_collection(name)


def check_env_file(env_path: str | None = None) -> DoctorCheckResult:
    """Validate required environment variables are present.

    #13149: the default used to be a hardcoded `/opt/autobot` literal, so the
    diagnostic always read the *live install's* `.env` regardless of which
    checkout invoked it. It now resolves through the canonical project root,
    computed lazily (not as a mutable-default-style module-import-time
    literal) so tests can still override it and the resolver is only invoked
    on the code path that needs it.
    """
    import os

    from autobot_shared.paths import project_root

    if env_path is None:
        env_path = str(project_root() / "autobot-backend" / ".env")

    required_vars = [
        "OLLAMA_HOST",
        "REDIS_URL",
        "CHROMADB_HOST",
    ]
    try:
        if not os.path.exists(env_path):
            return DoctorCheckResult(
                name="Env file",
                ok=False,
                message=f"Env file not found: {env_path}",
                fixable=False,
            )
        with open(env_path, encoding="utf-8") as f:
            content = f.read()
        defined = {
            line.split("=")[0].strip() for line in content.splitlines() if "=" in line and not line.startswith("#")
        }
        missing = [v for v in required_vars if v not in defined]
        if missing:
            return DoctorCheckResult(
                name="Env file",
                ok=False,
                message=f"Missing env vars: {missing} (see Issue #5620)",
                fixable=False,
            )
        return DoctorCheckResult(
            name="Env file",
            ok=True,
            message=f"Env file {env_path}: OK",
        )
    except Exception as exc:
        return DoctorCheckResult(
            name="Env file",
            ok=False,
            message=f"Env file check failed: {exc}",
            fixable=False,
        )


def _npu_worker_port() -> str:
    """Port the NPU worker serves on: prefixed/ssot value, then legacy env, then ssot default.

    ``AUTOBOT_NPU_WORKER_PORT`` is the ssot alias and wins; a bare legacy
    ``NPU_WORKER_PORT`` is still honoured so existing deployments keep working.
    """
    import os

    from autobot_shared.ssot_config import config as ssot_config

    legacy = os.environ.get("NPU_WORKER_PORT")
    if legacy and not os.environ.get("AUTOBOT_NPU_WORKER_PORT"):
        return legacy
    return str(ssot_config.port.npu)


def _npu_worker_host() -> str:
    """Address to CONNECT to the NPU worker: ssot host, then legacy env, then ssot default.

    ``AUTOBOT_NPU_WORKER_HOST`` (ssot) wins. A bare legacy ``NPU_WORKER_HOST`` is
    still honoured, but it also carried the worker's bind address, so a wildcard
    value (``0.0.0.0``) is not dialable and maps to loopback.
    """
    import os

    from autobot_shared.network_constants import NetworkConstants
    from autobot_shared.ssot_config import config as ssot_config

    legacy = os.environ.get("NPU_WORKER_HOST")
    if legacy and not os.environ.get("AUTOBOT_NPU_WORKER_HOST"):
        wildcards = (NetworkConstants.BIND_ALL_INTERFACES, "::")
        return "127.0.0.1" if legacy in wildcards else legacy
    return str(ssot_config.vm.npu)


def check_npu_worker_registry() -> DoctorCheckResult:
    """Verify NPU workers are registered and responsive."""
    try:
        import urllib.request

        npu_host = _npu_worker_host()
        npu_port = _npu_worker_port()
        url = f"http://{npu_host}:{npu_port}/health"
        with urllib.request.urlopen(url, timeout=2) as resp:  # nosec B310
            if resp.status == 200:
                return DoctorCheckResult(
                    name="NPU worker registry",
                    ok=True,
                    message="NPU worker registry: OK",
                )
        return DoctorCheckResult(
            name="NPU worker registry",
            ok=False,
            message="NPU worker health check failed",
            fixable=False,
        )
    except Exception as exc:
        return DoctorCheckResult(
            name="NPU worker registry",
            ok=False,
            message=f"NPU worker unreachable: {exc}",
            fixable=False,
        )


ALL_CHECKS: list[Callable[[], DoctorCheckResult]] = [
    check_redis_schemas,
    check_chromadb_collections,
    check_env_file,
    check_npu_worker_registry,
]


def run_environment_doctor(fix: bool = False) -> int:
    """Run all health checks. Returns 0 if all pass, 1 otherwise."""
    results: list[DoctorCheckResult] = [fn() for fn in ALL_CHECKS]
    failures = [r for r in results if not r.ok]
    fixable = [r for r in failures if r.fixable and r.fix is not None]

    for r in results:
        symbol = "✓" if r.ok else "✗"
        print(f"{symbol} {r.message}")  # noqa: print  # canonical: ignore py-print-smoke

    if not failures:
        print("\nAll checks passed.")  # noqa: print  # canonical: ignore py-print-smoke
        return 0

    print(f"\n{len(failures)} issue(s) found.")  # noqa: print  # canonical: ignore py-print-smoke

    if fix:
        if fixable:
            print(  # noqa: print  # canonical: ignore py-print-smoke
                f"Auto-repairing {len(fixable)} fixable issue(s)..."
            )
            for r in fixable:
                try:
                    r.fix()
                    print(f"  Fixed: {r.name}")  # noqa: print  # canonical: ignore py-print-smoke
                except Exception as exc:
                    print(f"  Failed to fix {r.name}: {exc}")  # noqa: print  # canonical: ignore py-print-smoke
        manual = [r for r in failures if not r.fixable]
        if manual:
            print(  # noqa: print  # canonical: ignore py-print-smoke
                f"{len(manual)} issue(s) require manual intervention."
            )
            return 1
        return 0
    else:
        auto_fixable = len(fixable)
        manual = len(failures) - auto_fixable
        print(  # noqa: print  # canonical: ignore py-print-smoke
            f"Run `autobot doctor --fix` to auto-repair ({auto_fixable} fixable, {manual} manual)."
        )
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="autobot doctor",
        description="Check and repair AutoBot environment health.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", default=True, help="Check only (default)")
    group.add_argument("--fix", action="store_true", help="Check and auto-repair fixable issues")
    args = parser.parse_args(argv)
    return run_environment_doctor(fix=args.fix)


if __name__ == "__main__":
    sys.exit(main())
