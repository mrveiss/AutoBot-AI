#!/usr/bin/env python3
"""
Test script for AutoBot Hybrid Agent Architecture
Tests local agents with the new base agent interface
"""

import asyncio
import logging
import sys
import os
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from agents.base_agent import create_agent_request, AgentRequest, AgentResponse
from agents.chat_agent import ChatAgent
from agents.rag_agent import get_rag_agent
from agents.classification_agent import ClassificationAgent
from agents.enhanced_system_commands_agent import get_enhanced_system_commands_agent
from agents.agent_client import AgentClient, AgentClientConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_local_agents():
    """Test local agents with new interface"""
    logger.info("=== Testing Local Agents ===")
    
    # Test Chat Agent
    logger.info("Testing Chat Agent...")
    try:
        chat_agent = ChatAgent()
        
        # Test capabilities
        capabilities = chat_agent.get_capabilities()
        logger.info(f"Chat Agent capabilities: {capabilities}")
        
        # Test health check
        health = await chat_agent.health_check()
        logger.info(f"Chat Agent health: {health.status.value}")
        
        # Test chat request
        request = create_agent_request(
            agent_type="chat",
            action="chat",
            payload={
                "message": "Hello, how are you?",
                "chat_history": []
            }
        )
        
        response = await chat_agent.process_request(request)
        logger.info(f"Chat response: {response.status} - {response.result.get('response_text', 'No response')[:100]}")
        
    except Exception as e:
        logger.error(f"Chat Agent test failed: {e}")
    
    # Test Classification Agent
    logger.info("Testing Classification Agent...")
    try:
        classification_agent = ClassificationAgent()
        
        capabilities = classification_agent.get_capabilities()
        logger.info(f"Classification Agent capabilities: {capabilities}")
        
        # Test classification request
        request = create_agent_request(
            agent_type="classification",
            action="classify_request",
            payload={
                "message": "What network scanning tools do we have available?"
            }
        )
        
        response = await classification_agent.process_request(request)
        logger.info(f"Classification response: {response.status}")
        if response.status == "success":
            result = response.result
            logger.info(f"Complexity: {result['complexity']}, Confidence: {result['confidence']}")
        
    except Exception as e:
        logger.error(f"Classification Agent test failed: {e}")
    
    # Test Enhanced System Commands Agent
    logger.info("Testing Enhanced System Commands Agent...")
    try:
        sys_agent = get_enhanced_system_commands_agent()
        
        capabilities = sys_agent.get_capabilities()
        logger.info(f"System Commands Agent capabilities: {capabilities}")
        
        # Test command generation request
        request = create_agent_request(
            agent_type="enhanced_system_commands",
            action="process_command",
            payload={
                "task": "List files in the current directory"
            }
        )
        
        response = await sys_agent.process_request(request)
        logger.info(f"System Commands response: {response.status}")
        if response.status == "success":
            commands = response.result.get('commands', [])
            logger.info(f"Generated commands: {commands[:3] if commands else 'None'}")  # Show first 3
        
    except Exception as e:
        logger.error(f"System Commands Agent test failed: {e}")


async def test_agent_client():
    """Test the agent client with local agents"""
    logger.info("=== Testing Agent Client ===")
    
    try:
        # Create agent client
        config = AgentClientConfig({
            "default_mode": "local",
            "request_timeout": 30.0
        })
        
        client = AgentClient(config)
        await client.initialize()
        
        # Register local agents
        await client.register_local_agent(ChatAgent())
        await client.register_local_agent(ClassificationAgent())
        await client.register_local_agent(get_enhanced_system_commands_agent())
        
        # Test chat via client
        logger.info("Testing chat via client...")
        response = await client.call_agent(
            agent_type="chat",
            action="chat",
            payload={"message": "Test message via client"}
        )
        logger.info(f"Client chat response: {response.status}")
        
        # Test classification via client
        logger.info("Testing classification via client...")
        response = await client.call_agent(
            agent_type="classification",
            action="classify_request",
            payload={"message": "Install Docker on Ubuntu"}
        )
        logger.info(f"Client classification response: {response.status}")
        
        # Get agent health status
        health_status = await client.get_agent_health_status()
        logger.info(f"Registered agents health: {list(health_status.keys())}")
        
        # Get performance stats
        stats = client.get_performance_stats()
        logger.info(f"Performance stats available for: {list(stats['client_stats'].keys())}")
        
        await client.cleanup()
        
    except Exception as e:
        logger.error(f"Agent Client test failed: {e}")


async def test_container_discovery():
    """Test container agent discovery (will fail if containers not running)"""
    logger.info("=== Testing Container Discovery ===")
    
    try:
        config = AgentClientConfig({
            "container_base_url": "http://localhost:8080"
        })
        
        client = AgentClient(config)
        await client.initialize()
        
        # Try to discover container agents
        discovered = await client.discover_container_agents()
        
        if discovered:
            logger.info(f"Discovered container agents: {discovered}")
            
            # Test container agent health
            health_status = await client.get_agent_health_status()
            logger.info(f"Container agents health: {health_status}")
        else:
            logger.info("No container agents discovered (containers may not be running)")
        
        await client.cleanup()
        
    except Exception as e:
        logger.warning(f"Container discovery test failed (expected if containers not running): {e}")


async def run_tests():
    """Run all tests"""
    logger.info("Starting AutoBot Hybrid Agent Tests")
    
    await test_local_agents()
    await test_agent_client()
    await test_container_discovery()
    
    logger.info("All tests completed!")


if __name__ == "__main__":
    asyncio.run(run_tests())