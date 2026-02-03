# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service Configurator Module
===========================

Configures AutoBot services to use TLS certificates.
Updates service configurations on VMs and local services.

Services configured:
- Redis Stack (TLS connections)
- Backend FastAPI (HTTPS)
- Inter-service communication
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

import asyncssh

from src.pki.config import VM_DEFINITIONS, TLSConfig

logger = logging.getLogger(__name__)


def _build_redis_tls_config(
    remote_cert_dir: str,
    auth_clients: str = "optional",
    disable_plain_port: bool = False,
) -> str:
    """
    Build Redis TLS configuration snippet.

    Issue #665: Extracted from configure_redis_tls to reduce function length.
    Issue #725: Added auth_clients and disable_plain_port parameters for mTLS migration.

    Args:
        remote_cert_dir: Remote directory path for certificates
        auth_clients: Client authentication mode:
            - "optional": Clients may use certificates (dual-auth mode for migration)
            - "yes": Clients MUST use certificates (full mTLS enforcement)
            - "no": Client certificates not required
        disable_plain_port: If True, sets port 0 to disable non-TLS connections

    Returns:
        Redis TLS configuration string
    """
    plain_port = "0" if disable_plain_port else "6379"
    return f"""
# TLS Configuration (AutoBot PKI)
tls-port 6380
port {plain_port}
tls-cert-file {remote_cert_dir}/server-cert.pem
tls-key-file {remote_cert_dir}/server-key.pem
tls-ca-cert-file {remote_cert_dir}/ca-cert.pem
tls-auth-clients {auth_clients}
"""


async def _write_tls_config_to_redis(conn, tls_config: str) -> None:
    """
    Write TLS configuration to Redis config file via SFTP.

    Issue #665: Extracted from configure_redis_tls to reduce function length.

    Args:
        conn: AsyncSSH connection
        tls_config: TLS configuration content to write
    """
    temp_config = "/tmp/redis-tls.conf"  # nosec B108 - Temp file for Redis TLS config
    async with conn.start_sftp_client() as sftp:
        async with sftp.open(temp_config, "w") as f:
            await f.write(tls_config)

    # Append to main config (Issue #725: Use correct Redis Stack config path)
    await conn.run(
        f"sudo cat {temp_config} | sudo tee -a /etc/redis-stack/redis-stack.conf > /dev/null",
        check=True,
    )
    await conn.run(f"rm {temp_config}")


@dataclass
class ConfigurationResult:
    """Result of service configuration."""

    service_name: str
    vm_name: str
    success: bool
    message: str
    restart_required: bool = False


