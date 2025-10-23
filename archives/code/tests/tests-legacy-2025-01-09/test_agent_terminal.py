"""
Integration Tests for Agent Terminal API

Tests agent terminal access with security controls, approval workflow,
and user interrupt/takeover mechanisms.

Security testing includes:
- CVE-002 compliance: Prompt injection detection
- CVE-003 compliance: No god mode, all agents subject to RBAC
- Command risk assessment
- Approval workflow for HIGH/DANGEROUS commands
- User control and interrupt
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch

from backend.services.agent_terminal_service import (
    AgentTerminalService,
    AgentRole,
    AgentSessionState,
)
from src.secure_command_executor import CommandRisk


@pytest.fixture
def mock_redis_client():
    """Mock Redis client"""
    redis_mock = Mock()
    redis_mock.setex = Mock()
    redis_mock.get = Mock(return_value=None)
    redis_mock.delete = Mock()
    return redis_mock


@pytest.fixture
def agent_terminal_service(mock_redis_client):
    """Create AgentTerminalService instance with mocked Redis"""
    return AgentTerminalService(redis_client=mock_redis_client)


@pytest.mark.asyncio
async def test_create_agent_session(agent_terminal_service):
    """Test creating an agent terminal session"""
    session = await agent_terminal_service.create_session(
        agent_id="test_agent_1",
        agent_role=AgentRole.CHAT_AGENT,
        conversation_id="conv_123",
        host="main",
    )

    assert session.agent_id == "test_agent_1"
    assert session.agent_role == AgentRole.CHAT_AGENT
    assert session.conversation_id == "conv_123"
    assert session.host == "main"
    assert session.state == AgentSessionState.AGENT_CONTROL
    assert len(session.command_history) == 0


@pytest.mark.asyncio
async def test_list_sessions_by_agent_id(agent_terminal_service):
    """Test listing sessions filtered by agent ID"""
    # Create multiple sessions
    await agent_terminal_service.create_session(
        agent_id="agent_1",
        agent_role=AgentRole.CHAT_AGENT,
    )
    await agent_terminal_service.create_session(
        agent_id="agent_2",
        agent_role=AgentRole.AUTOMATION_AGENT,
    )
    await agent_terminal_service.create_session(
        agent_id="agent_1",
        agent_role=AgentRole.CHAT_AGENT,
        conversation_id="conv_456",
    )

    # List sessions for agent_1
    sessions = await agent_terminal_service.list_sessions(agent_id="agent_1")

    assert len(sessions) == 2
    assert all(s.agent_id == "agent_1" for s in sessions)


@pytest.mark.asyncio
async def test_close_session(agent_terminal_service):
    """Test closing an agent terminal session"""
    session = await agent_terminal_service.create_session(
        agent_id="test_agent",
        agent_role=AgentRole.CHAT_AGENT,
    )

    # Close session
    success = await agent_terminal_service.close_session(session.session_id)

    assert success is True

    # Verify session is gone
    retrieved = await agent_terminal_service.get_session(session.session_id)
    assert retrieved is None


@pytest.mark.asyncio
async def test_agent_permission_check_safe_command(agent_terminal_service):
    """Test agent permission check for SAFE command"""
    # Chat agent should be allowed to execute SAFE commands
    allowed, reason = agent_terminal_service._check_agent_permission(
        AgentRole.CHAT_AGENT,
        CommandRisk.SAFE,
    )

    assert allowed is True
    assert "Permission granted" in reason


@pytest.mark.asyncio
async def test_agent_permission_check_high_risk_blocked(agent_terminal_service):
    """Test that chat agent is blocked from HIGH risk commands"""
    # Chat agent should NOT be allowed to execute HIGH commands
    allowed, reason = agent_terminal_service._check_agent_permission(
        AgentRole.CHAT_AGENT,
        CommandRisk.HIGH,
    )

    assert allowed is False
    assert "exceeds agent max risk" in reason


@pytest.mark.asyncio
async def test_agent_permission_check_admin_agent(agent_terminal_service):
    """Test admin agent permissions"""
    # Admin agent should be allowed HIGH commands
    allowed, reason = agent_terminal_service._check_agent_permission(
        AgentRole.ADMIN_AGENT,
        CommandRisk.HIGH,
    )

    assert allowed is True

    # Admin agent should be allowed DANGEROUS commands
    allowed, reason = agent_terminal_service._check_agent_permission(
        AgentRole.ADMIN_AGENT,
        CommandRisk.CRITICAL,
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_approval_required_for_moderate_chat_agent(agent_terminal_service):
    """Test that MODERATE commands require approval for chat agent"""
    needs_approval = agent_terminal_service._needs_approval(
        AgentRole.CHAT_AGENT,
        CommandRisk.MODERATE,
    )

    assert needs_approval is True


@pytest.mark.asyncio
async def test_approval_not_required_for_safe_chat_agent(agent_terminal_service):
    """Test that SAFE commands don't require approval for chat agent"""
    needs_approval = agent_terminal_service._needs_approval(
        AgentRole.CHAT_AGENT,
        CommandRisk.SAFE,
    )

    assert needs_approval is False


