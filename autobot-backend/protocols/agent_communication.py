#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Communication Protocol Standardization

This module defines standardized communication protocols, message formats,
and interaction patterns for inter-agent communication within AutoBot.
"""

import asyncio
import json
import os
import sys
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List

from autobot_shared.logging_manager import get_logger

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from autobot_shared.env_utils import env_int  # noqa: E402
from autobot_shared.error_boundaries import error_boundary  # noqa: E402
from autobot_shared.singleton_factory import lazy_singleton
from constants.threshold_constants import RetryConfig, TimingConstants  # noqa: E402


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


from autobot_shared.async_compat import fire_and_forget, run_or_schedule  # noqa: E402
from protocols.agent_channels import (  # noqa: E402,F401 -- #16986: channels and delivery by recipient live there
    INBOX_MAX_LENGTH,
    CommunicationChannel,
    DirectCommunicationChannel,
    RedisCommunicationChannel,
)
from protocols.agent_kind import AgentKind  # noqa: E402

logger = get_logger(__name__)

#: Most inbound messages one agent handles at once (#16986). The rest wait in a backlog
#: of up to ``INBOX_MAX_LENGTH``, in arrival order; beyond that the newest is dropped.
MAX_INFLIGHT_HANDLERS = env_int("AUTOBOT_AGENT_COMM_MAX_INFLIGHT_HANDLERS", 32)


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
    # #16947: additive shared-identity fields (design on #16946) -- every existing caller is unaffected.
    kind: AgentKind = AgentKind.AI_STACK
    name: str | None = None
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        if self.name is None:
            self.name = self.agent_id


@dataclass
class MessageHeader:
    """Standardized message header"""

    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    message_type: MessageType = MessageType.REQUEST
    priority: MessagePriority = MessagePriority.NORMAL
    sender: AgentIdentity | None = None
    recipient: str | None = None  # Agent ID
    correlation_id: str | None = None  # For request/response correlation
    reply_to: str | None = None  # For response routing
    timestamp: float = field(default_factory=time.time)
    expires_at: float | None = None
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
        self._handling: set = set()  # in-flight inbound messages, one task each (#16986)
        self._backlog: deque = deque()  # inbound messages waiting for a handler slot
        self._dropped = 0  # messages dropped in the current overload, logged once when it starts and ends

    async def start(self):
        """Start the communication protocol"""
        self.is_active = True

        # Start heartbeat
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Start message processor
        self.message_processor_task = asyncio.create_task(self._process_incoming_messages())

        logger.info(f"Agent communication protocol started for " f"{self.agent_identity.agent_id}")

    async def stop(self):
        """Stop the communication protocol"""
        self.is_active = False

        # Cancel background tasks
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.message_processor_task:
            self.message_processor_task.cancel()
        self._backlog.clear()
        for task in list(self._handling):
            task.cancel()
        await asyncio.gather(*self._handling, return_exceptions=True)

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
        """Add a communication channel, as this agent's inbound destination on it (#16986)"""
        channel.bind(self.agent_identity.agent_id)
        self.channels[channel_id] = channel
        logger.info("Added communication channel: %s", channel_id)

    def remove_channel(self, channel_id: str):
        """Remove a communication channel"""
        if channel_id in self.channels:
            channel = self.channels.pop(channel_id)
            fire_and_forget(channel.close(), name="channel-close")
            logger.info("Removed communication channel: %s", channel_id)

    def register_message_handler(
        self,
        message_type: MessageType,
        handler: Callable[[StandardMessage], Awaitable[StandardMessage | None]],
    ):
        """Register a handler for specific message types"""
        if message_type not in self.message_handlers:
            self.message_handlers[message_type] = []
        self.message_handlers[message_type].append(handler)
        logger.info("Registered handler for %s messages", message_type.value)

    async def send_message(self, message: StandardMessage, channel_id: str | None = None) -> bool:
        """Send a message through a specific or default channel"""

        # Set sender information
        message.header.sender = self.agent_identity

        # The named channel, or else the first that can reach the recipient (#16986)
        if channel_id and channel_id not in self.channels:
            logger.error("Channel %s not found", channel_id)
            return False
        candidates = [self.channels[channel_id]] if channel_id else list(self.channels.values())

        @error_boundary(component="agent_communication", function="send_message")
        async def _send():
            """Send message through the candidate channels with error boundary."""
            for channel in candidates:
                if await channel.send(message):
                    return True
            logger.error("No channel reached recipient %r", message.header.recipient)
            return False

        return await _send()

    async def send_request(
        self,
        request: StandardMessage,
        timeout: float = TimingConstants.SHORT_TIMEOUT,
        channel_id: str | None = None,
    ) -> StandardMessage | None:
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
        channel_id: str | None = None,
    ) -> bool:
        """Send a response to a request"""

        response.header.message_type = MessageType.RESPONSE
        response.header.correlation_id = original_request.header.correlation_id
        response.header.recipient = original_request.header.reply_to

        return await self.send_message(response, channel_id)

    async def broadcast(self, message: StandardMessage) -> int:
        """Broadcast a message to all channels"""

        message.header.message_type = MessageType.BROADCAST
        recipients = set()
        for channel in self.channels.values():
            recipients |= await channel.recipients()
        recipients.discard(self.agent_identity.agent_id)  # #16986: never to the sender itself

        sent_count = 0
        for recipient in sorted(recipients):
            copy = replace(message, header=replace(message.header, recipient=recipient))
            if await self.send_message(copy):
                sent_count += 1
        logger.info("Broadcasted message to %s/%s recipients", sent_count, len(recipients))
        return sent_count

    async def _dispatch(self, message: StandardMessage, channel_id: str) -> None:
        """Handle *message* in its own task, at most ``MAX_INFLIGHT_HANDLERS`` at once (#16986).

        Awaited inline, a handler that sends its own request (B forwarding A's to C)
        blocked the loop that must hand it C's reply. So this never makes the loop wait.
        A reply resolves its request at once, without a slot. Anything else starts a
        handler if a slot is free, or joins a bounded backlog, or past that is dropped;
        a dropped request is answered with an error at once rather than left to time out.
        Waiting for a slot in the loop would bring the deadlock back: the replies the
        busy handlers need would queue behind the message waiting for their slot.
        """
        if not self._addressed_here(message) or self._resolve_reply(message):
            return
        if len(self._handling) < MAX_INFLIGHT_HANDLERS:
            self._start(message, channel_id)
        elif len(self._backlog) < INBOX_MAX_LENGTH:
            if not self._backlog:
                logger.warning(
                    "Agent %s is handling %d messages; queueing more",
                    self.agent_identity.agent_id,
                    MAX_INFLIGHT_HANDLERS,
                )
            self._backlog.append((message, channel_id))
        else:
            await self._drop(message, channel_id)

    async def _drop(self, message: StandardMessage, channel_id: str) -> None:
        """Shed *message*: one warning per overload, and an immediate error to a waiting requester."""
        if not self._dropped:
            logger.warning(
                "Agent %s is overloaded (%d handling, %d queued); dropping until it drains",
                self.agent_identity.agent_id,
                len(self._handling),
                len(self._backlog),
            )
        self._dropped += 1
        if message.header.message_type == MessageType.REQUEST:
            await self.send_response(self._error_reply(message, "Agent overloaded", "Overloaded"), message, channel_id)

    def _start(self, message: StandardMessage, channel_id: str) -> None:
        task = asyncio.create_task(self._handle_message(message, channel_id))
        self._handling.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task) -> None:
        """A handler ended: free its slot for the oldest waiting message."""
        self._handling.discard(task)
        if self._backlog and self.is_active:
            self._start(*self._backlog.popleft())
        if self._dropped and not self._backlog:
            logger.warning("Agent %s drained; %d messages were dropped", self.agent_identity.agent_id, self._dropped)
            self._dropped = 0

    async def _process_incoming_messages(self):
        """Background task to process incoming messages from all channels"""
        while self.is_active:
            try:
                # Check all channels for incoming messages (Issue #376 - use constants)
                for channel_id, channel in list(self.channels.items()):
                    try:
                        message = await channel.receive(timeout=TimingConstants.MICRO_DELAY)
                        if message:
                            await self._dispatch(message, channel_id)
                    except Exception as e:
                        logger.error(f"Error processing message from channel {channel_id}: {e}")

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
        logger.debug("Received %s message: %s", message.header.message_type.value, message.header.message_id)
        if not self._addressed_here(message) or self._resolve_reply(message):
            return
        try:
            await self._run_handlers(message, channel_id)
        except Exception as e:
            logger.error("Error handling message %s: %s", message.header.message_id, e)

    def _addressed_here(self, message: StandardMessage) -> bool:
        """False, with a log line naming both ids, for a message addressed to another agent (#16986)."""
        recipient, own = message.header.recipient, self.agent_identity.agent_id
        if recipient and recipient != own:
            logger.warning(
                "Dropped message %s addressed to %r, received by %r", message.header.message_id, recipient, own
            )
            return False
        return True

    def _resolve_reply(self, message: StandardMessage) -> bool:
        """Hand a reply to the request waiting for it. True if *message* was that reply."""
        if message.header.message_type != MessageType.RESPONSE:
            return False
        future = self.pending_requests.get(message.header.correlation_id)
        if future is None:
            return False
        if not future.done():
            future.set_result(message)
        return True

    async def _run_handlers(self, message: StandardMessage, channel_id: str) -> None:
        """Run every handler registered for the message's type; answer a request with each result or error."""
        is_request = message.header.message_type == MessageType.REQUEST
        for handler in self.message_handlers.get(message.header.message_type, []):
            try:
                response = await handler(message)
                if response and is_request:
                    await self.send_response(response, message, channel_id)
            except Exception as e:
                logger.error("Error in message handler: %s", e)
                if is_request:
                    error = self._error_reply(message, "Message handling failed", type(e).__name__)
                    await self.send_response(error, message, channel_id)

    @staticmethod
    def _error_reply(message: StandardMessage, error: str, error_type: str) -> StandardMessage:
        """An error answer to *message*, correlated so its requester stops waiting."""
        return StandardMessage(
            header=MessageHeader(message_type=MessageType.ERROR, correlation_id=message.header.correlation_id),
            payload=MessagePayload(content={"error": error, "error_type": error_type}),
        )

    async def _heartbeat_loop(self):
        """Keep this agent reachable: refresh its registration on every channel (#16986).

        This used to broadcast a HEARTBEAT that no handler consumed; it looped back to
        the sender. Now that a broadcast reaches every agent, it would be all-to-all
        traffic for nobody. Liveness is what routing needs, so the heartbeat renews it.
        """
        while self.is_active:
            try:
                self.agent_identity.last_heartbeat = time.time()
                for channel in self.channels.values():
                    await channel.refresh()

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

        try:
            await self._open_channels(protocol, channel_configs)
        except Exception:
            for channel in protocol.channels.values():  # #16986: a refused channel leaves nothing bound
                await channel.close()
            raise

        # Start the protocol
        await protocol.start()

        # Register in manager
        self.protocols[agent_identity.agent_id] = protocol

        logger.info(f"Registered agent communication protocol: " f"{agent_identity.agent_id}")
        return protocol

    async def _open_channels(self, protocol: AgentCommunicationProtocol, channel_configs: List[Dict[str, Any]]) -> None:
        """Create, bind and start each configured channel. Raises if one refuses its owner."""
        for config in channel_configs:
            channel_type = config.get("type", "direct")
            channel_id = config.get("id", f"{protocol.agent_identity.agent_id}_{channel_type}")
            if channel_type not in self.channel_factory:
                logger.error("Unknown channel type: %s", channel_type)
                continue
            channel = self.channel_factory[channel_type](channel_id)
            protocol.add_channel(channel_id, channel)  # bound first: a Redis channel reads its owner's inbox
            if isinstance(channel, RedisCommunicationChannel):
                await channel.start()

    async def unregister_agent(self, agent_id: str):
        """Unregister an agent's communication protocol"""
        if agent_id in self.protocols:
            protocol = self.protocols.pop(agent_id)
            await protocol.stop()
            logger.info("Unregistered agent communication protocol: %s", agent_id)

    def get_protocol(self, agent_id: str) -> AgentCommunicationProtocol | None:
        """Get communication protocol for an agent"""
        return self.protocols.get(agent_id)

    async def shutdown_all(self):
        """Shutdown all agent communication protocols"""
        for agent_id in list(self.protocols.keys()):
            await self.unregister_agent(agent_id)
        logger.info("All agent communication protocols shutdown")


