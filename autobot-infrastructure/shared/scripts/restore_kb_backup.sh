#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# restore_kb_backup.sh — CLI wrapper for AutoBot knowledge-base backup restore.
#
# Issue #3294: Automated backup and recovery system.
#
# Usage:
#   ./restore_kb_backup.sh --backup-id 20260101_020000
#   ./restore_kb_backup.sh --list
#   ./restore_kb_backup.sh --verify --backup-id 20260101_020000
#   ./restore_kb_backup.sh --backup-id 20260101_020000 --dry-run
#   ./restore_kb_backup.sh --backup-id 20260101_020000 --target-dir /tmp/restore
#
# Required environment:
#   AUTOBOT_ENCRYPTION_KEY   — must match the key used at backup time
#
# Optional environment (override defaults from ssot_config):
#   AUTOBOT_BACKUP_DIR       — directory containing backup archives
#   AUTOBOT_BACKUP_STORAGE   — "local" or "s3"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/autobot-backend"

# Activate venv if present
if [[ -f "${REPO_ROOT}/.venv/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source "${REPO_ROOT}/.venv/bin/activate"
fi

# Add backend to PYTHONPATH so imports resolve
export PYTHONPATH="${BACKEND_DIR}:${REPO_ROOT}/autobot_shared:${PYTHONPATH:-}"

python3 - "$@" <<'PYTHON'
"""Entry point executed by restore_kb_backup.sh"""
import argparse
import asyncio
import sys

from backup.engine import BackupEngine


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="AutoBot knowledge-base backup restore utility (issue #3294)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  restore_kb_backup.sh --list
  restore_kb_backup.sh --verify --backup-id 20260101_020000
  restore_kb_backup.sh --backup-id 20260101_020000 --dry-run
  restore_kb_backup.sh --backup-id 20260101_020000 --target-dir /opt/autobot/data
  restore_kb_backup.sh --run-backup
""",
    )
    p.add_argument("--list", action="store_true", help="List available backups")
    p.add_argument("--verify", action="store_true", help="Verify backup integrity")
    p.add_argument("--backup-id", help="Backup ID to restore or verify")
    p.add_argument("--target-dir", help="Restore destination directory")
    p.add_argument("--dry-run", action="store_true", help="Show what would be restored")
    p.add_argument("--run-backup", action="store_true", help="Trigger a manual backup now")
    return p


async def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    engine = BackupEngine()

    if args.list:
        backups = engine.list_backups()
        if not backups:
            print("No backups found.")
            return 0
        print(f"{'Backup ID':<22} {'Timestamp':<26} {'Components':<30} {'Size MB':>8}")
        print("-" * 90)
        for b in backups:
            components = ", ".join(b.get("components", []))
            size_mb = b.get("size_bytes", 0) / 1_048_576
            print(f"{b['backup_id']:<22} {b['timestamp']:<26} {components:<30} {size_mb:>8.1f}")
        return 0

    if args.verify:
        if not args.backup_id:
            print("ERROR: --backup-id required for --verify", file=sys.stderr)
            return 1
        ok = engine.verify_backup(args.backup_id)
        print("OK" if ok else "FAILED")
        return 0 if ok else 1

    if args.run_backup:
        result = await engine.create_backup()
        if result.success:
            print(f"Backup succeeded: {result.backup_id} ({', '.join(result.components)})")
            return 0
        print(f"Backup FAILED: {result.error}", file=sys.stderr)
        return 1

    if not args.backup_id:
        print("ERROR: --backup-id required for restore", file=sys.stderr)
        parser.print_help(sys.stderr)
        return 1

    from pathlib import Path

    target = Path(args.target_dir) if args.target_dir else None
    ok = await engine.restore_backup(
        args.backup_id, target_dir=target, dry_run=args.dry_run
    )
    return 0 if ok else 1


sys.exit(asyncio.run(main()))
PYTHON