class ServiceConfigurator:
    """
    Configures services to use TLS certificates.

    Handles:
    - Redis TLS configuration
    - Service restart coordination
    - Configuration file updates
    """

    def __init__(self, config: Optional[TLSConfig] = None):
        """Initialize configurator."""
        self.config = config or TLSConfig()

    async def configure_all(self) -> Dict[str, ConfigurationResult]:
        """Configure all services for TLS."""
        results = {}

        # Configure Redis TLS
        redis_result = await self.configure_redis_tls()
        results["redis"] = redis_result

        return results

    async def configure_redis_tls(
        self,
        auth_clients: str = "optional",
        disable_plain_port: bool = False,
    ) -> ConfigurationResult:
        """
        Configure Redis Stack for TLS connections.

        Issue #665: Refactored to use extracted helpers for config building
        and SFTP operations.
        Issue #725: Added auth_clients and disable_plain_port parameters.
        Issue #694: Use SSOT config for Redis IP.

        Args:
            auth_clients: Client authentication mode ("optional", "yes", "no")
            disable_plain_port: If True, disables non-TLS port (port 0)
        """
        from src.config.ssot_config import config

        vm_ip = VM_DEFINITIONS.get("redis", config.vm.redis)

        logger.info("Configuring Redis Stack for TLS")

        try:
            async with asyncssh.connect(
                vm_ip,
                username=self.config.ssh_user,
                client_keys=[str(self.config.ssh_key_path)],
                known_hosts=None,
                connect_timeout=10,
            ) as conn:
                # Check if Redis Stack is running
                status_result = await conn.run(
                    "systemctl is-active redis-stack-server",
                )
                if status_result.returncode != 0:
                    return ConfigurationResult(
                        service_name="redis-stack-server",
                        vm_name="redis",
                        success=False,
                        message="Redis Stack is not running",
                    )

                # Check if TLS config already exists (Issue #725: Use correct config path)
                check_result = await conn.run(
                    "grep -q 'tls-port' /etc/redis-stack/redis-stack.conf 2>/dev/null || echo 'not_found'"
                )

                if "not_found" in check_result.stdout:
                    # Issue #665: Uses extracted helpers
                    # Issue #725: Pass auth_clients and disable_plain_port
                    tls_config = _build_redis_tls_config(
                        self.config.remote_cert_dir,
                        auth_clients=auth_clients,
                        disable_plain_port=disable_plain_port,
                    )
                    await _write_tls_config_to_redis(conn, tls_config)

                    logger.info("Redis TLS configuration added")
                    return ConfigurationResult(
                        service_name="redis-stack-server",
                        vm_name="redis",
                        success=True,
                        message="TLS configuration added. Redis restart required.",
                        restart_required=True,
                    )

                logger.info("Redis TLS already configured")
                return ConfigurationResult(
                    service_name="redis-stack-server",
                    vm_name="redis",
                    success=True,
                    message="TLS already configured",
                    restart_required=False,
                )

        except asyncssh.Error as e:
            logger.error("SSH error configuring Redis: %s", e)
            return ConfigurationResult(
                service_name="redis-stack-server",
                vm_name="redis",
                success=False,
                message=f"SSH error: {e}",
            )
        except Exception as e:
            logger.error("Error configuring Redis: %s", e)
            return ConfigurationResult(
                service_name="redis-stack-server",
                vm_name="redis",
                success=False,
                message=str(e),
            )

    async def restart_service(self, vm_name: str, service_name: str) -> bool:
        """Restart a service on a VM."""
        vm_ip = VM_DEFINITIONS.get(vm_name)
        if not vm_ip:
            logger.error(f"Unknown VM: {vm_name}")
            return False

        try:
            async with asyncssh.connect(
                vm_ip,
                username=self.config.ssh_user,
                client_keys=[str(self.config.ssh_key_path)],
                known_hosts=None,
                connect_timeout=10,
            ) as conn:
                result = await conn.run(
                    f"sudo systemctl restart {service_name}",
                )

                if result.returncode == 0:
                    logger.info(f"Restarted {service_name} on {vm_name}")
                    return True
                else:
                    logger.error(f"Failed to restart {service_name}: {result.stderr}")
                    return False

        except Exception as e:
            logger.error(f"Error restarting {service_name} on {vm_name}: {e}")
            return False

    def generate_backend_tls_config(self) -> str:
        """Generate TLS configuration snippet for FastAPI backend."""
        cert_dir = self.config.cert_dir_path / "main-host"

        return f"""
# TLS Configuration for FastAPI (uvicorn)
# Add these to your uvicorn.run() call:
#
# import ssl
# ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
# ssl_context.load_cert_chain(
#     certfile="{cert_dir}/server-cert.pem",
#     keyfile="{cert_dir}/server-key.pem",
# )
#
# uvicorn.run(
#     app,
#     host="0.0.0.0",
#     port=8001,
#     ssl_keyfile="{cert_dir}/server-key.pem",
#     ssl_certfile="{cert_dir}/server-cert.pem",
# )
"""

    def get_redis_tls_url(self) -> str:
        """Get Redis URL with TLS. Issue #694: Use SSOT config."""
        from src.config.ssot_config import config

        redis_ip = VM_DEFINITIONS.get("redis", config.vm.redis)
        return f"rediss://{redis_ip}:6380"

    def get_tls_context_params(self) -> dict:
        """Get parameters for creating SSL context."""
        cert_dir = self.config.cert_dir_path / "main-host"
        return {
            "ca_certs": str(self.config.ca_cert_path),
            "certfile": str(cert_dir / "server-cert.pem"),
            "keyfile": str(cert_dir / "server-key.pem"),
        }

    async def enable_dual_auth(self) -> ConfigurationResult:
        """
        Enable TLS with optional client authentication (migration phase).

        Issue #725: This is phase 1 of mTLS migration - allows both
        password and certificate authentication.
        """
        logger.info("Enabling Redis TLS with dual authentication (optional)")
        return await self.configure_redis_tls(
            auth_clients="optional",
            disable_plain_port=False,
        )

    async def enforce_mtls(self) -> ConfigurationResult:
        """
        Enforce full mTLS - require client certificates and disable plain port.

        Issue #725: This is the final phase of mTLS migration - enforces
        certificate-based authentication and disables non-TLS connections.

        WARNING: Ensure all clients have valid certificates before calling this.
        """
        logger.info(
            "Enforcing mTLS: requiring client certificates, disabling plain port"
        )
        return await self.configure_redis_tls(
            auth_clients="yes",
            disable_plain_port=True,
        )
