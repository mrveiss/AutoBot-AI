#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SSH surface verification (#14870).

Verifies the SSH surface this codebase actually has:
  * `services.execution.ssh_backend.SSHBackend` imports, with paramiko present
  * SSHBackend exposes execute / health_check / cleanup / verify_task_compatibility
  * `autobot_shared.ssot_config` exposes the canonical SSH key/user fields
  * the configured key files exist with 0600 permissions
  * the real SSH tests and runbooks are present
  * optionally, a live `health_check()` against a host given with `--host`

What this script does NOT verify, because it does not exist:
  * `SSHManager` - that class never landed; `grep -rn "class SSHManager"` is empty
    repo-wide. The previous version of this script verified it anyway and always
    printed success.
  * an SSH connection pool - there is no pool, no start()/stop() lifecycle and no
    get_pool_stats() anywhere in this repo. Do not add checks for one.

Every check reports PASSED, FAILED or SKIPPED. A check that could not run is
SKIPPED with a reason and is never counted or printed as a pass. Exit code is 1
if anything FAILED; a run containing SKIPPED checks says so explicitly so it
cannot be mistaken for a full verification.
"""

import argparse
import asyncio
import inspect
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

# Add the repo root (for `autobot_shared`) and autobot-backend (for
# `services.execution`) to sys.path so the first-party imports below resolve
# regardless of the caller's working directory. This script is a standalone
# operator entry point, not part of an installed package, so it needs the same
# explicit path setup other scripts under autobot-infrastructure/shared/scripts/
# use (see manage_system_knowledge.py).
_REPO_ROOT = Path(__file__).resolve().parents[4]
_BACKEND_DIR = _REPO_ROOT / "autobot-backend"
for _entry in (_REPO_ROOT, _BACKEND_DIR):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from autobot_shared.logging_manager import get_logger  # noqa: E402
from autobot_shared.ssot_config import config  # noqa: E402

logger = get_logger(__name__)

PASSED = "PASSED"
FAILED = "FAILED"
SKIPPED = "SKIPPED"

SSH_TEST_FILES = (
    "autobot-backend/tests/test_execution_backends.py",
    "autobot-slm-backend/tests/services/test_ssh_utils.py",
    "autobot-slm-backend/tests/test_canonical_ssh_key.py",
)

SSH_DOC_FILES = (
    "docs/runbooks/ROTATE_SSH_KEYS.md",
    "autobot-infrastructure/shared/scripts/security/ssh-hardening/README.md",
)


@dataclass
class CheckResult:
    """Outcome of a single verification check."""

    name: str
    state: str
    detail: str


def check_backend_import() -> CheckResult:
    """Import the real SSH backend module; paramiko must actually be present.

    ssh_backend.py guard-imports paramiko and sets it to None when absent, so
    the import alone proves nothing - assert the module attribute too.
    """
    name = "SSHBackend import"
    try:
        from services.execution import ssh_backend
    except ImportError as exc:
        logger.error("%s: import failed: %s", name, exc)
        return CheckResult(name, FAILED, f"import failed: {exc}")

    if not hasattr(ssh_backend, "SSHBackend"):
        return CheckResult(name, FAILED, "module has no SSHBackend class")
    if ssh_backend.paramiko is None:
        return CheckResult(name, SKIPPED, "paramiko not installed - SSHBackend cannot be constructed here")
    return CheckResult(name, PASSED, "services.execution.ssh_backend imported, paramiko available")


def check_backend_api() -> CheckResult:
    """Check SSHBackend exposes the execution-backend methods and ctor args."""
    name = "SSHBackend API"
    try:
        from services.execution.ssh_backend import SSHBackend
    except ImportError as exc:
        logger.error("%s: module not importable: %s", name, exc)
        return CheckResult(name, SKIPPED, f"module not importable: {exc}")

    methods = ("execute", "health_check", "cleanup", "verify_task_compatibility")
    missing = [m for m in methods if not callable(getattr(SSHBackend, m, None))]
    if missing:
        return CheckResult(name, FAILED, f"missing methods: {', '.join(missing)}")

    params = inspect.signature(SSHBackend.__init__).parameters
    expected = ("hostname", "port", "username", "password", "private_key_path", "timeout")
    absent = [p for p in expected if p not in params]
    if absent:
        return CheckResult(name, FAILED, f"__init__ missing parameters: {', '.join(absent)}")
    return CheckResult(name, PASSED, f"{len(methods)} methods and {len(expected)} ctor parameters present")


def check_ssot_ssh_config() -> CheckResult:
    """Check ssot_config exposes the canonical SSH key and user fields."""
    name = "SSOT SSH configuration"
    attributes = (
        "ssh_key_path",
        "management_ssh_key_path",
        "ssh_user",
        "ssh_key",
        "ssh_pubkey_path",
        "management_ssh_key",
    )
    missing = [a for a in attributes if not hasattr(config.path, a)]
    if missing:
        return CheckResult(name, FAILED, f"config.path missing: {', '.join(missing)}")

    logger.info("   service key:    %s", config.path.ssh_key)
    logger.info("   management key: %s", config.path.management_ssh_key)
    logger.info("   ssh user:       %s", config.path.ssh_user)
    return CheckResult(name, PASSED, f"config.path exposes all {len(attributes)} canonical SSH fields")


def check_key_material() -> CheckResult:
    """Check the configured SSH key files exist with 0600 permissions."""
    name = "SSH key material"
    candidates = (config.path.ssh_key, config.path.management_ssh_key)
    present = [key for key in candidates if key.exists()]
    if not present:
        return CheckResult(name, SKIPPED, "neither configured key file exists on this machine")

    wrong = []
    for key in present:
        mode = stat.S_IMODE(key.stat().st_mode)
        if mode != 0o600:
            wrong.append(f"{key.name}={oct(mode)}")
    if wrong:
        return CheckResult(name, FAILED, f"key permissions must be 0600: {', '.join(wrong)}")
    return CheckResult(name, PASSED, f"{len(present)} key file(s) present with 0600 permissions")


def _check_paths(name: str, relatives: tuple[str, ...]) -> CheckResult:
    """Check every repo-relative path in `relatives` exists."""
    missing = [rel for rel in relatives if not (_REPO_ROOT / rel).exists()]
    if missing:
        return CheckResult(name, FAILED, f"missing: {', '.join(missing)}")
    return CheckResult(name, PASSED, f"all {len(relatives)} path(s) present")


def check_test_files() -> CheckResult:
    """Check the real SSH test files are present."""
    return _check_paths("SSH test files", SSH_TEST_FILES)


def check_documentation() -> CheckResult:
    """Check the real SSH documentation is present."""
    return _check_paths("SSH documentation", SSH_DOC_FILES)


async def check_live_host(hostname: str | None) -> CheckResult:
    """Run SSHBackend.health_check() against a real host, if one was given."""
    name = "Live SSH health check"
    if not hostname:
        return CheckResult(name, SKIPPED, "no --host given")
    try:
        from services.execution.ssh_backend import SSHBackend
    except ImportError as exc:
        logger.error("%s: module not importable: %s", name, exc)
        return CheckResult(name, SKIPPED, f"SSHBackend not importable: {exc}")

    try:
        backend = SSHBackend(
            hostname=hostname,
            username=config.path.ssh_user,
            private_key_path=str(config.path.ssh_key),
        )
    except RuntimeError as exc:
        logger.error("%s: backend unavailable: %s", name, exc)
        return CheckResult(name, SKIPPED, f"backend unavailable: {exc}")

    try:
        healthy = await backend.health_check()
    finally:
        await backend.cleanup()
    if not healthy:
        return CheckResult(name, FAILED, "health_check() returned False for the given host")
    return CheckResult(name, PASSED, "health_check() succeeded for the given host")


def report(results: list[CheckResult]) -> int:
    """Log every result and the per-state counts; return the process exit code."""
    counts = {PASSED: 0, FAILED: 0, SKIPPED: 0}
    logger.info("=" * 60)
    logger.info("SSH surface verification (#14870)")
    logger.info("=" * 60)
    for result in results:
        counts[result.state] += 1
        logger.info("%-7s  %-24s  %s", result.state, result.name, result.detail)

    logger.info("-" * 60)
    logger.info("PASSED=%d FAILED=%d SKIPPED=%d", counts[PASSED], counts[FAILED], counts[SKIPPED])
    if counts[FAILED]:
        logger.error("VERIFICATION FAILED - %d check(s) failed", counts[FAILED])
        return 1
    if counts[SKIPPED]:
        logger.warning(
            "VERIFICATION INCOMPLETE - %d check(s) could not run; this is NOT a full verification",
            counts[SKIPPED],
        )
        return 0
    logger.info("VERIFICATION COMPLETE - every check ran and passed")
    return 0


async def run_checks(hostname: str | None) -> int:
    """Run every check and report; returns the process exit code."""
    results = [
        check_backend_import(),
        check_backend_api(),
        check_ssot_ssh_config(),
        check_key_material(),
        check_test_files(),
        check_documentation(),
        await check_live_host(hostname),
    ]
    return report(results)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Verify the SSH surface this codebase actually has (#14870).")
    parser.add_argument(
        "--host",
        default=None,
        help="Host to run a live SSHBackend.health_check() against. Omitted: the live check is SKIPPED.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(run_checks(parse_args().host)))
    except KeyboardInterrupt:
        logger.error("Verification interrupted by user")
        sys.exit(1)
