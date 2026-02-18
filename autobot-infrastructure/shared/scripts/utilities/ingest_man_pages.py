#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Man Page Ingestion Script for AutoBot

This script automatically ingests common command manuals from the system
into the AutoBot knowledge base for enhanced command assistance.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from command_manual_manager import CommandManualManager  # noqa: E402

# Issue #281: Essential commands extracted from get_essential_commands
# Tuple of 119 command names organized by category
ESSENTIAL_COMMANDS = (
    # File Operations
    "ls",
    "cd",
    "pwd",
    "mkdir",
    "rmdir",
    "rm",
    "cp",
    "mv",
    "cat",
    "less",
    "more",
    "head",
    "tail",
    "touch",
    "ln",
    "find",
    "locate",
    "which",
    "whereis",
    "file",
    "stat",
    "chmod",
    "chown",
    "chgrp",
    "umask",
    # Archives and Compression
    "tar",
    "gzip",
    "gunzip",
    "zip",
    "unzip",
    "bzip2",
    "bunzip2",
    # Text Processing
    "grep",
    "awk",
    "sed",
    "tr",
    "cut",
    "sort",
    "uniq",
    "wc",
    "dif",
    "comm",
    "join",
    "paste",
    "fmt",
    "fold",
    # Network Commands
    "ping",
    "traceroute",
    "netstat",
    "ss",
    "ifconfig",
    "ip",
    "route",
    "arp",
    "wget",
    "curl",
    "ssh",
    "scp",
    "rsync",
    "nc",
    "nmap",
    "nslookup",
    "dig",
    # Process Management
    "ps",
    "top",
    "htop",
    "jobs",
    "bg",
    "fg",
    "nohup",
    "kill",
    "killall",
    "pgrep",
    "pkill",
    "pido",
    "nice",
    "renice",
    "screen",
    "tmux",
    # System Information
    "uname",
    "whoami",
    "id",
    "groups",
    "w",
    "who",
    "uptime",
    "free",
    "d",
    "du",
    "lscpu",
    "lsmem",
    "lsblk",
    "lsusb",
    "lspci",
    "dmidecode",
    "lshw",
    # System Control
    "sudo",
    "su",
    "systemctl",
    "service",
    "mount",
    "umount",
    "halt",
    "shutdown",
    "reboot",
    "crontab",
    "at",
    # Package Management
    "apt",
    "apt-get",
    "dpkg",
    "yum",
    "dn",
    "rpm",
    "pip",
    "npm",
    "git",
    # Development Tools
    "make",
    "gcc",
    "g++",
    "python",
    "python3",
    "node",
    "java",
    "javac",
    "docker",
    # Text Editors and Utilities
    "vi",
    "vim",
    "nano",
    "emacs",
    "man",
    "info",
    "help",
    "history",
    "alias",
    "which",
    "type",
    # Disk and Filesystem
    "fdisk",
    "parted",
    "mkfs",
    "fsck",
    "lso",
    "fuser",
    # Security and Permissions
    "gpg",
    "openssl",
    "ssh-keygen",
    "passwd",
    "chage",
)