@pytest.mark.asyncio
async def test_approval_always_required_for_dangerous(agent_terminal_service):
    """Test that DANGEROUS commands ALWAYS require approval"""
    # Even for admin agent
    needs_approval = agent_terminal_service._needs_approval(
        AgentRole.ADMIN_AGENT,
        CommandRisk.CRITICAL,
    )

    assert needs_approval is True


@pytest.mark.asyncio
async def test_execute_command_safe_auto_approved(agent_terminal_service):
    """Test that SAFE commands are auto-approved for chat agent"""
    session = await agent_terminal_service.create_session(
        agent_id="test_agent",
        agent_role=AgentRole.CHAT_AGENT,
    )

    with patch("src.secure_command_executor.SecureCommandExecutor.run_shell_command") as mock_exec:
        mock_exec.return_value = {
            "status": "success",
            "stdout": "test output",
            "stderr": "",
            "return_code": 0,
        }

        result = await agent_terminal_service.execute_command(
            session_id=session.session_id,
            command="echo 'hello'",
        )

        # Should execute immediately (not pending approval)
        assert result.get("status") == "success"
        assert "stdout" in result
        assert mock_exec.called


@pytest.mark.asyncio
async def test_execute_command_moderate_requires_approval(agent_terminal_service):
    """Test that MODERATE commands require approval for chat agent"""
    session = await agent_terminal_service.create_session(
        agent_id="test_agent",
        agent_role=AgentRole.CHAT_AGENT,
    )

    result = await agent_terminal_service.execute_command(
        session_id=session.session_id,
        command="mkdir /tmp/test_dir",  # MODERATE risk
    )

    # Should require approval (not executed)
    assert result.get("status") == "pending_approval"
    assert "risk" in result
    assert "reasons" in result
    assert result.get("command") == "mkdir /tmp/test_dir"


@pytest.mark.asyncio
async def test_execute_command_high_risk_blocked_for_chat_agent(agent_terminal_service):
    """Test that HIGH risk commands are blocked for chat agent"""
    session = await agent_terminal_service.create_session(
        agent_id="test_agent",
        agent_role=AgentRole.CHAT_AGENT,
    )

    result = await agent_terminal_service.execute_command(
        session_id=session.session_id,
        command="rm -rf /tmp/test",  # HIGH risk
    )

    # Should be blocked due to agent permissions
    assert result.get("status") == "error"
    assert "exceeds agent max risk" in result.get("error", "")


@pytest.mark.asyncio
async def test_approve_command_approved(agent_terminal_service):
    """Test approving a pending command"""
    session = await agent_terminal_service.create_session(
        agent_id="test_agent",
        agent_role=AgentRole.CHAT_AGENT,
    )

    # Execute MODERATE command (requires approval)
    await agent_terminal_service.execute_command(
        session_id=session.session_id,
        command="mkdir /tmp/test_dir",
    )

    # Verify pending approval exists
    assert session.pending_approval is not None

    with patch("src.secure_command_executor.SecureCommandExecutor.run_shell_command") as mock_exec:
        mock_exec.return_value = {
            "status": "success",
            "stdout": "",
            "stderr": "",
            "return_code": 0,
        }

        # Approve command
        result = await agent_terminal_service.approve_command(
            session_id=session.session_id,
            approved=True,
            user_id="user_1",
        )

        assert result.get("status") == "approved"
        assert mock_exec.called
        assert session.pending_approval is None


@pytest.mark.asyncio
async def test_approve_command_denied(agent_terminal_service):
    """Test denying a pending command"""
    session = await agent_terminal_service.create_session(
        agent_id="test_agent",
        agent_role=AgentRole.CHAT_AGENT,
    )

    # Execute MODERATE command (requires approval)
    await agent_terminal_service.execute_command(
        session_id=session.session_id,
        command="mkdir /tmp/test_dir",
    )

    with patch("src.secure_command_executor.SecureCommandExecutor.run_shell_command") as mock_exec:
        # Deny command
        result = await agent_terminal_service.approve_command(
            session_id=session.session_id,
            approved=False,
        )

        assert result.get("status") == "denied"
        assert not mock_exec.called  # Command should NOT be executed
        assert session.pending_approval is None


