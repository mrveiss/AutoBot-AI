# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSH Key Provisioning Service

Provisions SSH keys on remote hosts using password authentication,
enabling passwordless SSH access for future operations.
"""

import logging
from io import StringIO
from typing import Tuple

import paramiko
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger(__name__)


class SSHKeyProvisioner:
    """
    Provisions SSH keys on remote hosts for passwordless authentication.

    Security features:
    - Generates 4096-bit RSA keys
    - Uses secure key permissions (0o600)
    - Verifies key authentication before completion
    - Timeout protection for all SSH operations
    """

    def __init__(self, connection_timeout: int = 30):
        """
        Initialize SSH key provisioner

        Args:
            connection_timeout: SSH connection timeout in seconds (default: 30)
        """
        self.connection_timeout = connection_timeout
        logger.info("SSH Key Provisioner initialized")

    def provision_key(
        self, host_ip: str, port: int, username: str, password: str
    ) -> Tuple[str, str]:
        """
        Provision SSH key on remote host

        Steps:
        1. Generate 4096-bit RSA key pair
        2. Connect to host using password authentication
        3. Create .ssh directory if needed
        4. Add public key to authorized_keys
        5. Verify key authentication works
        6. Return private key content and public key content

        Args:
            host_ip: IP address of remote host
            port: SSH port (default: 22)
            username: SSH username
            password: Password for initial authentication

        Returns:
            Tuple of (private_key_content, public_key_content)

        Raises:
            paramiko.AuthenticationException: If password authentication fails
            paramiko.SSHException: If SSH connection fails
            Exception: If key provisioning fails
        """
        logger.info(f"Starting SSH key provisioning for {username}@{host_ip}:{port}")

        # Generate 4096-bit RSA key pair
        logger.debug("Generating 4096-bit RSA key pair")
        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=4096, backend=default_backend()
        )

        # Serialize private key (unencrypted - will be encrypted by InfrastructureDB)
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=serialization.NoEncryption(),
        )

        # Serialize public key
        public_key = private_key.public_key()
        public_openssh = public_key.public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        ),
        pub_key_str = public_openssh.decode("utf-8")

        # Add comment to public key
        pub_key_with_comment = f"{pub_key_str} autobot-provisioned-key@{host_ip}"

        ssh = None

        try:
            # Connect with password authentication
            logger.info(f"Connecting to {host_ip}:{port} with password authentication")
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            ssh.connect(
                hostname=host_ip,
                port=port,
                username=username,
                password=password,
                timeout=self.connection_timeout,
                banner_timeout=self.connection_timeout,
            )

            logger.info("Password authentication successful")

            # Create .ssh directory with proper permissions
            logger.debug("Creating .ssh directory on remote host")
            self._exec_command(ssh, "mkdir -p ~/.ssh && chmod 700 ~/.ssh")

            # Add public key to authorized_keys
            logger.debug("Adding public key to authorized_keys")
            self._exec_command(
                ssh, f"echo '{pub_key_with_comment}' >> ~/.ssh/authorized_keys"
            )

            # Set proper permissions on authorized_keys
            self._exec_command(ssh, "chmod 600 ~/.ssh/authorized_keys")

            logger.info("Public key added to remote host")

            # Close password-authenticated connection
            ssh.close()
            ssh = None

            # Convert private key to string for in-memory handling
            private_key_str = private_pem.decode("utf-8")

            # Create paramiko RSAKey from in-memory string (SECURITY: No disk storage)
            logger.debug("Loading private key into paramiko RSAKey (in-memory only)")
            private_key_file = StringIO(private_key_str)
            pkey = paramiko.RSAKey.from_private_key(private_key_file)

            # Verify key authentication works
            logger.info("Verifying key authentication with in-memory key")
            ssh_test = paramiko.SSHClient()
            ssh_test.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            ssh_test.connect(
                hostname=host_ip,
                port=port,
                username=username,
                pkey=pkey,
                timeout=self.connection_timeout,
                banner_timeout=self.connection_timeout,
            )

            # Test command execution
            self._exec_command(ssh_test, "echo 'Key authentication verified'")

            ssh_test.close()

            logger.info(f"SSH key provisioning successful for {username}@{host_ip}")

            # Calculate public key fingerprint for verification
            fingerprint = self._get_key_fingerprint(public_key)
            logger.info(f"Public key fingerprint: {fingerprint}")

            return (private_key_str, pub_key_with_comment)

        except paramiko.AuthenticationException as e:
            logger.error(f"Authentication failed for {username}@{host_ip}: {e}")
            raise Exception(f"Password authentication failed: {str(e)}")

        except paramiko.SSHException as e:
            logger.error(f"SSH connection failed for {host_ip}:{port}: {e}")
            raise Exception(f"SSH connection failed: {str(e)}")

        except Exception as e:
            logger.exception(f"SSH key provisioning failed for {host_ip}: {e}")
            raise

        finally:
            if ssh:
                try:
                    ssh.close()
                except Exception as e:
                    logger.warning(f"Error closing SSH connection: {e}")

    def _exec_command(
        self, ssh: paramiko.SSHClient, command: str, timeout: int = 10
    ) -> str:
        """
        Execute command on remote host with error checking

        Args:
            ssh: Active SSH client connection
            command: Command to execute
            timeout: Command execution timeout in seconds

        Returns:
            Command stdout output

        Raises:
            Exception: If command fails (non-zero exit status)
        """
        stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0:
            error_output = stderr.read().decode("utf-8", errors="ignore")
            raise Exception(
                f"Command failed with exit status {exit_status}: {command}\n"
                f"Error: {error_output}"
            )

        return stdout.read().decode("utf-8", errors="ignore")

    def _get_key_fingerprint(self, public_key) -> str:
        """
        Calculate SSH key fingerprint (SHA256)

        Args:
            public_key: Cryptography public key object

        Returns:
            Fingerprint string in format: SHA256:base64_hash
        """
        public_openssh = public_key.public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )

        # Calculate SHA256 hash
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digest.update(public_openssh)
        fingerprint_bytes = digest.finalize()

        # Encode as base64 (no padding)
        import base64

        fingerprint_b64 = (
            base64.b64encode(fingerprint_bytes).decode("utf-8").rstrip("=")
        )

        return f"SHA256:{fingerprint_b64}"

    def test_key_authentication(
        self, host_ip: str, port: int, username: str, private_key_content: str
    ) -> bool:
        """
        Test if SSH key authentication works

        Args:
            host_ip: IP address of remote host
            port: SSH port
            username: SSH username
            private_key_content: Private key content as string

        Returns:
            True if authentication successful, False otherwise
        """
        try:
            logger.info(f"Testing key authentication for {username}@{host_ip}")

            # Load private key from in-memory string
            private_key_file = StringIO(private_key_content)
            pkey = paramiko.RSAKey.from_private_key(private_key_file)

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            ssh.connect(
                hostname=host_ip,
                port=port,
                username=username,
                pkey=pkey,
                timeout=self.connection_timeout,
                banner_timeout=self.connection_timeout,
            )

            # Execute test command
            self._exec_command(ssh, "echo 'test'")

            ssh.close()

            logger.info(f"Key authentication successful for {username}@{host_ip}")
            return True

        except Exception as e:
            logger.error(f"Key authentication failed for {username}@{host_ip}: {e}")
            return False
