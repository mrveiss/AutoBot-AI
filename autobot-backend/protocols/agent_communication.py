#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Communication Protocol Standardization

This module defines standardized communication protocols, message formats,
and interaction patterns for inter-agent communication within AutoBot.
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

# Add project root to path for imports
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from backend.constants.threshold_constants import (  # noqa: E402
    RetryConfig,
    TimingConstants,
)

from autobot_shared.error_boundaries import error_boundary  # noqa: E402


def _parse_message_type(msg_type: Any) -> "MessageType":
    """Parse message type from various formats (Issue #315 - extracted)."""
    if isinstance(msg_type, str) and msg_type.startswith("MessageType."):
        msg_type = msg_type.split(".")[-1].lower()
    if isinstance(msg_type, str):
        return MessageType(msg_type)
    return msg_type


def _parse_priority(priority: Any) -> "MessagePriority":
    """Parse message priority from various formats (Issue #315 - extracted)."""
    if isinstance(priority, int):
        return MessagePriority(priority)
    if isinstance(priority, str):
        if priority.startswith("MessagePriority."):
            priority_name = priority.split(".")[-1]
            return MessagePriority[priority_name]
        try:
            return MessagePriority(int(priority))
        except ValueError:
            return MessagePriority.NORMAL
    return MessagePriority.NORMAL


