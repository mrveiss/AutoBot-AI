# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSH Connection Service

Manages SSH connections to user-defined infrastructure hosts.
Handles connection establishment, command execution, and session management
for hosts stored in the secrets system.

Related Issue: #715 - Dynamic SSH/VNC host management via secrets

Key Features:
- Secure connection using credentials from secrets storage
- Session pooling for efficient connection reuse
- Command execution with timeout and error handling
- Integration with terminal handlers for interactive sessions
"""

import asyncio
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Optional

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False

from backend.services.infrastructure_host_service import (
    AuthType,
    get_infrastructure_host_service,
)

logger = logging.getLogger(__name__)


@dataclass
class SSHSession:
    """Represents an active SSH session."""

    host_id: str
    client: Any  # paramiko.SSHClient
    channel: Any = None  # paramiko.Channel for interactive sessions
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    is_interactive: bool = False

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now()


class SSHConnectionService:
    """
    Service for managing SSH connections to infrastructure hosts.

    Provides methods for:
    - Establishing SSH connections using stored credentials
    - Executing commands on remote hosts
    - Managing interactive PTY sessions for terminal integration
    - Connection pooling and lifecycle management
    """

    _instance: Optional["SSHConnectionService"] = None

    def __init__(self):
        """Initialize SSH connection service."""
        if not PARAMIKO_AVAILABLE:
            logger.warning("Paramiko not available - SSH connections will be disabled")

        self._sessions: Dict[str, SSHSession] = {}
        self._host_service = get_infrastructure_host_service()
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "SSHConnectionService":
        """Get singleton instance of SSHConnectionService."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _create_ssh_client(self) -> Any:
        """Create a new SSH client with security settings."""
        if not PARAMIKO_AVAILABLE:
            raise RuntimeError("Paramiko is not installed - cannot create SSH client")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client

    def _authenticate_client(
        self,
        client: Any,
        host: str,
        port: int,
        username: str,
        credentials: Dict[str, Any],
        auth_type: AuthType,
        timeout: float = 10.0,
    ) -> None:
        """
        Authenticate SSH client using stored credentials.

        Args:
            client: Paramiko SSH client
            host: Target hostname/IP
            port: SSH port
            username: SSH username
            credentials: Decrypted credentials dict
            auth_type: Authentication method (ssh_key or password)
            timeout: Connection timeout in seconds
        """
        if auth_type == AuthType.SSH_KEY:
            key_data = credentials.get("ssh_key", "")
            passphrase = credentials.get("ssh_key_passphrase")

            # Load private key from string
            key_file = io.StringIO(key_data)
            try:
                # Try RSA first
                private_key = paramiko.RSAKey.from_private_key(key_file, password=passphrase)
            except paramiko.ssh_exception.SSHException:
                # Try Ed25519
                key_file.seek(0)
                try:
                    private_key = paramiko.Ed25519Key.from_private_key(key_file, password=passphrase)
                except paramiko.ssh_exception.SSHException:
                    # Try ECDSA
                    key_file.seek(0)
                    private_key = paramiko.ECDSAKey.from_private_key(key_file, password=passphrase)

            client.connect(
                hostname=host,
                port=port,
                username=username,
                pkey=private_key,
                timeout=timeout,
                allow_agent=False,
                look_for_keys=False,
            )

        else:  # Password authentication
            password = credentials.get("ssh_password", "")
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=timeout,
                allow_agent=False,
                look_for_keys=False,
            )

    async def connect(
        self,
        host_id: str,
        accessed_by: str = "ssh_connection_service",
        timeout: float = 10.0,
    ) -> SSHSession:
        """
        Establish SSH connection to an infrastructure host.

        Args:
            host_id: ID of the infrastructure host
            accessed_by: Identifier for audit logging
            timeout: Connection timeout in seconds

        Returns:
            SSHSession object representing the connection

        Raises:
            ValueError: If host not found or credentials invalid
            ConnectionError: If SSH connection fails
        """
        if not PARAMIKO_AVAILABLE:
            raise RuntimeError("Paramiko is not installed - SSH connections unavailable")

        async with self._lock:
            # Check for existing session
            if host_id in self._sessions:
                session = self._sessions[host_id]
                if self._is_session_valid(session):
                    session.update_activity()
                    return session
                else:
                    await self._close_session(host_id)

        # Get host metadata
        host = self._host_service.get_host(host_id)
        if not host:
            raise ValueError(f"Infrastructure host not found: {host_id}")

        # Get credentials
        credentials = self._host_service.get_host_credentials(host_id, accessed_by)
        if not credentials:
            raise ValueError(f"Could not retrieve credentials for host: {host_id}")

        # Create and authenticate client
        client = self._create_ssh_client()

        try:
            auth_type = AuthType(host.auth_type) if isinstance(host.auth_type, str) else host.auth_type
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._authenticate_client(
                    client, host.host, host.ssh_port, host.username, credentials, auth_type, timeout
                ),
            )

            # Record successful connection
            self._host_service.record_connection(host_id)

            # Create session
            session = SSHSession(host_id=host_id, client=client)

            async with self._lock:
                self._sessions[host_id] = session

            logger.info("SSH connection established to host: %s (%s)", host.name, host.host)
            return session

        except Exception as e:
            client.close()
            logger.error("SSH connection failed to host %s: %s", host_id, e)
            raise ConnectionError(f"SSH connection failed: {e}") from e

    async def execute_command(
        self,
        host_id: str,
        command: str,
        timeout: float = 30.0,
        accessed_by: str = "ssh_connection_service",
    ) -> Dict[str, Any]:
        """
        Execute a command on a remote host.

        Args:
            host_id: ID of the infrastructure host
            command: Command to execute
            timeout: Command timeout in seconds
            accessed_by: Identifier for audit logging

        Returns:
            Dict with stdout, stderr, exit_code, and execution_time
        """
        session = await self.connect(host_id, accessed_by, timeout)

        start_time = datetime.now()
        try:
            stdin, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: session.client.exec_command(command, timeout=timeout),
            )

            # Read output
            stdout_data = await asyncio.get_event_loop().run_in_executor(None, stdout.read)
            stderr_data = await asyncio.get_event_loop().run_in_executor(None, stderr.read)
            exit_code = stdout.channel.recv_exit_status()

            execution_time = (datetime.now() - start_time).total_seconds()
            session.update_activity()

            return {
                "stdout": stdout_data.decode("utf-8", errors="replace"),
                "stderr": stderr_data.decode("utf-8", errors="replace"),
                "exit_code": exit_code,
                "execution_time": execution_time,
                "host_id": host_id,
            }

        except Exception as e:
            logger.error("Command execution failed on host %s: %s", host_id, e)
            raise

    async def create_interactive_session(
        self,
        host_id: str,
        term_type: str = "xterm-256color",
        cols: int = 80,
        rows: int = 24,
        accessed_by: str = "terminal_handler",
    ) -> SSHSession:
        """
        Create an interactive PTY session for terminal integration.

        Args:
            host_id: ID of the infrastructure host
            term_type: Terminal type for PTY
            cols: Terminal width in columns
            rows: Terminal height in rows
            accessed_by: Identifier for audit logging

        Returns:
            SSHSession with interactive channel
        """
        session = await self.connect(host_id, accessed_by)

        try:
            # Get a transport
            transport = session.client.get_transport()
            if not transport:
                raise ConnectionError("No transport available")

            # Open a channel
            channel = transport.open_session()
            channel.get_pty(term_type, cols, rows)
            channel.invoke_shell()

            session.channel = channel
            session.is_interactive = True

            logger.info("Interactive SSH session created for host: %s", host_id)
            return session

        except Exception as e:
            logger.error("Failed to create interactive session for host %s: %s", host_id, e)
            raise

    async def read_from_channel(
        self,
        session: SSHSession,
        callback: Optional[Callable[[bytes], None]] = None,
        timeout: float = 0.1,
    ) -> bytes:
        """
        Read data from an interactive channel.

        Args:
            session: SSHSession with interactive channel
            callback: Optional callback for data handling
            timeout: Read timeout in seconds

        Returns:
            Data read from channel
        """
        if not session.channel or not session.is_interactive:
            raise ValueError("Session does not have an interactive channel")

        data = b""
        try:
            if session.channel.recv_ready():
                data = session.channel.recv(65535)
                session.update_activity()
                if callback and data:
                    callback(data)
        except Exception as e:
            logger.error("Error reading from SSH channel: %s", e)

        return data

    async def write_to_channel(self, session: SSHSession, data: bytes) -> None:
        """
        Write data to an interactive channel.

        Args:
            session: SSHSession with interactive channel
            data: Data to write
        """
        if not session.channel or not session.is_interactive:
            raise ValueError("Session does not have an interactive channel")

        try:
            await asyncio.get_event_loop().run_in_executor(None, session.channel.send, data)
            session.update_activity()
        except Exception as e:
            logger.error("Error writing to SSH channel: %s", e)
            raise

    async def resize_pty(self, session: SSHSession, cols: int, rows: int) -> None:
        """
        Resize the PTY for an interactive session.

        Args:
            session: SSHSession with interactive channel
            cols: New terminal width
            rows: New terminal height
        """
        if not session.channel or not session.is_interactive:
            raise ValueError("Session does not have an interactive channel")

        try:
            session.channel.resize_pty(cols, rows)
        except Exception as e:
            logger.error("Error resizing PTY: %s", e)

    def _is_session_valid(self, session: SSHSession) -> bool:
        """Check if an SSH session is still valid."""
        try:
            if not session.client:
                return False

            transport = session.client.get_transport()
            if not transport or not transport.is_active():
                return False

            # Check for session timeout (30 minutes of inactivity)
            inactive_time = (datetime.now() - session.last_activity).total_seconds()
            if inactive_time > 1800:
                return False

            return True

        except Exception:
            return False

    async def _close_session(self, host_id: str) -> None:
        """Close and cleanup an SSH session."""
        session = self._sessions.pop(host_id, None)
        if session:
            try:
                if session.channel:
                    session.channel.close()
                if session.client:
                    session.client.close()
                logger.info("SSH session closed for host: %s", host_id)
            except Exception as e:
                logger.warning("Error closing SSH session for host %s: %s", host_id, e)

    async def disconnect(self, host_id: str) -> None:
        """
        Disconnect from an infrastructure host.

        Args:
            host_id: ID of the infrastructure host
        """
        async with self._lock:
            await self._close_session(host_id)

    async def disconnect_all(self) -> None:
        """Disconnect all SSH sessions."""
        async with self._lock:
            for host_id in list(self._sessions.keys()):
                await self._close_session(host_id)

    def get_session(self, host_id: str) -> Optional[SSHSession]:
        """Get an existing SSH session if available."""
        session = self._sessions.get(host_id)
        if session and self._is_session_valid(session):
            return session
        return None

    def list_active_sessions(self) -> Dict[str, Dict[str, Any]]:
        """List all active SSH sessions with their status."""
        result = {}
        for host_id, session in self._sessions.items():
            if self._is_session_valid(session):
                result[host_id] = {
                    "created_at": session.created_at.isoformat(),
                    "last_activity": session.last_activity.isoformat(),
                    "is_interactive": session.is_interactive,
                }
        return result


def get_ssh_connection_service() -> SSHConnectionService:
    """Get the singleton SSH connection service instance."""
    return SSHConnectionService.get_instance()
