"""
Unit tests for Secure Terminal WebSocket functionality
Tests WebSocket terminal with security auditing and command monitoring
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the modules to test
from api.secure_terminal_websocket import (
    SecureTerminalSession,
    get_secure_session,
    handle_secure_terminal_websocket,
)


class TestSecureTerminalSession:
    """Test SecureTerminalSession functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_security_layer = MagicMock()
        self.session_id = "test_session_123"
        self.user_role = "developer"

        self.session = SecureTerminalSession(
            session_id=self.session_id,
            security_layer=self.mock_security_layer,
            user_role=self.user_role,
        )

    def test_session_initialization(self):
        """Test SecureTerminalSession initializes correctly"""
        assert self.session.session_id == self.session_id
        assert self.session.security_layer == self.mock_security_layer
        assert self.session.user_role == self.user_role
        assert self.session.websocket is None
        assert self.session.active is False
        assert self.session.audit_commands is True
        assert self.session.command_buffer == ""
        assert self.session.last_command == ""

    @pytest.mark.asyncio
    async def test_connect_websocket(self):
        """Test WebSocket connection"""
        mock_websocket = AsyncMock()

        with patch.object(self.session, "start_pty_shell") as mock_start_pty:
            with patch.object(self.session, "send_message") as mock_send:
                await self.session.connect(mock_websocket)

                assert self.session.websocket == mock_websocket
                assert self.session.active is True
                mock_websocket.accept.assert_called_once()
                mock_start_pty.assert_called_once()
                mock_send.assert_called_once()

                # Check connection message
                call_args = mock_send.call_args[0][0]
                assert call_args["type"] == "connection"
                assert call_args["status"] == "connected"
                assert call_args["session_id"] == self.session_id
                assert call_args["user_role"] == self.user_role

    @pytest.mark.asyncio
    async def test_start_pty_shell_success(self):
        """Test PTY shell startup success"""
        with patch("pty.openpty") as mock_openpty:
            with patch("subprocess.Popen") as mock_popen:
                with patch("os.close") as mock_close:
                    with patch("threading.Thread") as mock_thread:
                        mock_openpty.return_value = (10, 11)  # master_fd, slave_fd
                        mock_process = MagicMock()
                        mock_popen.return_value = mock_process

                        await self.session.start_pty_shell()

                        assert self.session.pty_fd == 10
                        assert self.session.process == mock_process
                        mock_close.assert_called_once_with(11)  # slave_fd closed
                        mock_thread.assert_called_once()
                        mock_thread.return_value.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_pty_shell_failure(self):
        """Test PTY shell startup failure"""
        with patch("pty.openpty", side_effect=OSError("PTY failed")):
            with patch.object(self.session, "send_message") as mock_send:
                await self.session.start_pty_shell()

                assert self.session.pty_fd is None
                assert self.session.process is None
                mock_send.assert_called_once()

                # Check error message
                call_args = mock_send.call_args[0][0]
                assert call_args["type"] == "error"
                assert "Failed to start secure terminal" in call_args["message"]

    def test_read_pty_output_thread(self):
        """Test PTY output reading in thread"""
        self.session.pty_fd = 10
        self.session.active = True
        self.session.websocket = AsyncMock()

        # Mock select and os.read
        with patch("select.select") as mock_select:
            with patch("os.read") as mock_read:
                with patch("asyncio.run_coroutine_threadsafe") as mock_run_coro:
                    with patch("asyncio.get_event_loop"):
                        # First call returns data, second call returns empty
                        # (to break loop)
                        mock_select.side_effect = [([10], [], []), ([], [], [])]
                        mock_read.side_effect = [b"test output", b""]

                        self.session._read_pty_output()

                        assert mock_run_coro.called
                        # Check that send_message was scheduled
                        # Can't easily test the exact message here due to
                        # coroutine wrapping

    @pytest.mark.asyncio
    async def test_send_input_command_completion(self):
        """Test sending input with command completion"""
        self.session.pty_fd = 10
        self.session.active = True
        self.session.command_buffer = "ls -l"

        with patch("os.write") as mock_write:
            with patch.object(self.session, "audit_command") as mock_audit:
                await self.session.send_input("a\n")

                mock_write.assert_called_once_with(10, b"ls -la\n")
                mock_audit.assert_called_once_with("ls -la")
                assert self.session.command_buffer == ""

    @pytest.mark.asyncio
    async def test_send_input_partial_command(self):
        """Test sending partial command input"""
        self.session.pty_fd = 10
        self.session.active = True

        with patch("os.write") as mock_write:
            with patch.object(self.session, "audit_command") as mock_audit:
                await self.session.send_input("ls ")
                await self.session.send_input("-l")

                assert self.session.command_buffer == "ls -l"
                assert mock_audit.call_count == 0  # No command completed yet
                assert mock_write.call_count == 2

    @pytest.mark.asyncio
    async def test_send_input_write_error(self):
        """Test send input with write error"""
        self.session.pty_fd = 10
        self.session.active = True

        with patch("os.write", side_effect=OSError("Write failed")):
            # Should not raise exception
            await self.session.send_input("test")

    @pytest.mark.asyncio
    async def test_audit_command_without_security_layer(self):
        """Test command auditing without security layer"""
        self.session.security_layer = None

        # Should not raise exception
        await self.session.audit_command("ls -la")

    @pytest.mark.asyncio
    async def test_audit_command_with_security_layer(self):
        """Test command auditing with security layer"""
        await self.session.audit_command("ls -la")

        # Check that audit_log was called
        self.mock_security_layer.audit_log.assert_called()
        call_args = self.mock_security_layer.audit_log.call_args

        assert call_args[1]["action"] == "terminal_command"
        assert call_args[1]["user"] == f"terminal_{self.session_id}"
        assert call_args[1]["outcome"] == "executed"
        assert call_args[1]["details"]["command"] == "ls -la"
        assert call_args[1]["details"]["user_role"] == self.user_role

    @pytest.mark.asyncio
    async def test_audit_command_with_risk_assessment(self):
        """Test command auditing with risk assessment"""
        # Mock command executor with risk assessment
        mock_executor = MagicMock()
        mock_executor.assess_command_risk.return_value = ("high", ["High risk command"])
        self.mock_security_layer.command_executor = mock_executor

        with patch.object(self.session, "send_message") as mock_send:
            await self.session.audit_command("rm -rf /tmp/test")

            # Should log risk assessment
            assert (
                self.mock_security_layer.audit_log.call_count == 2
            )  # Command + risk assessment

            # Should send security warning
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0][0]
            assert call_args["type"] == "security_warning"
            assert "high risk" in call_args["message"]

    @pytest.mark.asyncio
    async def test_audit_command_safe_command(self):
        """Test auditing of safe command"""
        mock_executor = MagicMock()
        mock_executor.assess_command_risk.return_value = ("safe", ["Safe command"])
        self.mock_security_layer.command_executor = mock_executor

        with patch.object(self.session, "send_message") as mock_send:
            await self.session.audit_command("echo hello")

            # Should only log command, not risk assessment
            assert self.mock_security_layer.audit_log.call_count == 1

            # Should not send security warning
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_audit_command_error_handling(self):
        """Test command auditing error handling"""
        self.mock_security_layer.audit_log.side_effect = Exception("Audit failed")

        # Should not raise exception
        await self.session.audit_command("test command")

    @pytest.mark.asyncio
    async def test_execute_command(self):
        """Test command execution"""
        with patch.object(self.session, "send_input") as mock_send_input:
            result = await self.session.execute_command("ls -la")

            assert result is True
            mock_send_input.assert_called_once_with("ls -la\n")

    @pytest.mark.asyncio
    async def test_execute_command_empty(self):
        """Test execution of empty command"""
        result = await self.session.execute_command("")
        assert result is False

        result = await self.session.execute_command("   ")
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_command_error(self):
        """Test command execution with error"""
        with patch.object(
            self.session, "send_input", side_effect=Exception("Send failed")
        ):
            with patch.object(self.session, "send_message") as mock_send:
                result = await self.session.execute_command("test")

                assert result is False
                mock_send.assert_called_once()

                # Check error message
                call_args = mock_send.call_args[0][0]
                assert call_args["type"] == "error"
                assert "Secure terminal error" in call_args["message"]

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        """Test successful message sending"""
        self.session.websocket = AsyncMock()
        self.session.active = True

        message = {"type": "test", "data": "test message"}
        await self.session.send_message(message)

        self.session.websocket.send_text.assert_called_once_with(json.dumps(message))

    @pytest.mark.asyncio
    async def test_send_message_error(self):
        """Test message sending with error"""
        self.session.websocket = AsyncMock()
        self.session.websocket.send_text.side_effect = Exception("Send failed")
        self.session.active = True

        # Should not raise exception
        await self.session.send_message({"type": "test"})

    @pytest.mark.asyncio
    async def test_send_message_inactive_session(self):
        """Test message sending to inactive session"""
        self.session.websocket = AsyncMock()
        self.session.active = False

        await self.session.send_message({"type": "test"})

        # Should not try to send when inactive
        self.session.websocket.send_text.assert_not_called()

    def test_disconnect(self):
        """Test session disconnection"""
        # Set up session state
        self.session.active = True
        self.session.pty_fd = 10
        self.session.process = MagicMock()
        self.session.last_command = "test command"

        with patch("os.close") as mock_close:
            self.session.disconnect()

            assert self.session.active is False
            assert self.session.pty_fd is None
            mock_close.assert_called_once_with(10)
            self.session.process.terminate.assert_called_once()

            # Check audit log for session end
            self.mock_security_layer.audit_log.assert_called()
            call_args = self.mock_security_layer.audit_log.call_args
            assert call_args[1]["action"] == "terminal_session_ended"
            assert call_args[1]["details"]["last_command"] == "test command"

    def test_disconnect_process_kill(self):
        """Test session disconnection with process kill"""
        self.session.active = True
        self.session.process = MagicMock()
        self.session.process.wait.side_effect = Exception(
            "Timeout"
        )  # Simulate TimeoutExpired

        with patch.object(self.session.process, "kill"):
            self.session.disconnect()

            self.session.process.terminate.assert_called_once()
            # Can't easily test kill call due to exception handling