# noqa: E402
from autobot_shared.redis_client import get_redis_client  # noqa: E402

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Standard message types for agent communication"""

    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    BROADCAST = "broadcast"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    ACK = "acknowledgment"
    DELEGATE = "delegate"
    CALLBACK = "callback"


class MessagePriority(Enum):
    """Message priority levels"""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3
    CRITICAL = 4


class CommunicationPattern(Enum):
    """Communication patterns between agents"""

    SYNCHRONOUS = "sync"  # Direct call with immediate response
    ASYNCHRONOUS = "async"  # Fire-and-forget or callback-based
    BROADCAST = "broadcast"  # One-to-many communication
    PUB_SUB = "pubsub"  # Publisher-subscriber pattern
    PIPELINE = "pipeline"  # Sequential agent chain
    PARALLEL = "parallel"  # Parallel execution and aggregation


@dataclass
class AgentIdentity:
    """Standardized agent identity information"""

    agent_id: str
    agent_type: str
    instance_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    supported_patterns: List[CommunicationPattern] = field(default_factory=list)
    health_status: str = "healthy"
    last_heartbeat: float = field(default_factory=time.time)


@dataclass
class MessageHeader:
    """Standardized message header"""

    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    message_type: MessageType = MessageType.REQUEST
    priority: MessagePriority = MessagePriority.NORMAL
    sender: Optional[AgentIdentity] = None
    recipient: Optional[str] = None  # Agent ID
    correlation_id: Optional[str] = None  # For request/response correlation
    reply_to: Optional[str] = None  # For response routing
    timestamp: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    retry_count: int = 0
    max_retries: int = RetryConfig.DEFAULT_RETRIES


@dataclass
class MessagePayload:
    """Standardized message payload"""

    content: Any = None
    content_type: str = "application/json"
    encoding: str = "utf-8"
    metadata: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"


@dataclass
class StandardMessage:
    """Complete standardized message structure"""

    header: MessageHeader
    payload: MessagePayload

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return {"header": asdict(self.header), "payload": asdict(self.payload)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StandardMessage":
        """Create message from dictionary (Issue #315 - refactored)."""
        header_data = data["header"]
        payload_data = data["payload"]

        # Reconstruct enums using helper functions
        header_data["message_type"] = _parse_message_type(header_data["message_type"])
        header_data["priority"] = _parse_priority(header_data["priority"])

        header = MessageHeader(**header_data)
        payload = MessagePayload(**payload_data)

        return cls(header=header, payload=payload)

    def to_json(self) -> str:
        """Convert message to JSON string"""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "StandardMessage":
        """Create message from JSON string"""
        return cls.from_dict(json.loads(json_str))


class CommunicationChannel(ABC):
    """Abstract base class for communication channels"""

    def __init__(self, channel_id: str):
        """Initialize communication channel with ID and inactive state."""
        self.channel_id = channel_id
        self.is_active = False

    @abstractmethod
    async def send(self, message: StandardMessage) -> bool:
        """Send a message through the channel"""

    @abstractmethod
    async def receive(
        self, timeout: Optional[float] = None
    ) -> Optional[StandardMessage]:
        """Receive a message from the channel"""

    @abstractmethod
    async def close(self):
        """Close the communication channel"""


class RedisCommunicationChannel(CommunicationChannel):
    """Redis-based communication channel implementation"""

    def __init__(self, channel_id: str):
        """Initialize Redis channel with client connection and message queue."""
        super().__init__(channel_id)
        self.redis_client = get_redis_client()
        self.channel_key = f"autobot:agent_comm:{channel_id}"
        self.message_queue = asyncio.Queue()
        self.listener_task = None

    async def start(self):
        """Start the communication channel"""
        self.is_active = True
        self.listener_task = asyncio.create_task(self._listen_for_messages())
        logger.info("Redis communication channel %s started", self.channel_id)

    async def _listen_for_messages(self):
        """Background task to listen for incoming messages"""
        while self.is_active:
            try:
                # Use Redis BLPOP for blocking message retrieval (sync call in thread)
                result = await asyncio.to_thread(
                    self.redis_client.blpop, self.channel_key, 1
                )
                if result:
                    _, message_json = result
                    if isinstance(message_json, bytes):
                        message_data = message_json.decode()
                    else:
                        message_data = str(message_json)
                    message = StandardMessage.from_json(message_data)
                    await self.message_queue.put(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error listening for messages: %s", e)
                await asyncio.sleep(TimingConstants.STANDARD_DELAY)

    async def send(self, message: StandardMessage) -> bool:
        """Send a message through Redis"""
        try:
            message_json = message.to_json()
            await asyncio.to_thread(
                self.redis_client.rpush, self.channel_key, message_json
            )

            # Set TTL for automatic cleanup
            if message.header.expires_at:
                ttl = int(message.header.expires_at - time.time())
                if ttl > 0:
                    await asyncio.to_thread(
                        self.redis_client.expire, self.channel_key, ttl
                    )

            logger.debug(
                "Message sent to channel %s: %s",
                self.channel_id,
                message.header.message_id,
            )
            return True

        except Exception as e:
            logger.error("Failed to send message: %s", e)
            return False

    async def receive(
        self, timeout: Optional[float] = None
    ) -> Optional[StandardMessage]:
        """Receive a message from the channel"""
        try:
            if timeout:
                message = await asyncio.wait_for(
                    self.message_queue.get(), timeout=timeout
                )
            else:
                message = await self.message_queue.get()
            return message
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error("Error receiving message: %s", e)
            return None

    async def close(self):
        """Close the Redis communication channel"""
        self.is_active = False
        if self.listener_task:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                logger.debug("Listener task cancelled for channel %s", self.channel_id)
        logger.info("Redis communication channel %s closed", self.channel_id)


class DirectCommunicationChannel(CommunicationChannel):
    """Direct in-memory communication channel for same-process agents"""

    def __init__(self, channel_id: str):
        """Initialize direct in-memory channel with message queue."""
        super().__init__(channel_id)
        self.message_queue = asyncio.Queue()
        self.is_active = True

    async def send(self, message: StandardMessage) -> bool:
        """Send a message directly to the queue"""
        try:
            if not self.is_active:
                return False
            await self.message_queue.put(message)
            logger.debug(
                "Message sent directly to %s: %s",
                self.channel_id,
                message.header.message_id,
            )
            return True
        except Exception as e:
            logger.error("Failed to send direct message: %s", e)
            return False

    async def receive(
        self, timeout: Optional[float] = None
    ) -> Optional[StandardMessage]:
        """Receive a message from the direct queue"""
        try:
            if timeout:
                message = await asyncio.wait_for(
                    self.message_queue.get(), timeout=timeout
                )
            else:
                message = await self.message_queue.get()
            return message
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error("Error receiving direct message: %s", e)
            return None

    async def close(self):
        """Close the direct communication channel"""
        self.is_active = False
        # Clear remaining messages
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
            except asyncio.QueueEmpty:
                break


class AgentCommunicationProtocol:
    """Main protocol handler for standardized agent communication"""

    def __init__(self, agent_identity: AgentIdentity):
        """Initialize protocol handler with agent identity and empty registries."""
        self.agent_identity = agent_identity
        self.channels: Dict[str, CommunicationChannel] = {}
        self.message_handlers: Dict[MessageType, List[Callable]] = {}
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.is_active = False
        self.heartbeat_task = None
        self.message_processor_task = None

    async def start(self):
        """Start the communication protocol"""
        self.is_active = True

        # Start heartbeat
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Start message processor
        self.message_processor_task = asyncio.create_task(
            self._process_incoming_messages()
        )

        logger.info(
            f"Agent communication protocol started for "
            f"{self.agent_identity.agent_id}"
        )

    async def stop(self):
        """Stop the communication protocol"""
        self.is_active = False

        # Cancel background tasks
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.message_processor_task:
            self.message_processor_task.cancel()

        # Close all channels
        for channel in self.channels.values():
            await channel.close()

        # Cancel pending requests
        for future in self.pending_requests.values():
            if not future.done():
                future.cancel()

        logger.info(
            "Agent communication protocol stopped for %s",
            self.agent_identity.agent_id,
        )

    def add_channel(self, channel_id: str, channel: CommunicationChannel):
        """Add a communication channel"""
        self.channels[channel_id] = channel
        logger.info("Added communication channel: %s", channel_id)

    def remove_channel(self, channel_id: str):
        """Remove a communication channel"""
        if channel_id in self.channels:
            channel = self.channels.pop(channel_id)
            asyncio.create_task(channel.close())
            logger.info("Removed communication channel: %s", channel_id)

    def register_message_handler(
        self,
        message_type: MessageType,
        handler: Callable[[StandardMessage], Awaitable[Optional[StandardMessage]]],
    ):
        """Register a handler for specific message types"""
        if message_type not in self.message_handlers:
            self.message_handlers[message_type] = []
        self.message_handlers[message_type].append(handler)
        logger.info("Registered handler for %s messages", message_type.value)

    async def send_message(
        self, message: StandardMessage, channel_id: Optional[str] = None
    ) -> bool:
        """Send a message through a specific or default channel"""

        # Set sender information
        message.header.sender = self.agent_identity

        # Select channel
        if channel_id:
            if channel_id not in self.channels:
                logger.error("Channel %s not found", channel_id)
                return False
            channel = self.channels[channel_id]
        else:
            # Use first available channel
            if not self.channels:
                logger.error("No communication channels available")
                return False
            channel = next(iter(self.channels.values()))

        # Send message with error boundary
        @error_boundary(component="agent_communication", function="send_message")
        async def _send():
            """Send message through channel with error boundary."""
            return await channel.send(message)

        return await _send()

    async def send_request(
        self,
        request: StandardMessage,
        timeout: float = TimingConstants.SHORT_TIMEOUT,
        channel_id: Optional[str] = None,
    ) -> Optional[StandardMessage]:
        """Send a request and wait for response"""

        # Set up response correlation
        correlation_id = str(uuid.uuid4())
        request.header.correlation_id = correlation_id
        request.header.message_type = MessageType.REQUEST
        request.header.reply_to = self.agent_identity.agent_id

        # Create future for response
        response_future = asyncio.Future()
        self.pending_requests[correlation_id] = response_future

        try:
            # Send the request
            if await self.send_message(request, channel_id):
                # Wait for response
                response = await asyncio.wait_for(response_future, timeout=timeout)
                return response
            else:
                logger.error("Failed to send request")
                return None

        except asyncio.TimeoutError:
            logger.error(
                "Request timeout after %ss for correlation_id: %s",
                timeout,
                correlation_id,
            )
            return None
        except Exception as e:
            logger.error("Error sending request: %s", e)
            return None
        finally:
            # Clean up
            if correlation_id in self.pending_requests:
                del self.pending_requests[correlation_id]

    async def send_response(
        self,
        response: StandardMessage,
        original_request: StandardMessage,
        channel_id: Optional[str] = None,
    ) -> bool:
        """Send a response to a request"""

        response.header.message_type = MessageType.RESPONSE
        response.header.correlation_id = original_request.header.correlation_id
        response.header.recipient = original_request.header.reply_to

        return await self.send_message(response, channel_id)

    async def broadcast(self, message: StandardMessage) -> int:
        """Broadcast a message to all channels"""

        message.header.message_type = MessageType.BROADCAST
        sent_count = 0

        for channel_id, channel in self.channels.items():
            try:
                if await channel.send(message):
                    sent_count += 1
            except Exception as e:
                logger.error("Failed to broadcast to channel %s: %s", channel_id, e)

        logger.info(
            "Broadcasted message to %s/%s channels",
            sent_count,
            len(self.channels),
        )
        return sent_count

    async def _process_incoming_messages(self):
        """Background task to process incoming messages from all channels"""
        while self.is_active:
            try:
                # Check all channels for incoming messages (Issue #376 - use constants)
                for channel_id, channel in list(self.channels.items()):
                    try:
                        message = await channel.receive(
                            timeout=TimingConstants.MICRO_DELAY
                        )
                        if message:
                            await self._handle_message(message, channel_id)
                    except Exception as e:
                        logger.error(
                            f"Error processing message from channel {channel_id}: {e}"
                        )

                # Small delay to prevent busy waiting
                # 10ms - intentionally short for responsive message processing
                await asyncio.sleep(TimingConstants.POLL_INTERVAL)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in message processor: %s", e)
                await asyncio.sleep(TimingConstants.STANDARD_DELAY)

    async def _handle_message(self, message: StandardMessage, channel_id: str):
        """Handle an incoming message"""

        logger.debug(
            "Received %s message: %s",
            message.header.message_type.value,
            message.header.message_id,
        )

        try:
            # Check if this is a response to a pending request
            if (
                message.header.message_type == MessageType.RESPONSE
                and message.header.correlation_id in self.pending_requests
            ):
                future = self.pending_requests[message.header.correlation_id]
                if not future.done():
                    future.set_result(message)
                return

            # Handle message with registered handlers
            handlers = self.message_handlers.get(message.header.message_type, [])

            for handler in handlers:
                try:
                    response = await handler(message)

                    # Send response if handler returned one
                    if response and message.header.message_type == MessageType.REQUEST:
                        await self.send_response(response, message, channel_id)

                except Exception as e:
                    logger.error("Error in message handler: %s", e)

                    # Send error response for requests
                    if message.header.message_type == MessageType.REQUEST:
                        error_response = StandardMessage(
                            header=MessageHeader(
                                message_type=MessageType.ERROR,
                                correlation_id=message.header.correlation_id,
                            ),
                            payload=MessagePayload(
                                content={
                                    "error": str(e),
                                    "error_type": type(e).__name__,
                                }
                            ),
                        )
                        await self.send_response(error_response, message, channel_id)

        except Exception as e:
            logger.error("Error handling message %s: %s", message.header.message_id, e)

    async def _heartbeat_loop(self):
        """Send periodic heartbeat messages"""
        while self.is_active:
            try:
                # Update heartbeat timestamp
                self.agent_identity.last_heartbeat = time.time()

                # Create heartbeat message
                heartbeat = StandardMessage(
                    header=MessageHeader(message_type=MessageType.HEARTBEAT),
                    payload=MessagePayload(
                        content={
                            "agent_id": self.agent_identity.agent_id,
                            "health_status": self.agent_identity.health_status,
                            "timestamp": time.time(),
                        }
                    ),
                )

                # Broadcast heartbeat
                await self.broadcast(heartbeat)

                # Wait before next heartbeat (Issue #376 - use named constants)
                await asyncio.sleep(TimingConstants.SHORT_TIMEOUT)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in heartbeat loop: %s", e)
                await asyncio.sleep(TimingConstants.MEDIUM_DELAY)


class AgentCommunicationManager:
    """Manages communication protocols for multiple agents"""

    def __init__(self):
        """Initialize manager with empty protocol registry and channel factory."""
        self.protocols: Dict[str, AgentCommunicationProtocol] = {}
        self.channel_factory = {
            "redis": RedisCommunicationChannel,
            "direct": DirectCommunicationChannel,
        }

    async def register_agent(
        self, agent_identity: AgentIdentity, channel_configs: List[Dict[str, Any]]
    ) -> AgentCommunicationProtocol:
        """Register an agent with communication protocol"""

        if agent_identity.agent_id in self.protocols:
            logger.warning("Agent %s already registered", agent_identity.agent_id)
            return self.protocols[agent_identity.agent_id]

        # Create protocol
        protocol = AgentCommunicationProtocol(agent_identity)

        # Create and add channels
        for config in channel_configs:
            channel_type = config.get("type", "direct")
            channel_id = config.get("id", f"{agent_identity.agent_id}_{channel_type}")

            if channel_type in self.channel_factory:
                channel_class = self.channel_factory[channel_type]
                channel = channel_class(channel_id)

                # Start Redis channels
                if isinstance(channel, RedisCommunicationChannel):
                    await channel.start()

                protocol.add_channel(channel_id, channel)
            else:
                logger.error("Unknown channel type: %s", channel_type)

        # Start the protocol
        await protocol.start()

        # Register in manager
        self.protocols[agent_identity.agent_id] = protocol

        logger.info(
            f"Registered agent communication protocol: " f"{agent_identity.agent_id}"
        )
        return protocol

    async def unregister_agent(self, agent_id: str):
        """Unregister an agent's communication protocol"""
        if agent_id in self.protocols:
            protocol = self.protocols.pop(agent_id)
            await protocol.stop()
            logger.info("Unregistered agent communication protocol: %s", agent_id)

    def get_protocol(self, agent_id: str) -> Optional[AgentCommunicationProtocol]:
        """Get communication protocol for an agent"""
        return self.protocols.get(agent_id)

    async def shutdown_all(self):
        """Shutdown all agent communication protocols"""
        for agent_id in list(self.protocols.keys()):
            await self.unregister_agent(agent_id)
        logger.info("All agent communication protocols shutdown")


# Global communication manager instance
# Singleton instance (thread-safe)
import threading

_communication_manager = None
_communication_manager_lock = threading.Lock()


def get_communication_manager() -> AgentCommunicationManager:
    """Get global communication manager instance (thread-safe)"""
    global _communication_manager
    if _communication_manager is None:
        with _communication_manager_lock:
            # Double-check after acquiring lock
            if _communication_manager is None:
                _communication_manager = AgentCommunicationManager()
    return _communication_manager


# Utility functions for common communication patterns


async def send_agent_request(
    sender_id: str,
    recipient_id: str,
    request_data: Any,
    timeout: float = TimingConstants.SHORT_TIMEOUT,
) -> Optional[Any]:
    """Send a request from one agent to another"""

    manager = get_communication_manager()
    sender_protocol = manager.get_protocol(sender_id)

    if not sender_protocol:
        logger.error("Sender agent %s not registered", sender_id)
        return None

    # Create request message
    request = StandardMessage(
        header=MessageHeader(message_type=MessageType.REQUEST, recipient=recipient_id),
        payload=MessagePayload(content=request_data),
    )

    # Send request and wait for response
    response = await sender_protocol.send_request(request, timeout=timeout)

    if response and response.header.message_type != MessageType.ERROR:
        return response.payload.content
    elif response and response.header.message_type == MessageType.ERROR:
        logger.error("Agent request error: %s", response.payload.content)
        return None
    else:
        logger.error("No response from agent %s", recipient_id)
        return None


async def broadcast_to_all_agents(sender_id: str, message_data: Any) -> int:
    """Broadcast a message to all registered agents"""

    manager = get_communication_manager()
    sender_protocol = manager.get_protocol(sender_id)

    if not sender_protocol:
        logger.error("Sender agent %s not registered", sender_id)
        return 0

    # Create broadcast message
    broadcast_msg = StandardMessage(
        header=MessageHeader(message_type=MessageType.BROADCAST),
        payload=MessagePayload(content=message_data),
    )

    return await sender_protocol.broadcast(broadcast_msg)


# CLI for testing the communication protocol
if __name__ == "__main__":
    import argparse

    async def test_communication_protocol():
        """Run integration test for agent communication protocol."""

        logger.info("🧪 Testing Agent Communication Protocol")
        logger.info("=" * 50)

        manager = get_communication_manager()

        # Create test agents
        agent1_identity = AgentIdentity(
            agent_id="test_agent_1", agent_type="test", capabilities=["test", "demo"]
        )

        agent2_identity = AgentIdentity(
            agent_id="test_agent_2", agent_type="test", capabilities=["test", "demo"]
        )

        # Register agents with direct communication
        await manager.register_agent(agent1_identity, [{"type": "direct"}])
        protocol2 = await manager.register_agent(agent2_identity, [{"type": "direct"}])

        # Set up message handlers
        async def handle_request(message: StandardMessage) -> StandardMessage:
            """Handle incoming request and return response message."""
            logger.info("Agent 2 received request: {message.payload.content}")

            return StandardMessage(
                header=MessageHeader(message_type=MessageType.RESPONSE),
                payload=MessagePayload(content={"response": "Hello from Agent 2!"}),
            )

        protocol2.register_message_handler(MessageType.REQUEST, handle_request)

        # Test direct communication
        logger.info("Testing direct agent communication...")

        response = await send_agent_request(
            "test_agent_1", "test_agent_2", {"message": "Hello from Agent 1!"}
        )

        logger.info("Response received: %s", response)

        # Test broadcast
        logger.info("\nTesting broadcast communication...")
        broadcast_count = await broadcast_to_all_agents(
            "test_agent_1", {"broadcast": "Hello everyone!"}
        )

        logger.info("Broadcast sent to %s channels", broadcast_count)

        # Cleanup
        await manager.shutdown_all()
        logger.info("✅ Communication protocol test completed!")

    parser = argparse.ArgumentParser(description="Agent Communication Protocol Test")
    parser.add_argument("--test", action="store_true", help="Run communication test")

    args = parser.parse_args()

    if args.test:
        asyncio.run(test_communication_protocol())
    else:
        logger.info("Use --test to run the communication protocol test")