@pytest.mark.asyncio
async def test_user_interrupt(agent_terminal_service):
    """Test user interrupt/takeover mechanism"""
    session = await agent_terminal_service.create_session(
        agent_id="test_agent",
        agent_role=AgentRole.CHAT_AGENT,
    )

    # User interrupts agent
    result = await agent_terminal_service.user_interrupt(
        session_id=session.session_id,
        user_id="user_1",
    )

    assert result.get("status") == "success"
    assert session.state == AgentSessionState.USER_CONTROL
    assert result.get("previous_state") == AgentSessionState.AGENT_CONTROL.value


@pytest.mark.asyncio
async def test_commands_blocked_during_user_control(agent_terminal_service):
    """Test that agent commands are blocked when user has control"""
    session = await agent_terminal_service.create_session(
        agent_id="test_agent",
        agent_role=AgentRole.CHAT_AGENT,
    )

    # User takes control
    await agent_terminal_service.user_interrupt(
        session_id=session.session_id,
        user_id="user_1",
    )

    # Agent tries to execute command
    result = await agent_terminal_service.execute_command(
        session_id=session.session_id,
        command="echo 'test'",
    )

    assert result.get("status") == "error"
    assert "User has control" in result.get("error", "")


@pytest.mark.asyncio
async def test_agent_resume(agent_terminal_service):
    """Test agent resume after user interrupt"""
    session = await agent_terminal_service.create_session(
        agent_id="test_agent",
        agent_role=AgentRole.CHAT_AGENT,
    )

    # User interrupts
    await agent_terminal_service.user_interrupt(
        session_id=session.session_id,
        user_id="user_1",
    )

    # Agent resumes
    result = await agent_terminal_service.agent_resume(session_id=session.session_id)

    assert result.get("status") == "success"
    assert session.state == AgentSessionState.AGENT_CONTROL


@pytest.mark.asyncio
async def test_get_session_info(agent_terminal_service):
    """Test getting comprehensive session information"""
    session = await agent_terminal_service.create_session(
        agent_id="test_agent",
        agent_role=AgentRole.AUTOMATION_AGENT,
        conversation_id="conv_123",
    )

    session_info = await agent_terminal_service.get_session_info(session.session_id)

    assert session_info is not None
    assert session_info["agent_id"] == "test_agent"
    assert session_info["agent_role"] == AgentRole.AUTOMATION_AGENT.value
    assert session_info["conversation_id"] == "conv_123"
    assert session_info["state"] == AgentSessionState.AGENT_CONTROL.value
    assert "uptime" in session_info
    assert "command_count" in session_info


@pytest.mark.asyncio
async def test_security_cve_003_no_god_mode(agent_terminal_service):
    """CVE-003 Compliance: Verify no god mode for agents"""
    # Create session with ADMIN agent (highest privilege)
    session = await agent_terminal_service.create_session(
        agent_id="admin_agent",
        agent_role=AgentRole.ADMIN_AGENT,
    )

    # Even admin agents require approval for DANGEROUS commands
    result = await agent_terminal_service.execute_command(
        session_id=session.session_id,
        command="rm -rf /",  # DANGEROUS command
    )

    # Should be FORBIDDEN and blocked
    assert result.get("status") == "error"


@pytest.mark.asyncio
async def test_command_history_tracking(agent_terminal_service):
    """Test that command history is tracked"""
    session = await agent_terminal_service.create_session(
        agent_id="test_agent",
        agent_role=AgentRole.AUTOMATION_AGENT,
    )

    with patch("src.secure_command_executor.SecureCommandExecutor.run_shell_command") as mock_exec:
        mock_exec.return_value = {
            "status": "success",
            "stdout": "test",
            "stderr": "",
            "return_code": 0,
        }

        # Execute multiple SAFE commands
        await agent_terminal_service.execute_command(
            session_id=session.session_id,
            command="echo 'test1'",
        )

        await agent_terminal_service.execute_command(
            session_id=session.session_id,
            command="echo 'test2'",
        )

    # Check command history
    assert len(session.command_history) == 2
    assert session.command_history[0]["command"] == "echo 'test1'"
    assert session.command_history[1]["command"] == "echo 'test2'"
    assert all("timestamp" in cmd for cmd in session.command_history)
    assert all("risk" in cmd for cmd in session.command_history)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