get_communication_manager = lazy_singleton(AgentCommunicationManager)


# Utility functions for common communication patterns


async def send_agent_request(
    sender_id: str,
    recipient_id: str,
    request_data: Any,
    timeout: float = TimingConstants.SHORT_TIMEOUT,
) -> Any | None:
    """Send a request from one agent to another"""

    manager = get_communication_manager()
    sender_protocol = manager.get_protocol(sender_id)

    if not sender_protocol:
        logger.error("Sender agent %s not registered", sender_id)
        return None

    request = StandardMessage(
        header=MessageHeader(message_type=MessageType.REQUEST, recipient=recipient_id),
        payload=MessagePayload(content=request_data),
    )

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

        agent1_identity = AgentIdentity(agent_id="test_agent_1", agent_type="test", capabilities=["test", "demo"])

        agent2_identity = AgentIdentity(agent_id="test_agent_2", agent_type="test", capabilities=["test", "demo"])

        await manager.register_agent(agent1_identity, [{"type": "direct"}])
        protocol2 = await manager.register_agent(agent2_identity, [{"type": "direct"}])

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

        await manager.shutdown_all()
        logger.info("✅ Communication protocol test completed!")

    parser = argparse.ArgumentParser(description="Agent Communication Protocol Test")
    parser.add_argument("--test", action="store_true", help="Run communication test")

    args = parser.parse_args()

    if args.test:
        run_or_schedule(test_communication_protocol())
    else:
        logger.info("Use --test to run the communication protocol test")
