# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Manual round trip for the agent communication protocol: ``python -m protocols.agent_communication_demo --test``.

Moved out of ``protocols/agent_communication.py`` (#16950), where it sat under
``if __name__ == "__main__"`` in a module at its file-size ceiling. Unchanged
apart from its imports.
"""

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from protocols.agent_communication import (
    AgentIdentity,
    MessageHeader,
    MessagePayload,
    MessageType,
    StandardMessage,
    broadcast_to_all_agents,
    get_communication_manager,
    send_agent_request,
)

logger = get_logger(__name__)


if __name__ == "__main__":
    import argparse

    async def test_communication_protocol():
        """Run integration test for agent communication protocol."""

        logger.info("🧪 Testing Agent Communication Protocol")
        logger.info("=" * 50)

        manager = get_communication_manager()

        # Create test agents
        agent1_identity = AgentIdentity(agent_id="test_agent_1", agent_type="test", capabilities=["test", "demo"])

        agent2_identity = AgentIdentity(agent_id="test_agent_2", agent_type="test", capabilities=["test", "demo"])

        # Register agents with direct communication
        await manager.register_agent(agent1_identity, [{"type": "direct"}])
        protocol2 = await manager.register_agent(agent2_identity, [{"type": "direct"}])

        # Set up message handlers
        async def handle_request(message: StandardMessage) -> StandardMessage:
            """Handle incoming request and return response message."""
            logger.info(f"Agent 2 received request: {message.payload.content}")

            return StandardMessage(
                header=MessageHeader(message_type=MessageType.RESPONSE),
                payload=MessagePayload(content={"response": "Hello from Agent 2!"}),
            )

        protocol2.register_message_handler(MessageType.REQUEST, handle_request)

        # Test direct communication
        logger.info("Testing direct agent communication...")

        response = await send_agent_request("test_agent_1", "test_agent_2", {"message": "Hello from Agent 1!"})

        logger.info("Response received: %s", response)

        # Test broadcast
        logger.info("\nTesting broadcast communication...")
        broadcast_count = await broadcast_to_all_agents("test_agent_1", {"broadcast": "Hello everyone!"})

        logger.info("Broadcast sent to %s channels", broadcast_count)

        # Cleanup
        await manager.shutdown_all()
        logger.info("✅ Communication protocol test completed!")

    parser = argparse.ArgumentParser(description="Agent Communication Protocol Test")
    parser.add_argument("--test", action="store_true", help="Run communication test")

    args = parser.parse_args()

    if args.test:
        run_or_schedule(test_communication_protocol())
    else:
        logger.info("Use --test to run the communication protocol test")
