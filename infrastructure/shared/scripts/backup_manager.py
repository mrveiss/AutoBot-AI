#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Backup Manager
=====================

Automated backup system for AutoBot deployments, data, configurations, and state.
Supports multiple backup strategies including local, remote, and cloud storage.

Usage:
    python scripts/backup_manager.py --backup --type full
    python scripts/backup_manager.py --backup --type incremental
    python scripts/backup_manager.py --restore --backup-id 20250821-143022
    python scripts/backup_manager.py --list
    python scripts/backup_manager.py --cleanup --days 30
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.script_utils import ScriptFormatter
from src.utils.service_registry import get_service_registry


class BackupManager:
    """Manages automated backups for AutoBot deployments."""

    def __init__(self, backup_dir: str = "backups"):
        """Initialize backup manager with backup directory and critical paths."""
        self.project_root = Path(__file__).parent.parent
        self.backup_dir = self.project_root / backup_dir
        self.backup_dir.mkdir(exist_ok=True)

        self.service_registry = get_service_registry()

        # Critical paths to backup
        self.backup_paths = {
            "data": self.project_root / "data",
            "config": self.project_root / "config",
            "docker_compose": self.project_root / "docker/compose",
            "scripts": self.project_root / "scripts",
            "deployment_configs": self.project_root / "config/deployment",
            "logs": self.project_root / "logs",
            "reports": self.project_root / "reports",
        }

        # Files to always include
        self.critical_files = [
            "run_agent.sh",
            "setup_agent.sh",
            "deploy.sh",
            "requirements.txt",
            "package.json",
            "CLAUDE.md",
            "deployment_info.json",
        ]

        print("🗄️  AutoBot Backup Manager initialized")
        print(f"   Backup Directory: {self.backup_dir}")
        print(f"   Project Root: {self.project_root}")

    def print_header(self, title: str):
        """Print formatted header."""
        ScriptFormatter.print_header(title)

    def print_step(self, step: str, status: str = "info"):
        """Print step with status."""
        ScriptFormatter.print_step(step, status)

    def generate_backup_id(self) -> str:
        """Generate unique backup ID."""
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    def calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of file."""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception:
            return "error"

    def get_docker_volumes(self) -> List[str]:
        """Get list of Docker volumes to backup."""
        try:
            result = subprocess.run(
                [
                    "docker",
                    "volume",
                    "ls",
                    "--filter",
                    "name=autobot",
                    "--format",
                    "{{.Name}}",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return [vol.strip() for vol in result.stdout.split("\n") if vol.strip()]
            return []
        except Exception:
            return []

    def backup_docker_volume(self, volume_name: str, backup_path: Path) -> bool:
        """Backup a Docker volume."""
        try:
            self.print_step(f"Backing up Docker volume: {volume_name}", "running")

            # Create temporary container to access volume
            volume_backup_path = backup_path / "docker_volumes" / f"{volume_name}.tar"
            volume_backup_path.parent.mkdir(parents=True, exist_ok=True)

            cmd = [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{volume_name}:/volume:ro",
                "-v",
                f"{volume_backup_path.parent}:/backup",
                "alpine:latest",
                "tar",
                "-czf",
                f"/backup/{volume_name}.tar",
                "-C",
                "/volume",
                ".",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                self.print_step(f"Docker volume {volume_name} backed up", "success")
                return True
            else:
                self.print_step(
                    f"Failed to backup volume {volume_name}: {result.stderr}", "error"
                )
                return False

        except Exception as e:
            self.print_step(f"Error backing up volume {volume_name}: {e}", "error")
            return False

    def create_backup_metadata(
        self, backup_id: str, backup_type: str, paths: Dict[str, Path]
    ) -> Dict[str, Any]:
        """Create backup metadata."""
        deployment_info = self.service_registry.get_deployment_info()

        # Calculate sizes and checksums
        file_info = {}
        total_size = 0

        for category, path in paths.items():
            if path.exists():
                if path.is_file():
                    size = path.stat().st_size
                    checksum = self.calculate_checksum(path)
                    file_info[category] = {
                        "path": str(path),
                        "size": size,
                        "checksum": checksum,
                        "type": "file",
                    }
                    total_size += size
                elif path.is_dir():
                    dir_size = sum(
                        f.stat().st_size for f in path.rglob("*") if f.is_file()
                    )
                    file_count = len(list(path.rglob("*")))
                    file_info[category] = {
                        "path": str(path),
                        "size": dir_size,
                        "file_count": file_count,
                        "type": "directory",
                    }
                    total_size += dir_size

        metadata = {
            "backup_id": backup_id,
            "backup_type": backup_type,
            "timestamp": datetime.now().isoformat(),
            "deployment_mode": deployment_info["deployment_mode"],
            "total_size": total_size,
            "file_info": file_info,
            "docker_volumes": self.get_docker_volumes(),
            "version": "1.0",
            "autobot_version": deployment_info.get("deployer_version", "unknown"),
            "hostname": os.uname().nodename,
            "python_version": sys.version,
        }

        return metadata

    def create_full_backup(self) -> str:
        """Create a full backup of all AutoBot components."""
        backup_id = self.generate_backup_id()
        backup_path = self.backup_dir / f"full_{backup_id}"
        backup_path.mkdir(exist_ok=True)

        self.print_header(f"Creating Full Backup: {backup_id}")

        try:
            # Backup critical paths
            backed_up_paths = {}

            for category, source_path in self.backup_paths.items():
                if source_path.exists():
                    dest_path = backup_path / category
                    self.print_step(f"Backing up {category}: {source_path}", "running")

                    if source_path.is_dir():
                        shutil.copytree(
                            source_path, dest_path, ignore_dangling_symlinks=True
                        )
                    else:
                        shutil.copy2(source_path, dest_path)

                    backed_up_paths[category] = source_path
                    self.print_step(f"Backed up {category}", "success")
                else:
                    self.print_step(
                        f"Skipping {category} (not found): {source_path}", "warning"
                    )

            # Backup critical files
            critical_files_path = backup_path / "critical_files"
            critical_files_path.mkdir(exist_ok=True)

            for filename in self.critical_files:
                source_file = self.project_root / filename
                if source_file.exists():
                    dest_file = critical_files_path / filename
                    shutil.copy2(source_file, dest_file)
                    backed_up_paths[f"critical_{filename}"] = source_file
                    self.print_step(f"Backed up critical file: {filename}", "success")

            # Backup Docker volumes
            docker_volumes = self.get_docker_volumes()
            if docker_volumes:
                self.print_step(
                    f"Found {len(docker_volumes)} Docker volumes to backup", "info"
                )
                for volume in docker_volumes:
                    self.backup_docker_volume(volume, backup_path)

            # Create backup metadata
            metadata = self.create_backup_metadata(backup_id, "full", backed_up_paths)
            metadata_file = backup_path / "backup_metadata.json"

            with open(metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)

            # Create compressed archive
            archive_path = self.backup_dir / f"autobot_full_backup_{backup_id}.tar.gz"
            self.print_step(
                f"Creating compressed archive: {archive_path.name}", "running"
            )

            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(backup_path, arcname=f"autobot_backup_{backup_id}")

            # Cleanup temporary directory
            shutil.rmtree(backup_path)

            # Verify backup
            if archive_path.exists():
                size_mb = archive_path.stat().st_size / (1024 * 1024)
                self.print_step(
                    f"Full backup created successfully: {archive_path.name} ({size_mb:.1f} MB)",
                    "success",
                )

                # Save backup registry entry
                self.register_backup(backup_id, "full", str(archive_path), metadata)

                return backup_id
            else:
                self.print_step("Backup creation failed", "error")
                return None

        except Exception as e:
            self.print_step(f"Backup failed: {e}", "error")
            if backup_path.exists():
                shutil.rmtree(backup_path)
            return None

    def _find_base_backup_id(self, base_backup_id: Optional[str]) -> Optional[str]:
        """
        Find base backup ID for incremental comparison.

        Issue #281: Extracted from create_incremental_backup to reduce function length.

        Returns:
            Base backup ID or None if no backups exist.
        """
        if base_backup_id:
            return base_backup_id

        backups = self.list_backups()
        if not backups:
            return None

        # Use most recent backup as base
        return max(backups.keys())

    def _detect_changed_paths(self, base_metadata: Dict[str, Any]) -> Dict[str, Path]:
        """
        Detect paths that changed since base backup.

        Issue #281: Extracted from create_incremental_backup to reduce function length.

        Returns:
            Dictionary of changed category -> path mappings.
        """
        changed_paths = {}

        for category, source_path in self.backup_paths.items():
            if not source_path.exists():
                continue

            # Compare with base backup
            if category in base_metadata.get("file_info", {}):
                base_info = base_metadata["file_info"][category]

                if source_path.is_file():
                    current_checksum = self.calculate_checksum(source_path)
                    if current_checksum != base_info.get("checksum"):
                        changed_paths[category] = source_path
                        self.print_step(f"File changed: {category}", "info")
                else:
                    # For directories, check modification time
                    current_mtime = source_path.stat().st_mtime
                    base_time = datetime.fromisoformat(
                        base_metadata["timestamp"]
                    ).timestamp()

                    if current_mtime > base_time:
                        changed_paths[category] = source_path
                        self.print_step(f"Directory changed: {category}", "info")
            else:
                # New path not in base backup
                changed_paths[category] = source_path
                self.print_step(f"New path: {category}", "info")

        return changed_paths

    def _backup_changed_paths(
        self, changed_paths: Dict[str, Path], backup_path: Path
    ) -> None:
        """
        Copy changed paths to backup directory.

        Issue #281: Extracted from create_incremental_backup to reduce function length.
        """
        for category, source_path in changed_paths.items():
            dest_path = backup_path / category
            self.print_step(f"Backing up changed: {category}", "running")

            if source_path.is_dir():
                shutil.copytree(source_path, dest_path, ignore_dangling_symlinks=True)
            else:
                shutil.copy2(source_path, dest_path)

    def _create_incremental_archive(
        self,
        backup_id: str,
        backup_path: Path,
        base_backup_id: str,
        changed_paths: Dict[str, Path],
    ) -> Optional[str]:
        """
        Create archive and register incremental backup.

        Issue #281: Extracted from create_incremental_backup to reduce function length.

        Returns:
            Backup ID on success, None on failure.
        """
        # Create metadata
        metadata = self.create_backup_metadata(backup_id, "incremental", changed_paths)
        metadata["base_backup_id"] = base_backup_id

        metadata_file = backup_path / "backup_metadata.json"
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        # Create archive
        archive_path = (
            self.backup_dir / f"autobot_incremental_backup_{backup_id}.tar.gz"
        )

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(backup_path, arcname=f"autobot_incremental_{backup_id}")

        # Cleanup
        shutil.rmtree(backup_path)

        if archive_path.exists():
            size_mb = archive_path.stat().st_size / (1024 * 1024)
            self.print_step(
                f"Incremental backup created: {archive_path.name} ({size_mb:.1f} MB)",
                "success",
            )

            self.register_backup(backup_id, "incremental", str(archive_path), metadata)
            return backup_id

        return None

    def create_incremental_backup(self, base_backup_id: Optional[str] = None) -> str:
        """Create incremental backup (only changed files since last backup)."""
        backup_id = self.generate_backup_id()
        backup_path = self.backup_dir / f"incremental_{backup_id}"
        backup_path.mkdir(exist_ok=True)

        self.print_header(f"Creating Incremental Backup: {backup_id}")

        # Find base backup for comparison
        base_backup_id = self._find_base_backup_id(base_backup_id)
        if not base_backup_id:
            self.print_step(
                "No base backup found, creating full backup instead", "warning"
            )
            return self.create_full_backup()

        self.print_step(f"Using base backup: {base_backup_id}", "info")

        try:
            base_metadata = self.get_backup_metadata(base_backup_id)
            if not base_metadata:
                self.print_step(
                    "Base backup metadata not found, creating full backup", "warning"
                )
                return self.create_full_backup()

            # Detect changed paths
            changed_paths = self._detect_changed_paths(base_metadata)

            if not changed_paths:
                self.print_step("No changes detected since last backup", "success")
                shutil.rmtree(backup_path)
                return base_backup_id

            # Backup changed paths and create archive
            self._backup_changed_paths(changed_paths, backup_path)
            return self._create_incremental_archive(
                backup_id, backup_path, base_backup_id, changed_paths
            )

        except Exception as e:
            self.print_step(f"Incremental backup failed: {e}", "error")
            if backup_path.exists():
                shutil.rmtree(backup_path)
            return None

    def register_backup(
        self,
        backup_id: str,
        backup_type: str,
        archive_path: str,
        metadata: Dict[str, Any],
    ):
        """Register backup in registry."""
        registry_file = self.backup_dir / "backup_registry.json"

        registry = {}
        if registry_file.exists():
            try:
                with open(registry_file, "r") as f:
                    registry = json.load(f)
            except Exception:
                registry = {}

        registry[backup_id] = {
            "backup_id": backup_id,
            "backup_type": backup_type,
            "archive_path": archive_path,
            "created_at": metadata["timestamp"],
            "size": metadata["total_size"],
            "deployment_mode": metadata["deployment_mode"],
        }

        with open(registry_file, "w") as f:
            json.dump(registry, f, indent=2)

    def list_backups(self) -> Dict[str, Any]:
        """List all available backups."""
        registry_file = self.backup_dir / "backup_registry.json"

        if not registry_file.exists():
            return {}

        try:
            with open(registry_file, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def get_backup_metadata(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for specific backup."""
        backups = self.list_backups()

        if backup_id not in backups:
            return None

        backup_info = backups[backup_id]
        archive_path = Path(backup_info["archive_path"])

        if not archive_path.exists():
            return None

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                # Find metadata file in archive
                metadata_member = None
                for member in tar.getmembers():
                    if member.name.endswith("backup_metadata.json"):
                        metadata_member = member
                        break

                if metadata_member:
                    metadata_file = tar.extractfile(metadata_member)
                    return json.load(metadata_file)

        except Exception:
            pass  # Archive read/parse error, metadata unavailable

        return None

    def restore_backup(
        self, backup_id: str, target_dir: Optional[str] = None, dry_run: bool = False
    ) -> bool:
        """Restore backup to target directory."""
        if not target_dir:
            target_dir = self.project_root

        target_path = Path(target_dir)

        self.print_header(f"Restoring Backup: {backup_id}")

        if dry_run:
            self.print_step("DRY RUN MODE - No changes will be made", "warning")

        backups = self.list_backups()
        if backup_id not in backups:
            self.print_step(f"Backup {backup_id} not found", "error")
            return False

        backup_info = backups[backup_id]
        archive_path = Path(backup_info["archive_path"])

        if not archive_path.exists():
            self.print_step(f"Backup archive not found: {archive_path}", "error")
            return False

        try:
            metadata = self.get_backup_metadata(backup_id)
            if metadata:
                self.print_step(f"Backup type: {metadata['backup_type']}", "info")
                self.print_step(f"Created: {metadata['timestamp']}", "info")
                self.print_step(
                    f"Deployment mode: {metadata['deployment_mode']}", "info"
                )

            # Extract archive to temporary location
            temp_extract_path = self.backup_dir / f"restore_temp_{backup_id}"

            if not dry_run:
                self.print_step("Extracting archive to temporary location", "running")
                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.extractall(temp_extract_path)

                # Find extracted backup directory
                extracted_dirs = list(temp_extract_path.glob("autobot_*"))
                if not extracted_dirs:
                    self.print_step("No backup directory found in archive", "error")
                    return False

                backup_content_path = extracted_dirs[0]

                # Restore files
                restored_items = 0
                for item in backup_content_path.iterdir():
                    if item.name == "backup_metadata.json":
                        continue

                    dest_path = target_path / item.name
                    self.print_step(f"Restoring: {item.name} -> {dest_path}", "running")

                    if item.is_dir():
                        if dest_path.exists():
                            shutil.rmtree(dest_path)
                        shutil.copytree(item, dest_path)
                    else:
                        if dest_path.exists():
                            dest_path.unlink()
                        shutil.copy2(item, dest_path)

                    restored_items += 1
                    self.print_step(f"Restored: {item.name}", "success")

                # Cleanup temporary directory
                shutil.rmtree(temp_extract_path)

                self.print_step(
                    f"Restore completed: {restored_items} items restored", "success"
                )
            else:
                # Dry run - just show what would be restored
                with tarfile.open(archive_path, "r:gz") as tar:
                    self.print_step("Files that would be restored:", "info")
                    for member in tar.getmembers():
                        if member.isfile() and not member.name.endswith(
                            "backup_metadata.json"
                        ):
                            self.print_step(f"  - {member.name}", "info")

            return True

        except Exception as e:
            self.print_step(f"Restore failed: {e}", "error")
            # Cleanup on failure
            temp_path = self.backup_dir / f"restore_temp_{backup_id}"
            if temp_path.exists():
                shutil.rmtree(temp_path)
            return False

    def cleanup_old_backups(self, days: int = 30) -> int:
        """Remove backups older than specified days."""
        self.print_header(f"Cleaning Up Backups Older Than {days} Days")

        cutoff_date = datetime.now() - timedelta(days=days)
        backups = self.list_backups()

        removed_count = 0
        total_size_freed = 0

        for backup_id, backup_info in backups.items():
            created_date = datetime.fromisoformat(backup_info["created_at"])

            if created_date < cutoff_date:
                archive_path = Path(backup_info["archive_path"])

                if archive_path.exists():
                    file_size = archive_path.stat().st_size
                    archive_path.unlink()
                    total_size_freed += file_size
                    removed_count += 1
                    self.print_step(
                        f"Removed old backup: {backup_id} ({created_date.strftime('%Y-%m-%d')})",
                        "success",
                    )

                # Remove from registry
                del backups[backup_id]

        # Update registry
        if removed_count > 0:
            registry_file = self.backup_dir / "backup_registry.json"
            with open(registry_file, "w") as f:
                json.dump(backups, f, indent=2)

        size_mb = total_size_freed / (1024 * 1024)
        self.print_step(
            f"Cleanup completed: {removed_count} backups removed, {size_mb:.1f} MB freed",
            "success",
        )

        return removed_count

    def verify_backup(self, backup_id: str) -> bool:
        """Verify backup integrity."""
        self.print_header(f"Verifying Backup: {backup_id}")

        backups = self.list_backups()
        if backup_id not in backups:
            self.print_step(f"Backup {backup_id} not found", "error")
            return False

        backup_info = backups[backup_id]
        archive_path = Path(backup_info["archive_path"])

        if not archive_path.exists():
            self.print_step(f"Backup archive missing: {archive_path}", "error")
            return False

        try:
            # Test archive integrity
            self.print_step("Testing archive integrity", "running")
            with tarfile.open(archive_path, "r:gz") as tar:
                # Verify all members can be read
                for member in tar.getmembers():
                    if member.isfile():
                        tar.extractfile(member).read()

            self.print_step("Archive integrity verified", "success")

            # Verify metadata
            metadata = self.get_backup_metadata(backup_id)
            if metadata:
                self.print_step("Metadata found and readable", "success")
                self.print_step(f"Backup type: {metadata['backup_type']}", "info")
                self.print_step(f"Total size: {metadata['total_size']} bytes", "info")
            else:
                self.print_step("Metadata missing or unreadable", "warning")

            return True

        except Exception as e:
            self.print_step(f"Backup verification failed: {e}", "error")
            return False


