#!/usr/bin/env python3
"""
Simple test for base agent interface
Tests just the base agent functionality without heavy dependencies
"""

import asyncio
import logging
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from agents.base_agent import (
    AgentRequest,
    AgentResponse,
    LocalAgent,
    create_agent_request,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


class TestAgent(LocalAgent):
    """Simple test agent for testing base interface"""

    def __init__(self):
        super().__init__("test")
        self.capabilities = ["test_action", "ping"]

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        """Process test request"""
        if request.action == "test_action":
            return AgentResponse(
                request_id=request.request_id,
                agent_type=self.agent_type,
                status="success",
                result={"message": "Test successful", "payload": request.payload},
            )
        elif request.action == "ping":
            return AgentResponse(
                request_id=request.request_id,
                agent_type=self.agent_type,
                status="success",
                result={"pong": True},
            )
        else:
            return AgentResponse(
                request_id=request.request_id,
                agent_type=self.agent_type,
                status="error",
                result=None,
                error=f"Unknown action: {request.action}",
            )

    def get_capabilities(self) -> list:
        return self.capabilities.copy()


async def test_base_agent_interface():
    """Test the base agent interface"""
    logger.info("=== Testing Base Agent Interface ===")

    # Create test agent
    agent = TestAgent()

    # Test capabilities
    capabilities = agent.get_capabilities()
    logger.info(f"Agent capabilities: {capabilities}")

    # Test health check
    health = await agent.health_check()
    logger.info(f"Agent health: {health.status.value}")
    logger.info(f"Response time: {health.response_time_ms:.2f}ms")

    # Test statistics
    stats = agent.get_statistics()
    logger.info(f"Initial stats - Requests: {stats['total_requests']}")

    # Test basic request
    request = create_agent_request(
        agent_type="test", action="test_action", payload={"data": "test_value"}
    )

    response = await agent.execute_with_tracking(request)
    logger.info(f"Test action response: {response.status}")
    logger.info(f"Response data: {response.result}")
    logger.info(f"Execution time: {response.execution_time:.3f}s")

    # Test ping
    ping_request = create_agent_request(agent_type="test", action="ping", payload={})

    ping_response = await agent.execute_with_tracking(ping_request)
    logger.info(f"Ping response: {ping_response.status} - {ping_response.result}")

    # Test error case
    error_request = create_agent_request(
        agent_type="test", action="unknown_action", payload={}
    )

    error_response = await agent.execute_with_tracking(error_request)
    logger.info(f"Error response: {error_response.status} - {error_response.error}")

    # Test final statistics
    final_stats = agent.get_statistics()
    logger.info(
        f"Final stats - Total: {final_stats['total_requests']}, "
        f"Success: {final_stats['successful_requests']}, "
        f"Failed: {final_stats['failed_requests']}"
    )

    logger.info("Base agent interface test completed successfully!")


async def test_serialization():
    """Test request/response serialization"""
    logger.info("=== Testing Serialization ===")

    from agents.base_agent import deserialize_agent_request, serialize_agent_request

    # Create test request
    original_request = create_agent_request(
        agent_type="test",
        action="serialize_test",
        payload={"test_data": "value", "number": 42},
        context={"user_id": "test_user"},
    )

    # Serialize
    serialized = serialize_agent_request(original_request)
    logger.info(f"Serialized request length: {len(serialized)} chars")

    # Deserialize
    deserialized_request = deserialize_agent_request(serialized)

    # Verify
    assert deserialized_request.agent_type == original_request.agent_type
    assert deserialized_request.action == original_request.action
    assert deserialized_request.payload == original_request.payload
    assert deserialized_request.context == original_request.context

    logger.info("Serialization test passed!")


async def run_tests():
    """Run all tests"""
    logger.info("Starting Base Agent Tests")

    await test_base_agent_interface()
    await test_serialization()

    logger.info("All tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_tests())
