#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# restore_kb_backup.sh - CLI wrapper for AutoBot knowledge-base backup restore.
#
# Issue #3294: Automated backup and recovery system.
#
# (#14875) This drove `backup.engine.BackupEngine`, which has never existed:
# zero hits repo-wide for `class BackupEngine`, and autobot-backend/backup/
# holds only __init__.py and scheduler.py. The engine that actually performs KB
# backup is the KnowledgeBase bulk-operations mixin - it is what
# backup/scheduler.py:115-118 drives on the schedule, and what
# api/knowledge_maintenance.py serves to the maintenance UI. This script now
# drives the same one, so a restore from the CLI and a restore from the UI go
# through identical code.
#
# Two flags changed with it, because the real engine addresses backups by FILE,
# not by a synthesised id, and confines every restore to the knowledge backups
# directory (#9670):
#   --backup-id   -> --backup-file   (the filename from --list)
#   --target-dir  -> rejected, loudly; the destination is not caller-selectable
#
# Usage:
#   ./restore_kb_backup.sh --list
#   ./restore_kb_backup.sh --verify --backup-file kb_backup_20260101_020000.json.gz
#   ./restore_kb_backup.sh --backup-file kb_backup_20260101_020000.json.gz --dry-run
#   ./restore_kb_backup.sh --backup-file kb_backup_20260101_020000.json.gz --overwrite
#   ./restore_kb_backup.sh --run-backup
#
# Required environment:
#   AUTOBOT_ENCRYPTION_KEY   - must match the key used at backup time
#
# Optional environment (override defaults from ssot_config):
#   AUTOBOT_BACKUP_DIR       - directory containing backup archives
#   AUTOBOT_BACKUP_STORAGE   - "local" or "s3"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/autobot-backend"

