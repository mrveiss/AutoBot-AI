# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
PKI CLI Module
==============

Command-line interface for PKI operations.
Integrates with setup.py for automated certificate management.

Usage:
    # From command line
    python -m src.pki.cli setup
    python -m src.pki.cli status
    python -m src.pki.cli renew

    # From setup.py
    from src.pki.cli import run_pki_setup
    asyncio.run(run_pki_setup())
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pki.manager import PKIManager, setup_pki

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_pki_setup(
    force: bool = False,
    distribute: bool = True,
    configure: bool = True,
) -> bool:
    """
    Run PKI setup - main entry point for setup.py integration.

    Args:
        force: Force certificate regeneration
        distribute: Distribute certificates to VMs
        configure: Configure services for TLS

    Returns:
        True if setup successful
    """
    return await setup_pki(force=force, distribute=distribute, configure=configure)


async def run_status() -> None:
    """Display PKI status."""
    manager = PKIManager()
    manager.print_status()


async def run_renew(certificates: list = None) -> bool:
    """Renew certificates."""
    manager = PKIManager()
    return await manager.renew(certificates)


async def run_verify() -> None:
    """Verify certificate distribution on VMs."""
    manager = PKIManager()
    results = await manager.distributor.verify_distribution()

    logger.info("\nCertificate Distribution Verification")
    logger.info("=" * 40)
    for vm_name, verified in results.items():
        status = "✓" if verified else "✗"
        logger.info("  %s %s", status, vm_name)
    logger.info("")


def _create_argument_parser() -> argparse.ArgumentParser:
    """
    Create and configure the CLI argument parser.

    Issue #620.

    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        description="AutoBot PKI Management (oVirt-style)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.pki.cli setup              # Full PKI setup
  python -m src.pki.cli setup --force      # Force regenerate certificates
  python -m src.pki.cli setup --no-dist    # Generate only, don't distribute
  python -m src.pki.cli status             # Show certificate status
  python -m src.pki.cli renew              # Renew expiring certificates
  python -m src.pki.cli verify             # Verify distribution on VMs
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Setup command
    setup_parser = subparsers.add_parser("setup", help="Run PKI setup")
    setup_parser.add_argument(
        "--force", "-f", action="store_true", help="Force certificate regeneration"
    )
    setup_parser.add_argument(
        "--no-dist", action="store_true", help="Skip certificate distribution"
    )
    setup_parser.add_argument(
        "--no-config", action="store_true", help="Skip service configuration"
    )

    # Status command
    subparsers.add_parser("status", help="Show certificate status")

    # Renew command
    renew_parser = subparsers.add_parser("renew", help="Renew certificates")
    renew_parser.add_argument(
        "certificates", nargs="*", help="Specific certificates to renew (optional)"
    )

    # Verify command
    subparsers.add_parser("verify", help="Verify certificate distribution")

    return parser


def _execute_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """
    Execute the CLI command based on parsed arguments.

    Issue #620.

    Args:
        args: Parsed command line arguments
        parser: The argument parser (for help display)
    """
    if args.command == "setup":
        success = asyncio.run(
            run_pki_setup(
                force=args.force,
                distribute=not args.no_dist,
                configure=not args.no_config,
            )
        )
        sys.exit(0 if success else 1)

    elif args.command == "status":
        asyncio.run(run_status())

    elif args.command == "renew":
        success = asyncio.run(run_renew(args.certificates or None))
        sys.exit(0 if success else 1)

    elif args.command == "verify":
        asyncio.run(run_verify())

    else:
        parser.print_help()
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = _create_argument_parser()
    args = parser.parse_args()
    _execute_command(args, parser)


if __name__ == "__main__":
    main()
