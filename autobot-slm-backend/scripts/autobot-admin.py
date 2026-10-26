#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
autobot-admin - server-side management CLI for AutoBot SLM.

Usage:
    autobot-admin reset-password <username>   (prompts for the password, or reads one line from stdin)

Reads DB connection from /etc/autobot/slm-secrets.env or
/opt/autobot/autobot-slm-backend/.env (later file wins per key).
Works without the SLM backend running (direct PostgreSQL access).
"""

import argparse
import getpass
import logging
import os
import re
import sys
import time

# Stdlib logging, as in the other SLM code: the SLM test conftest mocks config, which
# autobot_shared.logging_manager reads at import (CLAUDE.md's stated exception). This CLI also runs
# standalone on the host, outside the backend's import path.
logger = logging.getLogger("autobot-admin")

#: The install root. Ansible copies this file alone to /usr/local/bin and runs it with the system python,
#: so it cannot import autobot_shared.fleet_constants.FLEET_INSTALL_ROOT; it restates that ONE value
#: here, and repo_tests/defined_twice_18094_test.py holds the two equal (#18094).
_INSTALL_ROOT = "/opt/autobot"  # noqa: ssot-path -- the pinned standalone copy described above


def load_env_file(path: str) -> dict:
    """Load key=value pairs from an env file, ignoring comments and blanks."""
    env: dict = {}
    if not os.path.exists(path):
        return env
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def get_db_url() -> str:
    """Legacy DSN from SLM_DB_* keys, used only when the service URLs are not in the secrets files."""
    env = _secrets_env()

    host = env.get("SLM_DB_HOST", "127.0.0.1")
    port = env.get("SLM_DB_PORT", "5432")
    # The SLM_DB_* keys are what the fleet postgresql role writes (#19320: these
    # defaults were the compose values, which no fleet host -- where this CLI is
    # installed -- has). Pinned to autobot_shared/postgres_identity.py.
    name = env.get("SLM_DB_NAME", "slm")
    user = env.get("SLM_DB_USER", "slm_app")
    password = env.get("SLM_DB_PASSWORD", "")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


#: A reset records the subject's password epoch in the SLM's own store (#18663), so every token
#: issued before it is refused (#12924). GREATEST keeps a later epoch from going backwards.
_UPSERT_EPOCH_SQL = (
    "INSERT INTO slm_password_epochs (subject, epoch) VALUES (%s, %s) "
    "ON CONFLICT (subject) DO UPDATE SET epoch = GREATEST(slm_password_epochs.epoch, EXCLUDED.epoch)"
)


def _secrets_env() -> dict:
    """Merged secrets files, later file wins per key."""
    env: dict = {}
    for path in ("/etc/autobot/slm-secrets.env", f"{_INSTALL_ROOT}/autobot-slm-backend/.env"):
        env.update(load_env_file(path))
    return env


def _dsn_from(env: dict, key: str) -> str:
    """The service's own asyncpg URL for *key*, as a psycopg2 DSN; legacy SLM_DB_* when unset."""
    url = env.get(key, "")
    return url.replace("+asyncpg", "", 1) if url else get_db_url()  # the psycopg2 form of the same DSN


def _read_password() -> str:
    """Never from argv, where ps and shell history expose it (#18672 review): prompt, or one stdin line."""
    if not sys.stdin.isatty():
        value = sys.stdin.readline().rstrip("\n")
    else:
        value = getpass.getpass("New password: ")
        if getpass.getpass("Repeat new password: ") != value:
            sys.exit("Error: the passwords do not match.")
    if not value:
        sys.exit("Error: an empty password is not allowed.")
    return value


def _require_user(psycopg2, users_dsn: str, username: str) -> None:
    conn = psycopg2.connect(users_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM slm_users WHERE username = %s", (username,))
            if cur.fetchone() is None:
                sys.exit(f"Error: user '{username}' not found.")
    finally:
        conn.close()


def _record_epoch(psycopg2, epoch_dsn: str, username: str) -> None:
    """Commit the password epoch FIRST: if the hash write then fails, older sessions are already
    revoked and the old password still works -- fail closed (#18672, #12924)."""
    conn = psycopg2.connect(epoch_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(_UPSERT_EPOCH_SQL, (username, int(time.time())))
        conn.commit()
    finally:
        conn.close()


def _write_hash(psycopg2, users_dsn: str, username: str, password_hash: str) -> None:
    conn = psycopg2.connect(users_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE slm_users SET password_hash = %s WHERE username = %s", (password_hash, username))
        conn.commit()
    finally:
        conn.close()


def _sync_secrets_file(username: str, password: str, secrets_path: str = "/etc/autobot/slm-secrets.env") -> None:
    """Keep SLM_ADMIN_PASSWORD in step so the next SLM restart's seed plays use the new value."""
    if username != "admin" or not os.path.exists(secrets_path):
        return
    with open(secrets_path, encoding="utf-8") as fh:
        content = fh.read()
    # A lambda replacement: a password holding `\\` or `\\1` is written literally, not as a regex escape.
    updated = re.sub(
        r"^SLM_ADMIN_PASSWORD=.*$", lambda _m: f"SLM_ADMIN_PASSWORD={password}", content, flags=re.MULTILINE
    )
    if "SLM_ADMIN_PASSWORD=" not in updated:
        updated += f"\nSLM_ADMIN_PASSWORD={password}\n"
    with open(secrets_path, "w", encoding="utf-8") as fh:
        fh.write(updated)
    logger.info("Updated SLM_ADMIN_PASSWORD in %s", secrets_path)


def cmd_reset_password(args: argparse.Namespace) -> None:
    """Hash a new password into slm_users after recording the epoch in the SLM database.

    Users and epochs live in two databases (SLM_USERS_DATABASE_URL and SLM_DATABASE_URL), so the
    two writes cannot share a transaction; the epoch commits first (fail closed).
    """
    try:
        import bcrypt  # noqa: PLC0415
        import psycopg2  # noqa: PLC0415
    except ImportError as exc:
        sys.exit(f"Missing dependency: {exc}. " "Install with: pip install bcrypt psycopg2-binary")

    password = _read_password()
    env = _secrets_env()
    users_dsn, epoch_dsn = _dsn_from(env, "SLM_USERS_DATABASE_URL"), _dsn_from(env, "SLM_DATABASE_URL")
    _require_user(psycopg2, users_dsn, args.username)
    _record_epoch(psycopg2, epoch_dsn, args.username)
    _write_hash(
        psycopg2,
        users_dsn,
        args.username,
        bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8"),
    )
    logger.info("Password for '%s' updated in database; older sessions are revoked.", args.username)
    _sync_secrets_file(args.username, password)
    logger.info("Done.")


def main() -> None:
    # Operator-facing output: the message alone, on stdout, as before (#1082 logging standard).
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(
        prog="autobot-admin",
        description="AutoBot server administration tool",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    rp = subparsers.add_parser("reset-password", help="Reset a user password")
    rp.add_argument("username", help="Username to reset")
    rp.set_defaults(func=cmd_reset_password)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