class TestSecureTerminalWebSocketHandler:
    """Test WebSocket handler functionality"""

    @pytest.mark.asyncio
    async def test_handle_secure_terminal_websocket_success(self):
        """Test successful WebSocket handling"""
        mock_websocket = AsyncMock()
        mock_websocket.query_params = {"role": "developer"}

        session_id = "test_session"
        mock_security_layer = MagicMock()

        # Mock WebSocket messages
        messages = [
            json.dumps({"type": "input", "data": "ls\n"}),
            json.dumps({"type": "command", "command": "pwd"}),
            json.dumps({"type": "ping"}),
        ]

        # Set up receive_text to return messages then disconnect
        mock_websocket.receive_text.side_effect = messages + [asyncio.TimeoutError()]

        with patch(
            "api.secure_terminal_websocket._secure_sessions", {}
        ) as mock_sessions:
            # Should complete without raising exception
            await handle_secure_terminal_websocket(
                mock_websocket, session_id, mock_security_layer
            )

            # Session should have been created and cleaned up
            assert session_id not in mock_sessions

    @pytest.mark.asyncio
    async def test_handle_secure_terminal_websocket_existing_session(self):
        """Test WebSocket handling with existing session"""
        mock_websocket = AsyncMock()
        mock_websocket.query_params = {"role": "admin"}

        session_id = "existing_session"
        mock_security_layer = MagicMock()

        # Create existing session
        existing_session = MagicMock()

        mock_websocket.receive_text.side_effect = [asyncio.TimeoutError()]

        with patch(
            "api.secure_terminal_websocket._secure_sessions",
            {session_id: existing_session},
        ):
            await handle_secure_terminal_websocket(
                mock_websocket, session_id, mock_security_layer
            )

            # Should update existing session
            assert existing_session.security_layer == mock_security_layer
            assert existing_session.user_role == "admin"

    @pytest.mark.asyncio
    async def test_handle_secure_terminal_websocket_invalid_json(self):
        """Test WebSocket handling with invalid JSON"""
        mock_websocket = AsyncMock()
        mock_websocket.query_params = {}

        session_id = "test_session"

        # Send invalid JSON
        mock_websocket.receive_text.side_effect = [
            "invalid json",
            asyncio.TimeoutError(),
        ]

        with patch("api.secure_terminal_websocket._secure_sessions", {}):
            # Should handle gracefully
            await handle_secure_terminal_websocket(mock_websocket, session_id, None)

    @pytest.mark.asyncio
    async def test_handle_secure_terminal_websocket_disconnect(self):
        """Test WebSocket handling with disconnect"""
        from fastapi import WebSocketDisconnect

        mock_websocket = AsyncMock()
        mock_websocket.query_params = {}
        mock_websocket.receive_text.side_effect = WebSocketDisconnect()

        session_id = "test_session"

        with patch("api.secure_terminal_websocket._secure_sessions", {}):
            # Should handle disconnect gracefully
            await handle_secure_terminal_websocket(mock_websocket, session_id, None)

    @pytest.mark.asyncio
    async def test_handle_secure_terminal_websocket_message_types(self):
        """Test different WebSocket message types"""
        mock_websocket = AsyncMock()
        mock_websocket.query_params = {}

        session_id = "test_session"
        mock_session = AsyncMock()

        messages = [
            json.dumps({"type": "input", "data": "test input"}),
            json.dumps({"type": "command", "command": "test command"}),
            json.dumps({"type": "resize", "cols": 80, "rows": 24}),
            json.dumps({"type": "ping"}),
            json.dumps({"type": "unknown_type"}),
        ]

        mock_websocket.receive_text.side_effect = messages + [asyncio.TimeoutError()]

        with patch(
            "api.secure_terminal_websocket.SecureTerminalSession"
        ) as MockSession:
            MockSession.return_value = mock_session

            await handle_secure_terminal_websocket(mock_websocket, session_id, None)

            # Check that appropriate methods were called
            mock_session.send_input.assert_called_once_with("test input")
            mock_session.execute_command.assert_called_once_with("test command")
            mock_session.send_message.assert_called_once_with({"type": "pong"})


