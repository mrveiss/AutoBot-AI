#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Startup Log Rotation Script for AutoBot

This script rotates startup logs every time the system starts.
It should be called at the beginning of the main startup sequence.
"""

import os
import shutil
import gzip
from datetime import datetime, timedelta
from pathlib import Path


def rotate_startup_logs():
    """Rotate startup logs according to configuration"""

    logs_dir = Path("logs")
    startup_files = [
        "startup.log",
        "startup.debug.log",
        "startup.info.log",
        "startup.warning.log",
        "startup.error.log",
        "startup.critical.log"
    ]

    # Configuration (would normally come from config)
    max_backup_count = 10
    compress_backups = True
    delete_old_logs_after_days = 90
    backup_naming = "timestamp"  # or "sequential"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"🔄 Rotating startup logs at {datetime.now()}")

    for log_file in startup_files:
        log_path = logs_dir / log_file

        if log_path.exists() and log_path.stat().st_size > 0:
            # Create backup filename
            if backup_naming == "timestamp":
                backup_name = f"{log_file}.{timestamp}"
            else:  # sequential
                backup_name = f"{log_file}.1"

            backup_path = logs_dir / backup_name

            # Move current log to backup
            shutil.move(str(log_path), str(backup_path))
            print(f"📁 Rotated {log_file} → {backup_name}")

            # Compress if enabled
            if compress_backups:
                with open(backup_path, 'rb') as f_in:
                    with gzip.open(f"{backup_path}.gz", 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(backup_path)
                print(f"🗜️  Compressed {backup_name} → {backup_name}.gz")

            # Create new empty log file
            log_path.touch()
            print(f"📄 Created new {log_file}")

    # Clean up old backups
    cleanup_old_logs(logs_dir, delete_old_logs_after_days, max_backup_count)

    print("✅ Startup log rotation completed")


def cleanup_old_logs(logs_dir, days_to_keep, max_backups):
    """Clean up old log backups"""

    cutoff_date = datetime.now() - timedelta(days=days_to_keep)

    # Find all startup log backups
    startup_backups = []
    for file_path in logs_dir.glob("startup.*.log*"):
        if file_path.is_file():
            startup_backups.append(file_path)

    # Sort by modification time (newest first)
    startup_backups.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    deleted_count = 0

    # Delete backups beyond max count
    if len(startup_backups) > max_backups:
        for backup in startup_backups[max_backups:]:
            os.remove(backup)
            deleted_count += 1
            print(f"🗑️  Deleted excess backup: {backup.name}")

    # Delete backups older than cutoff date
    for backup in startup_backups:
        file_time = datetime.fromtimestamp(backup.stat().st_mtime)
        if file_time < cutoff_date:
            os.remove(backup)
            deleted_count += 1
            print(f"🗑️  Deleted old backup: {backup.name}")

    if deleted_count > 0:
        print(f"🧹 Cleaned up {deleted_count} old log backups")


if __name__ == "__main__":
    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)
    rotate_startup_logs()