# Issue #281: Advanced commands extracted from get_advanced_commands
# Tuple of 73 command names for specialized tasks
ADVANCED_COMMANDS = (
    # Advanced Network Tools
    "tcpdump",
    "wireshark",
    "iptables",
    "ufw",
    "firewall-cmd",
    "ethtool",
    "iwconfig",
    "nmcli",
    "hostnamectl",
    # Advanced System Tools
    "strace",
    "ltrace",
    "gdb",
    "valgrind",
    "per",
    "sysctl",
    "dmesg",
    "journalctl",
    "systemd-analyze",
    # Advanced File Operations
    "rsnapshot",
    "rdiff-backup",
    "duplicity",
    "borgbackup",
    "rclone",
    "syncthing",
    # Container and Virtualization
    "podman",
    "kubectl",
    "helm",
    "vagrant",
    "qemu",
    "virt-manager",
    "virsh",
    # Database Tools
    "mysql",
    "psql",
    "sqlite3",
    "redis-cli",
    "mongo",
    # Web Development
    "apache2ctl",
    "nginx",
    "certbot",
    "ab",
    "siege",
    # Advanced Text Processing
    "jq",
    "yq",
    "xmllint",
    "csvkit",
    "pandoc",
    # Performance Monitoring
    "iotop",
    "nethogs",
    "vnstat",
    "sar",
    "iostat",
    "vmstat",
    "mpstat",
    "pidstat",
    # Security Tools
    "nessus",
    "openvas",
    "nikto",
    "sqlmap",
    "john",
    "hashcat",
    "aircrack-ng",
    "metasploit",
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ManPageIngester:
    """Handles bulk ingestion of man pages into the knowledge base."""

    def __init__(self, db_path: str = "data/knowledge_base.db"):
        """Initialize the ingester.

        Args:
            db_path: Path to the knowledge base database
        """
        self.manager = CommandManualManager(db_path)
        self.stats = {"attempted": 0, "successful": 0, "failed": 0, "skipped": 0}

    def get_essential_commands(self) -> list:
        """Get list of essential commands to ingest.

        Issue #281: Refactored to use module-level ESSENTIAL_COMMANDS constant.
        Reduced from 167 to 5 lines (97% reduction).

        Returns:
            List of essential command names
        """
        return list(ESSENTIAL_COMMANDS)

    def get_advanced_commands(self) -> list:
        """Get list of advanced/specialized commands.

        Issue #281: Refactored to use module-level ADVANCED_COMMANDS constant.
        Reduced from 79 to 5 lines (94% reduction).

        Returns:
            List of advanced command names
        """
        return list(ADVANCED_COMMANDS)

    def ingest_command_list(self, commands: list, category: str = "essential") -> None:
        """Ingest a list of commands.

        Args:
            commands: List of command names to ingest
            category: Category label for logging
        """
        logger.info("Starting ingestion of %s %s commands", len(commands), category)

        for command in commands:
            self.stats["attempted"] += 1

            try:
                # Check if already exists
                existing = self.manager.get_manual(command)
                if existing:
                    logger.info("Command '%s' already exists, skipping", command)
                    self.stats["skipped"] += 1
                    continue

                # Attempt to ingest
                success = self.manager.ingest_command(command)
                if success:
                    logger.info("Successfully ingested: %s", command)
                    self.stats["successful"] += 1
                else:
                    logger.warning("Failed to ingest: %s", command)
                    self.stats["failed"] += 1

            except Exception as e:
                logger.error("Error ingesting command '%s': %s", command, e)
                self.stats["failed"] += 1

    def ingest_all_essential(self) -> None:
        """Ingest all essential commands."""
        essential_commands = self.get_essential_commands()
        self.ingest_command_list(essential_commands, "essential")

    def ingest_all_advanced(self) -> None:
        """Ingest all advanced commands."""
        advanced_commands = self.get_advanced_commands()
        self.ingest_command_list(advanced_commands, "advanced")

    def ingest_custom_list(self, command_file: str) -> None:
        """Ingest commands from a custom file.

        Args:
            command_file: Path to file containing command names (one per line)
        """
        try:
            with open(command_file, "r") as f:
                commands = [
                    line.strip()
                    for line in f
                    if line.strip() and not line.startswith("#")
                ]

            logger.info("Loaded %s commands from %s", len(commands), command_file)
            self.ingest_command_list(commands, "custom")

        except Exception as e:
            logger.error("Failed to load commands from %s: %s", command_file, e)

    def print_statistics(self) -> None:
        """Print ingestion statistics."""
        logger.info("\n" + "=" * 50)
        logger.info("COMMAND MANUAL INGESTION STATISTICS")
        logger.info("=" * 50)
        logger.info(f"Commands attempted: {self.stats['attempted']}")
        logger.info(f"Successfully ingested: {self.stats['successful']}")
        logger.error(f"Failed to ingest: {self.stats['failed']}")
        logger.info(f"Skipped (already exists): {self.stats['skipped']}")

        if self.stats["attempted"] > 0:
            success_rate = (self.stats["successful"] / self.stats["attempted"]) * 100
            logger.info(f"Success rate: {success_rate:.1f}%")

        logger.info("=" * 50)

    def verify_ingestion(self, sample_commands: list = None) -> None:
        """Verify that ingested commands are properly stored.

        Args:
            sample_commands: Optional list of commands to verify
        """
        if sample_commands is None:
            sample_commands = ["ls", "cat", "grep", "ps", "ifconfig"]

        logger.info("\nVerifying ingestion...")
        for command in sample_commands:
            manual = self.manager.get_manual(command)
            if manual:
                logger.info(f"✓ {command}: {manual.description[:50]}...")
            else:
                logger.info(f"✗ {command}: Not found in knowledge base")


def main():
    """Main function for the ingestion script."""
    parser = argparse.ArgumentParser(
        description="Ingest command manuals into AutoBot knowledge base"
    )
    parser.add_argument(
        "--mode",
        choices=["essential", "advanced", "all", "custom"],
        default="essential",
        help="Ingestion mode (default: essential)",
    )
    parser.add_argument(
        "--custom-file", help="Path to custom command list file (for custom mode)"
    )
    parser.add_argument(
        "--db-path",
        default="data/knowledge_base.db",
        help="Path to knowledge base database",
    )
    parser.add_argument(
        "--verify", action="store_true", help="Verify ingestion after completion"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force re-ingestion of existing commands"
    )

    args = parser.parse_args()

    # Ensure data directory exists
    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize ingester
    ingester = ManPageIngester(args.db_path)

    # Perform ingestion based on mode
    if args.mode == "essential":
        ingester.ingest_all_essential()
    elif args.mode == "advanced":
        ingester.ingest_all_advanced()
    elif args.mode == "all":
        ingester.ingest_all_essential()
        ingester.ingest_all_advanced()
    elif args.mode == "custom":
        if not args.custom_file:
            logger.error("Error: --custom-file required for custom mode")
            sys.exit(1)
        ingester.ingest_custom_list(args.custom_file)

    # Print statistics
    ingester.print_statistics()

    # Verify if requested
    if args.verify:
        ingester.verify_ingestion()

    logger.info("\nIngestion complete!")


if __name__ == "__main__":
    main()
