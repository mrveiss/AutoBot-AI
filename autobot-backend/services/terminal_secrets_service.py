# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal Secrets Service - SSH Key Integration for Terminal Sessions

Provides automatic SSH key injection and management for terminal sessions.
Integrates with the secrets management system to provide secure key handling.

Features:
- Auto-detect SSH key requirements from commands
- Inject SSH keys into ssh-agent for terminal sessions
- Support for passphrase-protected keys
- Cleanup of keys when terminal session ends
- Audit logging for key usage

Related Issues:
- #211 - Secrets Management System - Missing Features

Usage:
    from services.terminal_secrets_service import get_terminal_secrets_service

    service = get_terminal_secrets_service()

    # Setup SSH keys for a terminal session
    await service.setup_ssh_keys(session_id, chat_id)

    # Cleanup when session ends
    await service.cleanup_session_keys(session_id)
"""

import asyncio
import logging
import os
import subprocess  # nosec B404 - Required for SSH key validation
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from services.agent_secrets_integration import (
    AgentSecretsIntegration,
    get_agent_secrets_integration,
)

logger = logging.getLogger(__name__)


@dataclass
class SSHKeyInfo:
    """Information about an injected SSH key."""

    secret_id: str
    name: str
    key_path: str  # Temporary file path for the key
    fingerprint: Optional[str] = None
    added_to_agent: bool = False
    passphrase_required: bool = False


@dataclass
class SessionKeyState:
    """Tracks SSH keys for a terminal session."""

    session_id: str
    chat_id: Optional[str] = None
    keys: List[SSHKeyInfo] = field(default_factory=list)
    agent_socket: Optional[str] = None
    agent_pid: Optional[int] = None
    temp_dir: Optional[str] = None


class TerminalSecretsService:
    """
    Service for managing secrets in terminal sessions.

    Handles SSH key injection, passphrase prompts, and cleanup
    for terminal sessions that need credential access.
    """

    def __init__(self, agent_secrets: Optional[AgentSecretsIntegration] = None):
        """Initialize terminal secrets service.

        Args:
            agent_secrets: Optional AgentSecretsIntegration instance
        """
        self._agent_secrets = agent_secrets
        self._sessions: Dict[str, SessionKeyState] = {}
        self._sessions_lock = threading.Lock()
        logger.info("TerminalSecretsService initialized")

    @property
    def agent_secrets(self) -> AgentSecretsIntegration:
        """Get agent secrets integration (lazy initialization)."""
        if self._agent_secrets is None:
            self._agent_secrets = get_agent_secrets_integration()
        return self._agent_secrets

    def _create_session_state(
        self, session_id: str, chat_id: Optional[str]
    ) -> SessionKeyState:
        """Helper for setup_ssh_keys. Ref: #1088."""
        state = SessionKeyState(session_id=session_id, chat_id=chat_id)
        state.temp_dir = tempfile.mkdtemp(prefix=f"autobot_ssh_{session_id}_")
        return state

    def _store_session_state(self, session_id: str, state: SessionKeyState) -> None:
        """Helper for setup_ssh_keys. Ref: #1088."""
        with self._sessions_lock:
            self._sessions[session_id] = state

    @staticmethod
    def _make_setup_result(session_id: str) -> Dict:
        """Helper for setup_ssh_keys. Ref: #1088."""
        return {
            "keys_available": [],
            "keys_loaded": 0,
            "errors": [],
            "session_id": session_id,
        }

    def _filter_keys_by_name(
        self, ssh_keys: List[Dict], specific_key_names: Optional[List[str]]
    ) -> List[Dict]:
        """
        Filter SSH keys by specific names if provided.

        Issue #665: Extracted from setup_ssh_keys.
        """
        if specific_key_names:
            return [k for k in ssh_keys if k["name"] in specific_key_names]
        return ssh_keys

    async def _prepare_session_keys(
        self,
        session_state: SessionKeyState,
        ssh_keys: List[Dict],
        result: Dict,
    ) -> None:
        """
        Prepare all SSH keys for a session, updating result dict.

        Issue #665: Extracted from setup_ssh_keys.

        Args:
            session_state: Session state to add keys to
            ssh_keys: List of key data dictionaries
            result: Result dict to update with key names and errors
        """
        for key_data in ssh_keys:
            try:
                key_info = await self._prepare_ssh_key(key_data, session_state.temp_dir)
                session_state.keys.append(key_info)
                result["keys_available"].append(key_data["name"])
                result["keys_loaded"] += 1
                logger.info(
                    "Prepared SSH key '%s' for session %s",
                    key_data["name"],
                    session_state.session_id,
                )
            except Exception as e:
                error_msg = f"Failed to prepare key '{key_data['name']}': {e}"
                result["errors"].append(error_msg)
                logger.error(error_msg)

    async def setup_ssh_keys(
        self,
        session_id: str,
        chat_id: Optional[str] = None,
        include_general: bool = True,
        specific_key_names: Optional[List[str]] = None,
    ) -> Dict[str, any]:
        """Setup SSH keys for a terminal session.

        Issue #665: Refactored from 90 lines to use extracted helper methods.

        Retrieves SSH keys from secrets storage and prepares them for use
        in the terminal session. Keys are written to temporary files with
        proper permissions.

        Args:
            session_id: Terminal session ID
            chat_id: Optional chat ID for chat-scoped keys
            include_general: Whether to include general-scoped keys
            specific_key_names: Optional list of specific key names to use

        Returns:
            Dictionary with setup results:
            - keys_available: List of available key names
            - keys_loaded: Number of keys loaded
            - errors: Any errors encountered
        """
        result = self._make_setup_result(session_id)

        try:
            # Get SSH keys from secrets
            ssh_keys = await self.agent_secrets.get_ssh_keys_for_terminal(
                chat_id=chat_id, include_general=include_general
            )

            if not ssh_keys:
                logger.debug("No SSH keys available for session %s", session_id)
                return result

            # Filter by specific names (Issue #665: uses helper)
            ssh_keys = self._filter_keys_by_name(ssh_keys, specific_key_names)

            # Create session state with temp directory
            session_state = self._create_session_state(session_id, chat_id)

            # Prepare all keys (Issue #665: uses helper)
            await self._prepare_session_keys(session_state, ssh_keys, result)

            # Store session state
            self._store_session_state(session_id, session_state)

            logger.info(
                "SSH key setup complete for session %s: %d keys loaded",
                session_id,
                result["keys_loaded"],
            )

        except Exception as e:
            error_msg = f"SSH key setup failed: {e}"
            result["errors"].append(error_msg)
            logger.error(error_msg)

        return result

    async def _prepare_ssh_key(self, key_data: Dict, temp_dir: str) -> SSHKeyInfo:
        """Prepare an SSH key for use in a terminal session.

        Writes the key to a temporary file with proper permissions
        and determines if it requires a passphrase.

        Args:
            key_data: Dictionary with key name and value
            temp_dir: Temporary directory for key files

        Returns:
            SSHKeyInfo with key details
        """
        key_name = key_data["name"]
        key_value = key_data["value"]

        # Sanitize key name for filename
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in key_name)
        key_path = os.path.join(temp_dir, f"{safe_name}")

        # Write key to file
        with open(key_path, "w", encoding="utf-8") as f:
            f.write(key_value)
            if not key_value.endswith("\n"):
                f.write("\n")

        # Set proper permissions (read-only for owner)
        os.chmod(key_path, 0o600)

        # Check if key requires passphrase
        passphrase_required = self._check_passphrase_required(key_path)

        # Get key fingerprint if possible
        fingerprint = await self._get_key_fingerprint(key_path)

        return SSHKeyInfo(
            secret_id=key_data.get("id", ""),
            name=key_name,
            key_path=key_path,
            fingerprint=fingerprint,
            passphrase_required=passphrase_required,
        )

    def _check_passphrase_required(self, key_path: str) -> bool:
        """Check if an SSH key requires a passphrase.

        Args:
            key_path: Path to the SSH key file

        Returns:
            True if key requires passphrase, False otherwise
        """
        try:
            # Try to read key without passphrase using ssh-keygen
            result = subprocess.run(  # nosec B607 - ssh-keygen is a trusted system tool
                ["ssh-keygen", "-y", "-P", "", "-f", key_path],
                capture_output=True,
                timeout=5,
            )
            # If exit code is 0, no passphrase needed
            return result.returncode != 0
        except Exception:
            # If check fails, assume passphrase may be needed
            return True

    async def _get_key_fingerprint(self, key_path: str) -> Optional[str]:
        """Get the fingerprint of an SSH key.

        Args:
            key_path: Path to the SSH key file

        Returns:
            Key fingerprint string or None if couldn't be determined
        """
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["ssh-keygen", "-l", "-f", key_path],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Output format: "2048 SHA256:xxx user@host (RSA)"
                parts = result.stdout.strip().split()
                if len(parts) >= 2:
                    return parts[1]  # SHA256:xxx
            return None
        except Exception as e:
            logger.debug("Could not get key fingerprint: %s", e)
            return None

    def _find_key_by_name(
        self, session_state: SessionKeyState, key_name: str
    ) -> Optional[SSHKeyInfo]:
        """
        Find an SSH key by name in session state.

        Issue #665: Extracted from add_key_to_agent.

        Args:
            session_state: Session key state
            key_name: Name of the key to find

        Returns:
            SSHKeyInfo if found, None otherwise
        """
        for k in session_state.keys:
            if k.name == key_name:
                return k
        return None

    def _setup_askpass_script(self, temp_dir: str) -> str:
        """
        Create a temporary askpass script for passphrase handling.

        Issue #665: Extracted from add_key_to_agent.

        Args:
            temp_dir: Directory for temporary files

        Returns:
            Path to the askpass script
        """
        askpass_script = os.path.join(temp_dir, "askpass.sh")
        with open(askpass_script, "w", encoding="utf-8") as f:
            f.write("#!/bin/bash\ncat\n")
        os.chmod(askpass_script, 0o700)
        return askpass_script

    async def _run_ssh_add(
        self,
        key_path: str,
        env: dict,
        passphrase: Optional[str] = None,
    ) -> subprocess.CompletedProcess:
        """
        Run ssh-add command with the given environment.

        Issue #665: Extracted from add_key_to_agent.

        Args:
            key_path: Path to the SSH key file
            env: Environment variables including SSH_AUTH_SOCK
            passphrase: Optional passphrase for encrypted keys

        Returns:
            CompletedProcess with result of ssh-add command
        """
        return await asyncio.to_thread(
            subprocess.run,
            ["ssh-add", key_path],
            input=passphrase,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )

    async def add_key_to_agent(
        self,
        session_id: str,
        key_name: str,
        passphrase: Optional[str] = None,
    ) -> bool:
        """Add an SSH key to ssh-agent for a session. Ref: #1088."""
        with self._sessions_lock:
            session_state = self._sessions.get(session_id)

        if not session_state:
            logger.warning("No session state found for %s", session_id)
            return False

        # Find the key (Issue #665: uses _find_key_by_name helper)
        key_info = self._find_key_by_name(session_state, key_name)

        if not key_info:
            logger.warning("Key '%s' not found in session %s", key_name, session_id)
            return False

        if key_info.added_to_agent:
            logger.debug("Key '%s' already added to agent", key_name)
            return True

        try:
            # Setup environment for ssh-add
            env = os.environ.copy()
            if session_state.agent_socket:
                env["SSH_AUTH_SOCK"] = session_state.agent_socket

            askpass_script = None
            if key_info.passphrase_required and passphrase:
                # Setup askpass for passphrase (Issue #665: uses helper)
                askpass_script = self._setup_askpass_script(session_state.temp_dir)
                env["SSH_ASKPASS"] = askpass_script
                env["SSH_ASKPASS_REQUIRE"] = "force"
                env["DISPLAY"] = ":0"  # Required for SSH_ASKPASS

            # Run ssh-add (Issue #665: uses _run_ssh_add helper)
            result = await self._run_ssh_add(
                key_info.key_path, env, passphrase if askpass_script else None
            )

            # Cleanup askpass script if created
            if askpass_script:
                try:
                    os.remove(askpass_script)
                except OSError:
                    pass

            if result.returncode == 0:
                key_info.added_to_agent = True
                logger.info("Added key '%s' to ssh-agent", key_name)
                return True
            else:
                logger.error(
                    "Failed to add key '%s' to agent: %s", key_name, result.stderr
                )
                return False

        except Exception as e:
            logger.error("Error adding key to agent: %s", e)
            return False

    def get_session_keys(self, session_id: str) -> List[Dict[str, any]]:
        """Get list of SSH keys available for a session.

        Args:
            session_id: Terminal session ID

        Returns:
            List of key information dictionaries
        """
        with self._sessions_lock:
            session_state = self._sessions.get(session_id)

        if not session_state:
            return []

        return [
            {
                "name": k.name,
                "fingerprint": k.fingerprint,
                "passphrase_required": k.passphrase_required,
                "added_to_agent": k.added_to_agent,
            }
            for k in session_state.keys
        ]

    def get_key_path(self, session_id: str, key_name: str) -> Optional[str]:
        """Get the file path for an SSH key in a session.

        Used when executing ssh/scp commands that need the key file path.

        Args:
            session_id: Terminal session ID
            key_name: Name of the key

        Returns:
            File path to the key or None if not found
        """
        with self._sessions_lock:
            session_state = self._sessions.get(session_id)

        if not session_state:
            return None

        for k in session_state.keys:
            if k.name == key_name:
                return k.key_path

        return None

    async def cleanup_session_keys(self, session_id: str) -> None:
        """Cleanup SSH keys for a terminal session.

        Removes temporary key files and clears session state.
        Should be called when a terminal session ends.

        Args:
            session_id: Terminal session ID to cleanup
        """
        with self._sessions_lock:
            session_state = self._sessions.pop(session_id, None)

        if not session_state:
            return

        try:
            # Remove temporary key files
            for key_info in session_state.keys:
                try:
                    if os.path.exists(key_info.key_path):
                        # Securely overwrite before deletion
                        with open(key_info.key_path, "wb") as f:
                            f.write(b"\x00" * os.path.getsize(key_info.key_path))
                        os.remove(key_info.key_path)
                except Exception as e:
                    logger.warning(
                        "Failed to remove key file %s: %s",
                        key_info.key_path,
                        e,
                    )

            # Remove temporary directory
            if session_state.temp_dir and os.path.exists(session_state.temp_dir):
                try:
                    os.rmdir(session_state.temp_dir)
                except Exception as e:
                    logger.warning(
                        "Failed to remove temp dir %s: %s",
                        session_state.temp_dir,
                        e,
                    )

            logger.info("Cleaned up SSH keys for session %s", session_id)

        except Exception as e:
            logger.error("Error during session key cleanup: %s", e)

    def detect_ssh_command(self, command: str) -> Optional[Dict[str, any]]:
        """Detect if a command requires SSH and extract connection details.

        Args:
            command: Command string to analyze

        Returns:
            Dictionary with SSH connection details or None if not SSH
        """
        import re

        # Patterns for SSH-related commands
        ssh_patterns = [
            r"ssh\s+(?:(?:-[a-zA-Z]+)\s+)*([^@]+@)?([^\s:]+)",
            r"scp\s+(?:(?:-[a-zA-Z]+)\s+)*(?:[^:]+:)?([^@]+@)?([^\s:]+):",
            r"sftp\s+(?:(?:-[a-zA-Z]+)\s+)*([^@]+@)?([^\s:]+)",
            r"rsync\s+.*?([^@]+@)?([^\s:]+):",
        ]

        for pattern in ssh_patterns:
            match = re.search(pattern, command)
            if match:
                groups = match.groups()
                user = groups[0].rstrip("@") if groups[0] else None
                host = groups[-1] if groups else None

                return {
                    "command_type": "ssh",
                    "user": user,
                    "host": host,
                    "original_command": command,
                }

        return None

    def get_active_sessions(self) -> List[str]:
        """Get list of session IDs with active SSH keys.

        Returns:
            List of active session IDs
        """
        with self._sessions_lock:
            return list(self._sessions.keys())


# Thread-safe singleton instance
_terminal_secrets_service: Optional[TerminalSecretsService] = None
_service_lock = threading.Lock()


def get_terminal_secrets_service() -> TerminalSecretsService:
    """Get or create the TerminalSecretsService singleton (thread-safe).

    Returns:
        TerminalSecretsService singleton instance
    """
    global _terminal_secrets_service
    if _terminal_secrets_service is None:
        with _service_lock:
            # Double-check after acquiring lock
            if _terminal_secrets_service is None:
                _terminal_secrets_service = TerminalSecretsService()
    return _terminal_secrets_service