# Activate venv if present
if [[ -f "${REPO_ROOT}/.venv/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source "${REPO_ROOT}/.venv/bin/activate"
fi

# Add backend to PYTHONPATH so imports resolve.
# (#14867) The second entry used to be ${REPO_ROOT}/autobot_shared, which puts
# the *contents* of the package on the path instead of its parent, so every
# `import autobot_shared.*` failed. The package root is ${REPO_ROOT}.
export PYTHONPATH="${BACKEND_DIR}:${REPO_ROOT}:${PYTHONPATH:-}"

if [[ ! -d "${BACKEND_DIR}" ]]; then
    echo "ERROR: backend package root not found at ${BACKEND_DIR}." >&2
    echo "       No backup was listed, verified or restored (#14867)." >&2
    exit 1
fi

python3 - "$@" <<'PYTHON'
"""Entry point executed by restore_kb_backup.sh"""
import argparse
import asyncio
import sys

# (#14875) knowledge._composed is the canonical knowledge-base facade; its
# BulkOperationsMixin (knowledge/bulk.py) is the backup engine that
# backup/scheduler.py drives on the schedule and that the maintenance UI calls
# through api/knowledge_maintenance.py. Nothing else in this repo backs up the
# knowledge base, so nothing else belongs here.
try:
    from knowledge._composed import get_knowledge_base
except ImportError as exc:  # pragma: no cover - operator-facing failure path
    print(
        "ERROR: the knowledge-base backup engine could not be imported "
        f"({exc}). NOTHING was listed, verified or restored - do not treat "
        "this run as a successful restore (#14875).",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="AutoBot knowledge-base backup restore utility (issue #3294)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  restore_kb_backup.sh --list
  restore_kb_backup.sh --verify --backup-file kb_backup_20260101_020000.json.gz
  restore_kb_backup.sh --backup-file kb_backup_20260101_020000.json.gz --dry-run
  restore_kb_backup.sh --run-backup
""",
    )
    p.add_argument("--list", action="store_true", help="List available backups")
    p.add_argument("--verify", action="store_true", help="Inspect a backup without restoring it")
    p.add_argument("--backup-file", help="Backup filename to restore or verify (see --list)")
    p.add_argument("--dry-run", action="store_true", help="Show what would be restored")
    p.add_argument("--overwrite", action="store_true", help="Overwrite facts that already exist")
    p.add_argument("--run-backup", action="store_true", help="Trigger a manual backup now")
    # Retired, and rejected by name rather than by argparse's generic
    # "unrecognized arguments": a caller who scripted it needs to know the
    # destination is fixed by the containment check, not merely that the flag
    # went away.
    p.add_argument("--target-dir", help=argparse.SUPPRESS)
    p.add_argument("--backup-id", help=argparse.SUPPRESS)
    return p


def _reject_retired_flags(args) -> int:
    """Retired flags fail loudly. Ignoring one would restore somewhere else silently."""
    if args.target_dir:
        print(
            "ERROR: --target-dir was removed. The knowledge-base restore path is "
            "confined to the knowledge backups directory by design (#9670); it is "
            "not caller-selectable. NOTHING was restored.",
            file=sys.stderr,
        )
        return 2
    if args.backup_id:
        print(
            "ERROR: --backup-id was replaced by --backup-file. Backups are "
            "addressed by filename - run --list to see them. NOTHING was restored.",
            file=sys.stderr,
        )
        return 2
    return 0


def _print_backups(payload: dict) -> int:
    if payload.get("status") != "success":
        print(f"ERROR: could not list backups: {payload.get('message', payload)}", file=sys.stderr)
        return 1
    backups = payload.get("backups", [])
    if not backups:
        print(f"No backups found in {payload.get('backup_dir', 'the backup directory')}.")
        return 0
    print(f"{'Filename':<44} {'Created':<26} {'Size MB':>8}  Compressed")
    print("-" * 92)
    for entry in backups:
        size_mb = entry.get("size", 0) / 1_048_576
        print(
            f"{entry.get('filename', '?'):<44} {str(entry.get('created_at', '?')):<26} "
            f"{size_mb:>8.1f}  {entry.get('compressed', False)}"
        )
    return 0


def _print_preview(payload: dict) -> int:
    """Render a dry-run/verify result. A failed inspection must not read as a clean backup."""
    if payload.get("status") != "success":
        print(f"FAILED: {payload.get('message', payload)}", file=sys.stderr)
        return 1
    print(f"OK: {payload.get('total_facts_in_backup', 0)} facts in backup")
    print(f"  version:    {payload.get('backup_version', 'unknown')}")
    print(f"  created:    {payload.get('backup_created_at', 'unknown')}")
    print(f"  embeddings: {payload.get('has_embeddings', False)}")
    return 0


def _print_restore(payload: dict) -> int:
    if payload.get("status") != "success":
        print(f"Restore FAILED: {payload.get('message', payload)}", file=sys.stderr)
        return 1
    print(
        f"Restore complete: {payload.get('restored', 0)} restored, "
        f"{payload.get('skipped', 0)} skipped, {payload.get('updated', 0)} updated, "
        f"{payload.get('errors', 0)} errors, "
        f"{payload.get('embeddings_restored', 0)} embeddings restored"
    )
    return 1 if payload.get("errors", 0) else 0


async def _run_backup(kb) -> int:
    result = await kb.create_backup()
    if result.get("status") == "success":
        print(f"Backup succeeded: {result.get('backup_name')} ({result.get('facts_count', 0)} facts)")
        return 0
    print(f"Backup FAILED: {result.get('message', result)}", file=sys.stderr)
    return 1


async def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    rejected = _reject_retired_flags(args)
    if rejected:
        return rejected

    kb = await get_knowledge_base()

    if args.list:
        return _print_backups(await kb.list_backups())

    if args.run_backup:
        return await _run_backup(kb)

    if not args.backup_file:
        print("ERROR: --backup-file required (run --list to see them)", file=sys.stderr)
        parser.print_help(sys.stderr)
        return 1

    if args.verify or args.dry_run:
        return _print_preview(await kb.restore_backup(args.backup_file, dry_run=True))

    return _print_restore(
        await kb.restore_backup(
            args.backup_file,
            overwrite_existing=args.overwrite,
            dry_run=False,
        )
    )


sys.exit(asyncio.run(main()))
PYTHON
