#!/usr/bin/env python3
"""
Quick test to verify Command Execution Queue integration works end-to-end.
This demonstrates the complete lifecycle: create → approve → execute → complete.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.models.command_execution import CommandExecution, CommandState, RiskLevel
from backend.services.command_execution_queue import get_command_queue


async def test_queue_integration():
    """Test complete command lifecycle through the queue"""

    print("=" * 80)
    print("COMMAND QUEUE INTEGRATION TEST")
    print("=" * 80)
    print()

    # Get queue instance
    queue = get_command_queue()

    # Test 1: Create a command
    print("✅ TEST 1: Creating command in queue...")
    cmd = CommandExecution(
        terminal_session_id="test_terminal_123",
        chat_id="test_chat_456",
        command="whoami",
        purpose="Test command for queue integration",
        risk_level=RiskLevel.LOW,
        risk_reasons=["Read-only command", "Safe to execute"],
        state=CommandState.PENDING_APPROVAL,
    )

    success = await queue.add_command(cmd)
    assert success, "Failed to add command to queue"
    print(f"   Command created: {cmd.command_id}")
    print(f"   Terminal: {cmd.terminal_session_id}")
    print(f"   Chat: {cmd.chat_id}")
    print(f"   State: {cmd.state.value}")
    print()

    # Test 2: Retrieve command
    print("✅ TEST 2: Retrieving command from queue...")
    retrieved_cmd = await queue.get_command(cmd.command_id)
    assert retrieved_cmd is not None, "Failed to retrieve command"
    assert retrieved_cmd.command == "whoami", "Command mismatch"
    assert retrieved_cmd.state == CommandState.PENDING_APPROVAL, "State mismatch"
    print(f"   Retrieved command: {retrieved_cmd.command}")
    print(f"   State matches: {retrieved_cmd.state == cmd.state}")
    print()

    # Test 3: Query by chat
    print("✅ TEST 3: Querying commands by chat_id...")
    chat_commands = await queue.get_chat_commands("test_chat_456")
    assert len(chat_commands) >= 1, "Failed to find command by chat_id"
    print(f"   Found {len(chat_commands)} command(s) for chat test_chat_456")
    print()

    # Test 4: Query pending approvals
    print("✅ TEST 4: Querying pending approvals...")
    pending = await queue.get_pending_approvals()
    pending_ids = [c.command_id for c in pending]
    assert cmd.command_id in pending_ids, "Command not in pending approvals"
    print(f"   Found {len(pending)} pending approval(s)")
    print("   Our command is in pending list: True")
    print()

    # Test 5: Approve command
    print("✅ TEST 5: Approving command...")
    success = await queue.approve_command(
        command_id=cmd.command_id, user_id="test_user", comment="Approved for testing"
    )
    assert success, "Failed to approve command"

    approved_cmd = await queue.get_command(cmd.command_id)
    assert approved_cmd.state == CommandState.APPROVED, "State not updated to APPROVED"
    print(f"   Command approved by: {approved_cmd.approved_by_user_id}")
    print(f"   State: {approved_cmd.state.value}")
    print(f"   Comment: {approved_cmd.approval_comment}")
    print()

    # Test 6: Start execution
    print("✅ TEST 6: Starting execution...")
    success = await queue.start_execution(cmd.command_id)
    assert success, "Failed to start execution"

    executing_cmd = await queue.get_command(cmd.command_id)
    assert (
        executing_cmd.state == CommandState.EXECUTING
    ), "State not updated to EXECUTING"
    print(f"   State: {executing_cmd.state.value}")
    print(f"   Execution started at: {executing_cmd.execution_started_at}")
    print()

    # Test 7: Complete execution
    print("✅ TEST 7: Completing execution...")
    success = await queue.complete_command(
        command_id=cmd.command_id,
        output="kali",  # Simulated whoami output
        stderr="",
        return_code=0,
    )
    assert success, "Failed to complete command"

    completed_cmd = await queue.get_command(cmd.command_id)
    assert (
        completed_cmd.state == CommandState.COMPLETED
    ), "State not updated to COMPLETED"
    assert completed_cmd.output == "kali", "Output mismatch"
    print(f"   State: {completed_cmd.state.value}")
    print(f"   Output: {completed_cmd.output}")
    print(f"   Return code: {completed_cmd.return_code}")
    print(f"   Execution completed at: {completed_cmd.execution_completed_at}")
    print()

    # Test 8: Verify no longer in pending
    print("✅ TEST 8: Verifying command removed from pending...")
    pending_after = await queue.get_pending_approvals()
    pending_ids_after = [c.command_id for c in pending_after]
    assert cmd.command_id not in pending_ids_after, "Command still in pending list"
    print("   Command removed from pending approvals: True")
    print()

    # Test 9: Test denial flow
    print("✅ TEST 9: Testing denial flow...")
    denied_cmd = CommandExecution(
        terminal_session_id="test_terminal_789",
        chat_id="test_chat_456",
        command="rm -rf /",
        purpose="Dangerous command - should be denied",
        risk_level=RiskLevel.CRITICAL,
        risk_reasons=["Destructive command"],
        state=CommandState.PENDING_APPROVAL,
    )

    await queue.add_command(denied_cmd)
    success = await queue.deny_command(
        command_id=denied_cmd.command_id, user_id="test_user", comment="Too dangerous!"
    )
    assert success, "Failed to deny command"

    denied = await queue.get_command(denied_cmd.command_id)
    assert denied.state == CommandState.DENIED, "State not updated to DENIED"
    print(f"   Command denied by: {denied.approved_by_user_id}")
    print(f"   State: {denied.state.value}")
    print(f"   Comment: {denied.approval_comment}")
    print()

    print("=" * 80)
    print("✅ ALL TESTS PASSED - QUEUE INTEGRATION WORKING PERFECTLY!")
    print("=" * 80)
    print()
    print("Summary:")
    print("  ✅ Commands can be created and added to queue")
    print("  ✅ Commands can be retrieved by ID")
    print("  ✅ Commands can be queried by chat_id")
    print("  ✅ Pending approvals can be queried")
    print("  ✅ Commands can be approved")
    print("  ✅ Commands can be marked as executing")
    print("  ✅ Commands can be completed with output")
    print("  ✅ Commands can be denied")
    print("  ✅ State transitions work correctly")
    print()
    print("🎯 The queue is ready for frontend integration!")
    print()


if __name__ == "__main__":
    asyncio.run(test_queue_integration())