def _handle_backup_command(backup_manager, args) -> int:
    """Handle --backup command (Issue #315: extracted helper)."""
    if args.type == "full":
        backup_id = backup_manager.create_full_backup()
    else:
        backup_id = backup_manager.create_incremental_backup()

    if backup_id:
        print(f"\n✅ Backup completed successfully: {backup_id}")
        return 0
    print("\n❌ Backup failed")
    return 1


def _handle_restore_command(backup_manager, args) -> int:
    """Handle --restore command (Issue #315: extracted helper)."""
    if not args.backup_id:
        print("❌ --backup-id required for restore")
        return 1

    success = backup_manager.restore_backup(
        args.backup_id, args.target_dir, args.dry_run
    )
    return 0 if success else 1


def _handle_list_command(backup_manager, args) -> int:
    """Handle --list command (Issue #315: extracted helper)."""
    backups = backup_manager.list_backups()

    if not backups:
        print("No backups found")
        return 0

    print("\n📋 Available Backups:")
    print("=" * 80)
    print(f"{'Backup ID':<20} {'Type':<12} {'Date':<20} {'Size (MB)':<10} {'Mode':<15}")
    print("-" * 80)

    for backup_id, info in sorted(backups.items(), reverse=True):
        created = datetime.fromisoformat(info["created_at"])
        size_mb = info["size"] / (1024 * 1024)
        print(
            f"{backup_id:<20} {info['backup_type']:<12} "
            f"{created.strftime('%Y-%m-%d %H:%M'):<20} {size_mb:<10.1f} {info['deployment_mode']:<15}"
        )
    return 0


