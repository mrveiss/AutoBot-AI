# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Certificate Distributor Module
==============================

Distributes TLS certificates to AutoBot VMs via SSH.
Handles secure file transfer and permission management.

Inspired by oVirt's certificate distribution during host deployment.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import asyncssh

from src.pki.config import TLSConfig, VM_DEFINITIONS, VMCertificateInfo

logger = logging.getLogger(__name__)


@dataclass
class DistributionResult:
    """Result of certificate distribution to a VM."""

    vm_name: str
    success: bool
    message: str
    files_copied: List[str] = None

    def __post_init__(self):
        if self.files_copied is None:
            self.files_copied = []


class CertificateDistributor:
    """
    Distributes certificates to VMs via SSH.

    Features:
    - Async SSH operations for parallel distribution
    - Automatic directory creation on remote hosts
    - Proper permission setting (600 for keys, 644 for certs)
    - Certificate verification after distribution
    """

    def __init__(self, config: Optional[TLSConfig] = None):
        """Initialize distributor with configuration."""
        self.config = config or TLSConfig()

    async def distribute_all(
        self,
        exclude_vms: Optional[List[str]] = None,
    ) -> Dict[str, DistributionResult]:
        """
        Distribute certificates to all VMs.

        Args:
            exclude_vms: List of VM names to skip

        Returns:
            Dict mapping VM name to distribution result
        """
        exclude_vms = exclude_vms or []
        results = {}

        # Skip main-host (local machine)
        vms_to_process = {
            name: ip
            for name, ip in VM_DEFINITIONS.items()
            if name not in exclude_vms and name != "main-host"
        }

        logger.info(f"Distributing certificates to {len(vms_to_process)} VMs")

        # Distribute in parallel
        tasks = []
        for vm_name, vm_ip in vms_to_process.items():
            vm_info = self.config.get_vm_cert_info(vm_name, vm_ip)
            tasks.append(self._distribute_to_vm(vm_info))

        distribution_results = await asyncio.gather(*tasks, return_exceptions=True)

        for (vm_name, _), result in zip(vms_to_process.items(), distribution_results):
            if isinstance(result, Exception):
                results[vm_name] = DistributionResult(
                    vm_name=vm_name,
                    success=False,
                    message=str(result),
                )
            else:
                results[vm_name] = result

        # Log summary
        success_count = sum(1 for r in results.values() if r.success)
        logger.info(
            f"Certificate distribution complete: {success_count}/{len(results)} successful"
        )

        return results

    async def _distribute_to_vm(
        self, vm_info: VMCertificateInfo
    ) -> DistributionResult:
        """Distribute certificates to a single VM."""
        logger.info(f"Distributing certificates to {vm_info.name} ({vm_info.ip})")

        files_copied = []

        try:
            # Connect via SSH
            async with asyncssh.connect(
                vm_info.ip,
                username=self.config.ssh_user,
                client_keys=[str(self.config.ssh_key_path)],
                known_hosts=None,  # TODO: Use proper known_hosts in production
                connect_timeout=10,
            ) as conn:

                # Create remote directory
                remote_dir = self.config.remote_cert_dir
                await conn.run(f"sudo mkdir -p {remote_dir}", check=True)
                await conn.run(
                    f"sudo chown {self.config.ssh_user}:{self.config.ssh_user} {remote_dir}",
                    check=True,
                )

                # Copy CA certificate
                ca_remote = f"{remote_dir}/ca-cert.pem"
                await self._copy_file(
                    conn,
                    self.config.ca_cert_path,
                    ca_remote,
                    mode="644",
                )
                files_copied.append(ca_remote)

                # Copy service certificate
                cert_remote = f"{remote_dir}/server-cert.pem"
                await self._copy_file(
                    conn,
                    vm_info.cert_path,
                    cert_remote,
                    mode="644",
                )
                files_copied.append(cert_remote)

                # Copy service key
                key_remote = f"{remote_dir}/server-key.pem"
                await self._copy_file(
                    conn,
                    vm_info.key_path,
                    key_remote,
                    mode="600",
                )
                files_copied.append(key_remote)

                # Set final ownership to root
                await conn.run(
                    f"sudo chown root:root {remote_dir}/*.pem",
                    check=True,
                )

                # Verify certificate on remote
                verify_result = await conn.run(
                    f"openssl verify -CAfile {ca_remote} {cert_remote}",
                )
                if verify_result.returncode != 0:
                    raise RuntimeError(
                        f"Certificate verification failed: {verify_result.stderr}"
                    )

                logger.info(f"Successfully distributed certificates to {vm_info.name}")
                return DistributionResult(
                    vm_name=vm_info.name,
                    success=True,
                    message="Certificates distributed and verified",
                    files_copied=files_copied,
                )

        except asyncssh.Error as e:
            logger.error(f"SSH error distributing to {vm_info.name}: {e}")
            return DistributionResult(
                vm_name=vm_info.name,
                success=False,
                message=f"SSH error: {e}",
            )
        except Exception as e:
            logger.error(f"Error distributing to {vm_info.name}: {e}")
            return DistributionResult(
                vm_name=vm_info.name,
                success=False,
                message=str(e),
            )

    async def _copy_file(
        self,
        conn: asyncssh.SSHClientConnection,
        local_path: Path,
        remote_path: str,
        mode: str = "644",
    ):
        """Copy a file to remote host and set permissions."""
        # Read local file
        content = local_path.read_bytes()

        # Write to temporary location
        temp_path = f"/tmp/{local_path.name}"
        async with conn.start_sftp_client() as sftp:
            async with sftp.open(temp_path, "wb") as f:
                await f.write(content)

        # Move to final location with sudo and set permissions
        await conn.run(f"sudo mv {temp_path} {remote_path}", check=True)
        await conn.run(f"sudo chmod {mode} {remote_path}", check=True)

    async def verify_distribution(self) -> Dict[str, bool]:
        """Verify certificates are properly distributed to all VMs."""
        results = {}

        for vm_name, vm_ip in VM_DEFINITIONS.items():
            if vm_name == "main-host":
                continue

            try:
                async with asyncssh.connect(
                    vm_ip,
                    username=self.config.ssh_user,
                    client_keys=[str(self.config.ssh_key_path)],
                    known_hosts=None,
                    connect_timeout=10,
                ) as conn:

                    remote_dir = self.config.remote_cert_dir

                    # Check all required files exist
                    check_result = await conn.run(
                        f"test -f {remote_dir}/ca-cert.pem && "
                        f"test -f {remote_dir}/server-cert.pem && "
                        f"test -f {remote_dir}/server-key.pem"
                    )

                    if check_result.returncode != 0:
                        results[vm_name] = False
                        continue

                    # Verify certificate chain
                    verify_result = await conn.run(
                        f"openssl verify -CAfile {remote_dir}/ca-cert.pem "
                        f"{remote_dir}/server-cert.pem"
                    )

                    results[vm_name] = verify_result.returncode == 0

            except Exception as e:
                logger.error(f"Failed to verify {vm_name}: {e}")
                results[vm_name] = False

        return results