class TestSecureTerminalUtilities:
    """Test utility functions"""

    def test_get_secure_session_exists(self):
        """Test getting existing secure session"""
        session_id = "test_session"
        mock_session = MagicMock()

        with patch(
            "api.secure_terminal_websocket._secure_sessions",
            {session_id: mock_session},
        ):
            result = get_secure_session(session_id)
            assert result == mock_session

    def test_get_secure_session_not_exists(self):
        """Test getting non-existent secure session"""
        session_id = "nonexistent_session"

        with patch("api.secure_terminal_websocket._secure_sessions", {}):
            result = get_secure_session(session_id)
            assert result is None


# Integration tests
class TestSecureTerminalIntegration:
    """Integration tests for secure terminal functionality"""

    @pytest.mark.asyncio
    async def test_full_terminal_session_lifecycle(self):
        """Test complete terminal session lifecycle"""
        mock_security_layer = MagicMock()
        session_id = "integration_test"

        # Create session
        session = SecureTerminalSession(session_id, mock_security_layer, "developer")

        # Mock WebSocket
        mock_websocket = AsyncMock()

        # Test connection
        with patch.object(session, "start_pty_shell"):
            await session.connect(mock_websocket)
            assert session.active is True

        # Test command execution
        with patch.object(session, "send_input") as mock_send:
            await session.execute_command("echo 'integration test'")
            mock_send.assert_called_once()

        # Test auditing
        await session.audit_command("ls -la")
        mock_security_layer.audit_log.assert_called()

        # Test disconnection
        session.disconnect()
        assert session.active is False


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