def _handle_cleanup_command(backup_manager, args) -> int:
    """Handle --cleanup command (Issue #315: extracted helper)."""
    backup_manager.cleanup_old_backups(args.days)
    return 0


def _handle_verify_command(backup_manager, args) -> int:
    """Handle --verify command (Issue #315: extracted helper)."""
    if not args.backup_id:
        print("❌ --backup-id required for verify")
        return 1

    success = backup_manager.verify_backup(args.backup_id)
    return 0 if success else 1


def main():
    """Entry point for AutoBot backup manager CLI."""
    parser = argparse.ArgumentParser(
        description="AutoBot Backup Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/backup_manager.py --backup --type full
  python scripts/backup_manager.py --backup --type incremental
  python scripts/backup_manager.py --restore --backup-id 20250821-143022
  python scripts/backup_manager.py --list
  python scripts/backup_manager.py --cleanup --days 30
  python scripts/backup_manager.py --verify --backup-id 20250821-143022
        """,
    )

    parser.add_argument("--backup", action="store_true", help="Create backup")
    parser.add_argument("--restore", action="store_true", help="Restore backup")
    parser.add_argument("--list", action="store_true", help="List backups")
    parser.add_argument("--cleanup", action="store_true", help="Cleanup old backups")
    parser.add_argument("--verify", action="store_true", help="Verify backup")

    parser.add_argument(
        "--type", choices=["full", "incremental"], default="full", help="Backup type"
    )
    parser.add_argument("--backup-id", help="Backup ID for restore/verify")
    parser.add_argument("--target-dir", help="Target directory for restore")
    parser.add_argument("--days", type=int, default=30, help="Days for cleanup")
    parser.add_argument("--backup-dir", default="backups", help="Backup directory")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")

    args = parser.parse_args()

    if not any([args.backup, args.restore, args.list, args.cleanup, args.verify]):
        parser.print_help()
        return 1

    backup_manager = BackupManager(args.backup_dir)

    # Command dispatch table (Issue #315: reduces nesting)
    command_handlers = {
        "backup": (_handle_backup_command, args.backup),
        "restore": (_handle_restore_command, args.restore),
        "list": (_handle_list_command, args.list),
        "cleanup": (_handle_cleanup_command, args.cleanup),
        "verify": (_handle_verify_command, args.verify),
    }

    try:
        for cmd_name, (handler, is_active) in command_handlers.items():
            if is_active:
                return handler(backup_manager, args)
        return 0

    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
