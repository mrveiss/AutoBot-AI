# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
mTLS Migration Script - Issue #725

Orchestrates the migration from password-based to mTLS authentication.
Implements dual-auth transition (password + TLS) before full mTLS.

Usage:
    # Phase 2: Enable Redis TLS (dual-auth)
    python scripts/security/mtls-migrate.py --phase redis-dual-auth

    # Phase 3: Enable Backend TLS
    python scripts/security/mtls-migrate.py --phase backend-tls

    # Phase 4: Verify all services
    python scripts/security/mtls-migrate.py --phase verify

    # Full migration (all phases)
    python scripts/security/mtls-migrate.py --phase all

    # Rollback
    python scripts/security/mtls-migrate.py --rollback redis
"""

import argparse
import asyncio
import datetime
import logging
import os
import secrets
import shlex
import string
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pki.config import VM_DEFINITIONS, TLSConfig
from pki.configurator import ServiceConfigurator
from pki.distributor import CertificateDistributor
from pki.generator import CertificateGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class MTLSMigration:
    """Orchestrates mTLS migration phases."""

    # Admin credentials file - stored separately from app config
    ADMIN_CREDS_FILE = PROJECT_ROOT / "certs" / ".redis-admin-credentials"

    def __init__(self):
        self.config = TLSConfig()
        self.generator = CertificateGenerator(self.config)
        self.distributor = CertificateDistributor(self.config)
        self.configurator = ServiceConfigurator(self.config)
        self.env_file = PROJECT_ROOT / ".env"

    def _generate_admin_password(self) -> str:
        """Generate a secure admin password (shell-safe characters only)."""
        # Avoid special chars that cause shell escaping issues
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(48))

    def _save_admin_credentials(self, username: str, password: str) -> None:
        """Save admin credentials to secure file (not in app config)."""
        self.ADMIN_CREDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.ADMIN_CREDS_FILE, "w", encoding="utf-8") as f:
            f.write("# Redis Admin Credentials - Issue #725\n")
            f.write("# DO NOT use in application - emergency recovery only\n")
            f.write(f"# Created: {datetime.datetime.now().isoformat()}\n")
            f.write(f"REDIS_ADMIN_USER={username}\n")
            f.write(f"REDIS_ADMIN_PASSWORD={password}\n")
        # Secure file permissions (owner read/write only)
        os.chmod(self.ADMIN_CREDS_FILE, 0o600)
        logger.info(f"Admin credentials saved to: {self.ADMIN_CREDS_FILE}")

    def _get_admin_credentials(self) -> Optional[tuple]:
        """Get admin credentials from secure file."""
        if not self.ADMIN_CREDS_FILE.exists():
            return None
        username = None
        password = None
        with open(self.ADMIN_CREDS_FILE, encoding="utf-8") as f:
            for line in f:
                if line.startswith("REDIS_ADMIN_USER="):
                    username = line.split("=", 1)[1].strip()
                elif line.startswith("REDIS_ADMIN_PASSWORD="):
                    password = line.split("=", 1)[1].strip()
        if username and password:
            return (username, password)
        return None

    async def setup_admin_user(self) -> bool:
        """
        Create a separate Redis admin user for emergency access.

        This user:
        - Has full permissions (+@all)
        - Uses password authentication (works even when mTLS is required)
        - Is NOT used by the application
        - Can re-enable password auth if needed
        """
        logger.info("=" * 60)
        logger.info("Setting up Redis Admin User")
        logger.info("=" * 60)

        import asyncssh

        redis_ip = VM_DEFINITIONS.get("redis", "172.16.168.23")
        admin_user = "autobot_admin"
        admin_password = self._generate_admin_password()

        try:
            # Get current Redis password for authentication
            current_password = self._get_redis_password()
            if not current_password:
                logger.error("Cannot get current Redis password from .env")
                return False

            async with asyncssh.connect(
                redis_ip,
                username=self.config.ssh_user,
                client_keys=[str(self.config.ssh_key_path)],
                known_hosts=None,
                connect_timeout=10,
            ) as conn:
                # Create admin user with ACL - escape password for shell safety
                # +@all = all commands, ~* = all keys, &* = all channels
                escaped_pass = shlex.quote(current_password)
                acl_cmd = (
                    f"redis-cli --no-auth-warning -a {escaped_pass} "
                    f"ACL SETUSER {admin_user} on \\>{admin_password} ~* \\&* +@all"
                )
                result = await conn.run(acl_cmd)
                if result.returncode != 0:
                    logger.error(f"Failed to create admin user: {result.stderr}")
                    return False

                # Persist config using CONFIG REWRITE (ACL file not configured)
                save_result = await conn.run(
                    f"redis-cli --no-auth-warning -a {escaped_pass} CONFIG REWRITE"
                )
                if save_result.returncode != 0:
                    logger.warning(
                        "CONFIG REWRITE failed - user may not persist after restart"
                    )

                logger.info(f"Admin user '{admin_user}' created successfully")

            # Save credentials to secure file
            self._save_admin_credentials(admin_user, admin_password)

            logger.info("\n" + "=" * 60)
            logger.info("Admin User Setup Complete")
            logger.info("=" * 60)
            logger.info(f"\nCredentials saved to: {self.ADMIN_CREDS_FILE}")
            logger.info("This file is NOT in app config - keep it secure!")
            logger.info("\nTo use admin user for recovery:")
            logger.info(
                f"  redis-cli -h {redis_ip} -p 6379 --user {admin_user} --pass <password>"
            )
            logger.info(
                f"  redis-cli -h {redis_ip} -p 6380 --tls --user {admin_user} --pass <password>"
            )

            return True

        except Exception as e:
            logger.error(f"Admin user setup failed: {e}")
            return False

    def _get_redis_password(self) -> Optional[str]:
        """Get Redis password from environment or config."""
        # Try environment variable first
        password = os.environ.get("AUTOBOT_REDIS_PASSWORD")
        if password:
            return password
        # Try .env file
        if self.env_file.exists():
            with open(self.env_file, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("AUTOBOT_REDIS_PASSWORD="):
                        return line.split("=", 1)[1].strip()
        return None

    def check_certificates(self) -> bool:
        """Verify all certificates exist and are valid."""
        logger.info("Checking certificate status...")
        statuses = self.generator.get_all_statuses()

        all_valid = True
        for name, status in statuses.items():
            if not status.exists:
                logger.error(f"Certificate missing: {name}")
                all_valid = False
            elif not status.valid:
                logger.error(f"Certificate invalid: {name}")
                all_valid = False
            elif status.needs_renewal:
                logger.warning(
                    f"Certificate needs renewal: {name} "
                    f"(expires in {status.days_until_expiry} days)"
                )
            else:
                logger.info(f"Certificate OK: {name}")

        return all_valid

    async def distribute_certificates(self, vm_name: str = None) -> bool:
        """Distribute certificates to VMs."""
        if vm_name:
            logger.info(f"Distributing certificates to {vm_name}...")
            exclude = [v for v in VM_DEFINITIONS.keys() if v != vm_name]
            results = await self.distributor.distribute_all(exclude_vms=exclude)
        else:
            logger.info("Distributing certificates to all VMs...")
            results = await self.distributor.distribute_all()

        success = all(r.success for r in results.values())
        for vm, result in results.items():
            if result.success:
                logger.info(f"  {vm}: OK - {result.message}")
            else:
                logger.error(f"  {vm}: FAILED - {result.message}")

        return success

    async def phase_redis_dual_auth(self) -> bool:
        """
        Phase 2: Enable Redis TLS with dual-auth.

        Redis will listen on both:
        - Port 6379 (plain) - existing connections continue to work
        - Port 6380 (TLS) - new secure connections

        Steps:
        1. Verify certificates
        2. Distribute certs to Redis VM
        3. Configure Redis TLS
        4. Restart Redis
        5. Test both ports
        """
        logger.info("=" * 60)
        logger.info("Phase 2: Redis Dual-Auth Migration")
        logger.info("=" * 60)

        # Step 1: Verify certificates
        if not self.check_certificates():
            logger.error("Certificate check failed. Run certificate generation first.")
            return False

        # Step 2: Distribute to Redis VM
        logger.info("\nDistributing certificates to Redis VM...")
        if not await self.distribute_certificates("redis"):
            logger.error("Certificate distribution failed")
            return False

        # Step 3: Configure Redis TLS
        logger.info("\nConfiguring Redis TLS...")
        result = await self.configurator.configure_redis_tls()
        if not result.success:
            logger.error(f"Redis configuration failed: {result.message}")
            return False
        logger.info(f"Redis configuration: {result.message}")

        # Step 4: Restart Redis if needed
        if result.restart_required:
            logger.info("\nRestarting Redis service...")
            if not await self.configurator.restart_service(
                "redis", "redis-stack-server"
            ):
                logger.error("Redis restart failed")
                return False
            logger.info("Redis restarted successfully")

            # Wait for Redis to come up
            logger.info("Waiting for Redis to become available...")
            await asyncio.sleep(3)

        # Step 5: Test connections
        logger.info("\nTesting Redis connections...")
        await self._test_redis_dual_auth()

        # Step 6: Update .env file guidance
        logger.info("\n" + "=" * 60)
        logger.info("Phase 2 Complete - Redis Dual-Auth Enabled")
        logger.info("=" * 60)
        logger.info("\nNext steps to enable TLS on client side:")
        logger.info("1. Add to .env file:")
        logger.info("   AUTOBOT_REDIS_TLS_ENABLED=true")
        logger.info("   AUTOBOT_REDIS_TLS_PORT=6380")
        logger.info("2. Restart the backend service")
        logger.info("3. Verify connections work via TLS")
        logger.info("\nPlain connections (port 6379) remain available as fallback.")

        return True

    async def _test_redis_dual_auth(self):
        """Test both plain and TLS Redis connections."""
        import redis

        redis_ip = VM_DEFINITIONS.get("redis", "172.16.168.23")

        # Test plain connection
        try:
            r = redis.Redis(host=redis_ip, port=6379, socket_timeout=5)
            r.ping()
            logger.info(f"  Plain connection (6379): OK")
            r.close()
        except Exception as e:
            logger.error(f"  Plain connection (6379): FAILED - {e}")

        # Test TLS connection (Issue #725: Use explicit SSL params for redis-py)
        try:
            cert_dir = self.config.cert_dir_path / "main-host"
            r = redis.Redis(
                host=redis_ip,
                port=6380,
                password=self._get_redis_password(),
                ssl=True,
                ssl_ca_certs=str(self.config.ca_cert_path),
                ssl_certfile=str(cert_dir / "server-cert.pem"),
                ssl_keyfile=str(cert_dir / "server-key.pem"),
                ssl_check_hostname=False,
                socket_timeout=5,
            )
            r.ping()
            logger.info("  TLS connection (6380): OK")
            r.close()
        except Exception as e:
            logger.error(f"  TLS connection (6380): FAILED - {e}")

    async def phase_backend_tls(self) -> bool:
        """
        Phase 3: Enable Backend TLS (HTTPS on port 8443).

        Steps:
        1. Verify main-host certificates
        2. Update backend startup configuration
        3. Test HTTPS endpoint
        """
        logger.info("=" * 60)
        logger.info("Phase 3: Backend TLS Migration")
        logger.info("=" * 60)

        # Show configuration
        config_snippet = self.configurator.generate_backend_tls_config()
        logger.info("\nBackend TLS configuration snippet:")
        logger.info(config_snippet)

        logger.info("\nNext steps:")
        logger.info("1. Add to .env file:")
        logger.info("   AUTOBOT_BACKEND_TLS_ENABLED=true")
        logger.info("2. Update backend/main.py to use TLS")
        logger.info("3. Update frontend to connect via HTTPS")

        return True

    async def phase_verify(self) -> bool:
        """Verify all mTLS configurations comprehensively."""
        logger.info("=" * 60)
        logger.info("Phase 5: Comprehensive mTLS Verification")
        logger.info("=" * 60)

        all_passed = True

        # Step 1: Check certificates
        logger.info("\n[1/5] Checking certificate status...")
        if not self.check_certificates():
            all_passed = False

        # Step 2: Verify distribution
        logger.info("\n[2/5] Verifying certificate distribution...")
        results = await self.distributor.verify_distribution()
        for vm, verified in results.items():
            status = "OK" if verified else "FAILED"
            logger.info(f"  {vm}: {status}")
            if not verified:
                all_passed = False

        # Step 3: Test Redis TLS connection
        logger.info("\n[3/5] Testing Redis TLS connections...")
        await self._test_redis_dual_auth()

        # Step 4: Check active connections on plain port
        logger.info("\n[4/5] Checking for active plain port connections...")
        plain_conns = await self._check_plain_port_connections()
        if plain_conns > 0:
            logger.warning(f"  {plain_conns} active connections on port 6379")
            logger.warning(
                "  Cannot proceed to disable password auth until 0 connections"
            )
        else:
            logger.info("  No connections on plain port 6379 - ready for cutover")

        # Step 5: Summary
        logger.info("\n[5/5] Verification Summary")
        logger.info("=" * 60)
        if all_passed and plain_conns == 0:
            logger.info("All checks PASSED - Ready for Phase 6 (disable password auth)")
            logger.info("\nTo complete mTLS migration, run:")
            logger.info(
                "  python scripts/security/mtls-migrate.py --phase disable-password"
            )
        elif all_passed:
            logger.info("Certificate checks PASSED")
            logger.info(f"WARNING: {plain_conns} connections still on plain port")
            logger.info("Ensure AUTOBOT_REDIS_TLS_ENABLED=true is set and restart app")
            logger.info("Then re-run verification with the app running")
        else:
            logger.error("Some checks FAILED - review errors above")

        return all_passed

    async def _check_plain_port_connections(self) -> int:
        """Check number of active connections on plain Redis port 6379."""
        import asyncssh

        redis_ip = VM_DEFINITIONS.get("redis", "172.16.168.23")

        try:
            async with asyncssh.connect(
                redis_ip,
                username=self.config.ssh_user,
                client_keys=[str(self.config.ssh_key_path)],
                known_hosts=None,
                connect_timeout=10,
            ) as conn:
                # Count connections on plain port using ss
                result = await conn.run(
                    "ss -tn state established '( sport = :6379 )' | wc -l"
                )
                # Subtract 1 for header line
                count = max(0, int(result.stdout.strip()) - 1)
                return count
        except Exception as e:
            logger.error(f"Failed to check plain port connections: {e}")
            return -1

    async def _run_disable_password_safety_checks(self) -> bool:
        """Run safety checks before disabling password auth.

        Helper for phase_disable_password (Issue #825).
        """
        logger.info("\n[1/4] Running safety checks...")

        plain_conns = await self._check_plain_port_connections()
        if plain_conns > 0:
            logger.error(f"ABORT: {plain_conns} active connections on port 6379")
            logger.error("All clients must use TLS before disabling password auth")
            return False
        logger.info("  No plain port connections - OK")

        logger.info("\n[2/4] Confirming TLS connectivity...")
        try:
            await self._test_tls_with_password()
            logger.info("  TLS connection test passed")
        except Exception as e:
            logger.error(f"ABORT: TLS connection failed: {e}")
            return False

        return True

    def _get_disable_password_confirmation(self, force: bool) -> bool:
        """Get user confirmation before disabling password auth.

        Helper for phase_disable_password (Issue #825).
        """
        logger.info("\n[3/4] CONFIRMATION")
        logger.info("=" * 60)
        logger.info("This will:")
        logger.info("  1. Disable plain port 6379")
        logger.info("  2. Enforce client certificate verification")
        logger.info("  3. Remove password requirement for default user")
        logger.info("  (Admin user 'autobot_admin' will still work with password)")
        logger.info("")

        if force:
            logger.info("--force flag set, proceeding without confirmation")
            return True
        else:
            logger.info("Type 'CONFIRM' to proceed (or anything else to abort):")
            confirmation = input().strip()
            if confirmation != "CONFIRM":
                logger.info("Aborted by user")
                return False
            return True

    async def _execute_disable_password_cutover(self) -> bool:
        """Execute the final cutover to disable password auth.

        Helper for phase_disable_password (Issue #825).
        """
        logger.info("\n[4/4] Executing final cutover...")
        import asyncssh

        redis_ip = VM_DEFINITIONS.get("redis", "172.16.168.23")

        try:
            async with asyncssh.connect(
                redis_ip,
                username=self.config.ssh_user,
                client_keys=[str(self.config.ssh_key_path)],
                known_hosts=None,
                connect_timeout=10,
            ) as conn:
                config_path = "/etc/redis-stack/redis-stack.conf"

                await conn.run(
                    f"sudo cp {config_path} {config_path}.pre-mtls-final",
                    check=True,
                )
                logger.info("  Config backed up")

                await conn.run(
                    f"sudo sed -i 's/^port 6379$/port 0/' {config_path}",
                    check=True,
                )
                await conn.run(
                    f"sudo sed -i 's/^tls-auth-clients optional$/tls-auth-clients yes/' "
                    f"{config_path}",
                    check=True,
                )
                await conn.run(
                    f"sudo sed -i '/^requirepass/d' {config_path}",
                    check=True,
                )
                logger.info("  Config updated")

                await conn.run("sudo systemctl restart redis-stack-server", check=True)
                logger.info("  Redis restarted")

                await asyncio.sleep(2)
                await self._test_tls_only()
                logger.info("  TLS-only verification passed")

                logger.info("\n" + "=" * 60)
                logger.info("mTLS MIGRATION COMPLETE")
                logger.info("=" * 60)
                logger.info("Redis now requires mTLS on port 6380")
                logger.info("Plain port 6379 is disabled")
                logger.info("Password auth removed for default user")
                logger.info("")
                logger.info(
                    "RECOVERY: Admin user 'autobot_admin' still works with password:"
                )
                logger.info(
                    f"  redis-cli -h {redis_ip} -p 6380 --tls --user autobot_admin --pass <password>"
                )
                logger.info("  Credentials: certs/.redis-admin-credentials")
                logger.info("")
                logger.info(
                    "To rollback: python scripts/security/mtls-migrate.py --rollback redis-full"
                )

                return True

        except Exception as e:
            logger.error(f"Cutover failed: {e}")
            logger.error("Attempting automatic rollback...")
            await self.rollback_redis_full()
            return False

    async def phase_disable_password(self, force: bool = False) -> bool:
        """
        Phase 6: Disable password authentication (FINAL CUTOVER).

        DANGER: This is irreversible without rollback script.
        Only run after verification confirms 0 connections on port 6379.
        """
        logger.info("=" * 60)
        logger.info("Phase 6: Disable Password Authentication (FINAL)")
        logger.info("=" * 60)

        if not await self._run_disable_password_safety_checks():
            return False

        if not self._get_disable_password_confirmation(force):
            return False

        return await self._execute_disable_password_cutover()

    async def _test_tls_with_password(self):
        """Test TLS connection with current password (pre-cutover check)."""
        import redis

        redis_ip = VM_DEFINITIONS.get("redis", "172.16.168.23")
        cert_dir = self.config.cert_dir_path / "main-host"
        password = self._get_redis_password()

        r = redis.Redis(
            host=redis_ip,
            port=6380,
            password=password,
            ssl=True,
            ssl_ca_certs=str(self.config.ca_cert_path),
            ssl_certfile=str(cert_dir / "server-cert.pem"),
            ssl_keyfile=str(cert_dir / "server-key.pem"),
            ssl_check_hostname=False,
            socket_timeout=5,
        )
        r.ping()
        r.close()

    async def _test_tls_only(self):
        """Test TLS connection without password (post-cutover check)."""
        import redis

        redis_ip = VM_DEFINITIONS.get("redis", "172.16.168.23")
        cert_dir = self.config.cert_dir_path / "main-host"

        # Use explicit SSL params for redis-py (Issue #725)
        r = redis.Redis(
            host=redis_ip,
            port=6380,
            ssl=True,
            ssl_ca_certs=str(self.config.ca_cert_path),
            ssl_certfile=str(cert_dir / "server-cert.pem"),
            ssl_keyfile=str(cert_dir / "server-key.pem"),
            ssl_check_hostname=False,
            socket_timeout=5,
        )
        r.ping()
        r.close()

    async def rollback_redis_full(self) -> bool:
        """Full rollback to pre-mTLS state (restores password auth)."""
        logger.info("=" * 60)
        logger.info("Full Rollback: Restoring pre-mTLS configuration")
        logger.info("=" * 60)

        import asyncssh

        redis_ip = VM_DEFINITIONS.get("redis", "172.16.168.23")

        try:
            async with asyncssh.connect(
                redis_ip,
                username=self.config.ssh_user,
                client_keys=[str(self.config.ssh_key_path)],
                known_hosts=None,
                connect_timeout=10,
            ) as conn:
                # Check if backup exists
                check = await conn.run(
                    "test -f /etc/redis-stack.conf.pre-mtls-final && echo 'exists'"
                )
                if "exists" in check.stdout:
                    await conn.run(
                        "sudo cp /etc/redis-stack.conf.pre-mtls-final /etc/redis-stack.conf",
                        check=True,
                    )
                    logger.info("Restored from pre-mTLS-final backup")
                else:
                    # Fallback: re-enable plain port
                    await conn.run(
                        "sudo sed -i 's/^port 0$/port 6379/' /etc/redis-stack.conf"
                    )
                    await conn.run(
                        "sudo sed -i 's/^tls-auth-clients yes$/tls-auth-clients optional/' "
                        "/etc/redis-stack.conf"
                    )
                    logger.info("Re-enabled plain port 6379")

                await conn.run("sudo systemctl restart redis-stack-server", check=True)
                logger.info("Redis restarted")
                return True

        except Exception as e:
            logger.error(f"Full rollback failed: {e}")
            return False

    async def rollback_redis(self) -> bool:
        """Rollback Redis to plain connections only."""
        logger.info("=" * 60)
        logger.info("Rollback: Disabling Redis TLS")
        logger.info("=" * 60)

        import asyncssh

        redis_ip = VM_DEFINITIONS.get("redis", "172.16.168.23")

        try:
            async with asyncssh.connect(
                redis_ip,
                username=self.config.ssh_user,
                client_keys=[str(self.config.ssh_key_path)],
                known_hosts=None,
                connect_timeout=10,
            ) as conn:
                # Remove TLS config lines
                await conn.run(
                    "sudo sed -i '/# TLS Configuration/,/tls-auth-clients/d' "
                    "/etc/redis-stack.conf",
                    check=True,
                )
                logger.info("TLS configuration removed from Redis")

                # Restart Redis
                await conn.run("sudo systemctl restart redis-stack-server", check=True)
                logger.info("Redis restarted")

                return True

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False


def _create_mtls_argument_parser() -> argparse.ArgumentParser:
    """Create argument parser for mTLS migration.

    Helper for main (Issue #825).
    """
    parser = argparse.ArgumentParser(
        description="mTLS Migration Tool for AutoBot (Issue #725)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Migration Phases:
  redis-dual-auth   Phase 2: Enable Redis TLS while keeping password auth
  backend-tls       Phase 3: Configure backend for HTTPS
  verify            Phase 5: Comprehensive verification of mTLS setup
  disable-password  Phase 6: FINAL - Disable password auth (requires confirmation)
  all               Run phases 2-5 sequentially

Rollback Options:
  redis             Remove TLS config, keep dual-auth
  redis-full        Full rollback to pre-mTLS state

On-Demand App Workflow:
  1. Run: --phase redis-dual-auth (configure Redis TLS)
  2. Set AUTOBOT_REDIS_TLS_ENABLED=true in .env
  3. Start app and test functionality
  4. Run: --phase verify (with app running)
  5. If all tests pass, run: --phase disable-password

Examples:
  python scripts/security/mtls-migrate.py --phase redis-dual-auth
  python scripts/security/mtls-migrate.py --phase verify
  python scripts/security/mtls-migrate.py --rollback redis
""",
    )
    parser.add_argument(
        "--phase",
        choices=["redis-dual-auth", "backend-tls", "verify", "disable-password", "all"],
        help="Migration phase to execute",
    )
    parser.add_argument(
        "--rollback",
        choices=["redis", "redis-full"],
        help="Rollback a specific phase",
    )
    parser.add_argument(
        "--check-certs",
        action="store_true",
        help="Check certificate status only",
    )
    parser.add_argument(
        "--setup-admin",
        action="store_true",
        help="Create Redis admin user (run BEFORE disable-password)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt (use with caution)",
    )
    return parser


async def _handle_phase_execution(migration: "MTLSMigration", phase: str, force: bool = False) -> bool:
    """Execute the specified migration phase.

    Helper for main (Issue #825).
    """
    if phase == "redis-dual-auth":
        return await migration.phase_redis_dual_auth()
    elif phase == "backend-tls":
        return await migration.phase_backend_tls()
    elif phase == "verify":
        return await migration.phase_verify()
    elif phase == "disable-password":
        return await migration.phase_disable_password(force=force)
    elif phase == "all":
        success = await migration.phase_redis_dual_auth()
        if success:
            success = await migration.phase_backend_tls()
        if success:
            success = await migration.phase_verify()
        return success
    return False


async def main():
    parser = _create_mtls_argument_parser()
    args = parser.parse_args()

    migration = MTLSMigration()

    if args.check_certs:
        success = migration.check_certificates()
        sys.exit(0 if success else 1)

    if args.setup_admin:
        success = await migration.setup_admin_user()
        sys.exit(0 if success else 1)

    if args.rollback:
        if args.rollback == "redis":
            success = await migration.rollback_redis()
        elif args.rollback == "redis-full":
            success = await migration.rollback_redis_full()
        sys.exit(0 if success else 1)

    if args.phase:
        success = await _handle_phase_execution(migration, args.phase, args.force)
        sys.exit(0 if success else 1)

    parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
