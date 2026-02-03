# Agent Communication Protocol Documentation

## Overview

The Agent Communication Protocol provides a standardized messaging system for inter-agent communication within the AutoBot ecosystem, supporting both direct and Redis-based message routing.

## Architecture

### Communication Channels

The protocol supports multiple communication channels:

1. **Direct Channel**: In-memory message passing for local agents
2. **Redis Channel**: Distributed messaging for remote agents
3. **Broadcast Channel**: Multi-cast messaging for system-wide announcements

### Message Format

All messages follow a standardized JSON format:

```json
{
  "header": {
    "message_id": "uuid",
    "message_type": "REQUEST|RESPONSE|BROADCAST|NOTIFICATION",
    "priority": "LOW|NORMAL|HIGH|URGENT",
    "sender_id": "agent_id",
    "recipient_id": "agent_id",
    "correlation_id": "uuid",
    "timestamp": "2025-08-20T08:45:00Z",
    "ttl": 300
  },
  "payload": {
    "action": "string",
    "data": {},
    "context": {},
    "metadata": {}
  }
}
```

## Message Types

### REQUEST
Used for agent-to-agent service requests:
```json
{
  "header": {
    "message_type": "REQUEST",
    "priority": "NORMAL",
    "sender_id": "client_agent",
    "recipient_id": "service_agent"
  },
  "payload": {
    "action": "process_data",
    "data": {"input": "value"},
    "context": {"request_id": "123"}
  }
}
```

### RESPONSE
Response to a REQUEST message:
```json
{
  "header": {
    "message_type": "RESPONSE",
    "priority": "NORMAL",
    "sender_id": "service_agent",
    "recipient_id": "client_agent",
    "correlation_id": "original_request_id"
  },
  "payload": {
    "action": "process_data_result",
    "data": {"result": "processed_value"},
    "status": "SUCCESS|ERROR|PARTIAL"
  }
}
```

### BROADCAST
System-wide announcements:
```json
{
  "header": {
    "message_type": "BROADCAST",
    "priority": "HIGH",
    "sender_id": "system_agent"
  },
  "payload": {
    "action": "system_shutdown",
    "data": {"reason": "maintenance", "grace_period": 300}
  }
}
```

### NOTIFICATION
Asynchronous notifications:
```json
{
  "header": {
    "message_type": "NOTIFICATION",
    "priority": "LOW",
    "sender_id": "monitoring_agent",
    "recipient_id": "admin_agent"
  },
  "payload": {
    "action": "status_update",
    "data": {"metric": "cpu_usage", "value": 85.2}
  }
}
```

## Priority Levels

### URGENT (4)
- System critical messages
- Security alerts
- Emergency shutdowns

### HIGH (3)
- Important operational messages
- Error notifications
- Performance warnings

### NORMAL (2)
- Standard requests and responses
- Regular status updates
- Data processing requests

### LOW (1)
- Debug information
- Metrics collection
- Background tasks

## Agent Registration

### Registering an Agent

```python
from src.protocols.agent_communication import AgentCommunicationProtocol

# Create agent communication
protocol = AgentCommunicationProtocol(
    agent_id="my_agent_123",
    agent_type="processing_agent"
)

# Start the protocol
await protocol.start()

# Register message handlers
@protocol.message_handler("process_request")
async def handle_process_request(message: AgentMessage) -> AgentMessage:
    # Process the request
    result = await process_data(message.payload.data)

    # Return response
    return AgentMessage.create_response(
        original_message=message,
        action="process_result",
        data=result
    )
```

### Agent Discovery

```python
# Find agents by type
processing_agents = await protocol.discover_agents("processing_agent")

# Find specific agent
target_agent = await protocol.find_agent("specific_agent_id")

# Get all active agents
all_agents = await protocol.get_active_agents()
```

## Message Routing

### Direct Messaging

```python
# Send direct message
response = await protocol.send_message(
    recipient_id="target_agent",
    action="process_data",
    data={"input": "value"},
    priority=MessagePriority.NORMAL,
    timeout=30.0
)
```

### Broadcast Messaging

```python
# Send broadcast to all agents
await protocol.broadcast_message(
    action="system_notification",
    data={"message": "System maintenance in 5 minutes"},
    priority=MessagePriority.HIGH
)

# Send broadcast to specific agent types
await protocol.broadcast_to_type(
    agent_type="processing_agent",
    action="pause_processing",
    data={}
)
```

### Redis-based Messaging

The protocol automatically uses Redis for distributed messaging when available:

```python
# Redis configuration
redis_config = {
    "host": "localhost",
    "port": 6379,
    "db": 0,
    "channel_prefix": "autobot_agents"
}

# Initialize with Redis support
protocol = AgentCommunicationProtocol(
    agent_id="distributed_agent",
    redis_config=redis_config
)
```

## Error Handling

### Message Delivery Failures

The protocol implements automatic retry and fallback mechanisms:

```python
# Configure retry behavior
protocol.configure_delivery(
    max_retries=3,
    retry_delay=1.0,
    exponential_backoff=True,
    fallback_to_direct=True
)
```

### Error Response Format

```json
{
  "header": {
    "message_type": "RESPONSE",
    "priority": "HIGH",
    "correlation_id": "failed_request_id"
  },
  "payload": {
    "action": "error_response",
    "status": "ERROR",
    "error": {
      "code": "PROCESSING_FAILED",
      "message": "Unable to process request",
      "details": {"reason": "Invalid input format"}
    }
  }
}
```

## Security Features

### Message Validation

All messages are validated before processing:

```python
class MessageValidator:
    def validate_message(self, message: AgentMessage) -> bool:
        # Check required fields
        if not message.header.message_id:
            return False

        # Validate message type
        if message.header.message_type not in MessageType:
            return False

        # Check priority level
        if message.header.priority not in MessagePriority:
            return False

        return True
```

### Agent Authentication

Agents must authenticate before joining the communication network:

```python
# Agent authentication  # pragma: allowlist secret
credentials = {
    "agent_id": "secure_agent",
    "api_key": "secure_key_123",  # pragma: allowlist secret
    "capabilities": ["data_processing", "file_access"]
}

authenticated = await protocol.authenticate(credentials)
if not authenticated:
    raise SecurityError("Agent authentication failed")
```

### Message Encryption

For sensitive communications, messages can be encrypted:

```python
# Enable encryption for specific message types
protocol.enable_encryption(
    message_types=[MessageType.REQUEST, MessageType.RESPONSE],
    encryption_key="your_encryption_key"
)
```

## Performance Monitoring

### Message Metrics

The protocol collects performance metrics:

```python
# Get protocol statistics
stats = protocol.get_statistics()
print(f"Messages sent: {stats.messages_sent}")
print(f"Messages received: {stats.messages_received}")
print(f"Average response time: {stats.avg_response_time}ms")
print(f"Failed deliveries: {stats.delivery_failures}")
```

### Performance Optimization

```python
# Configure performance settings
protocol.configure_performance(
    message_buffer_size=1000,
    batch_processing=True,
    compression_enabled=True,
    keep_alive_interval=30
)
```

## Protocol Implementation

### Core Classes

#### AgentMessage
```python
@dataclass
class AgentMessage:
    header: MessageHeader
    payload: MessagePayload

    @classmethod
    def create_request(cls, recipient_id: str, action: str,
                      data: dict, priority: MessagePriority = MessagePriority.NORMAL):
        return cls(
            header=MessageHeader(
                message_type=MessageType.REQUEST,
                recipient_id=recipient_id,
                priority=priority
            ),
            payload=MessagePayload(action=action, data=data)
        )
```

#### MessageRouter
```python
class MessageRouter:
    def __init__(self):
        self.routes = {}
        self.handlers = {}

    async def route_message(self, message: AgentMessage):
        # Determine routing strategy
        if message.header.message_type == MessageType.BROADCAST:
            await self._broadcast_message(message)
        else:
            await self._direct_message(message)

    async def _direct_message(self, message: AgentMessage):
        recipient = message.header.recipient_id
        if recipient in self.routes:
            await self.routes[recipient].handle_message(message)
```

### Channel Management

#### DirectChannel
```python
class DirectChannel:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.message_queue = asyncio.Queue()

    async def send_message(self, message: AgentMessage):
        await self.message_queue.put(message)

    async def receive_message(self) -> AgentMessage:
        return await self.message_queue.get()
```

#### RedisChannel
```python
class RedisChannel:
    def __init__(self, agent_id: str, redis_client):
        self.agent_id = agent_id
        self.redis_client = redis_client
        self.channel_key = f"agent_channel:{agent_id}"

    async def send_message(self, message: AgentMessage):
        message_data = json.dumps(message.to_dict())
        await asyncio.to_thread(
            self.redis_client.lpush,
            self.channel_key,
            message_data
        )

    async def receive_message(self) -> AgentMessage:
        result = await asyncio.to_thread(
            self.redis_client.brpop,
            self.channel_key,
            timeout=1
        )
        if result:
            _, message_data = result
            return AgentMessage.from_dict(json.loads(message_data))
```

## Usage Examples

### Simple Agent Communication

```python
# Agent A - Sender
async def sender_agent():
    protocol = AgentCommunicationProtocol("agent_a")
    await protocol.start()

    # Send request
    response = await protocol.send_message(
        recipient_id="agent_b",
        action="calculate",
        data={"x": 10, "y": 20, "operation": "add"}
    )

    print(f"Result: {response.payload.data['result']}")

# Agent B - Receiver
async def receiver_agent():
    protocol = AgentCommunicationProtocol("agent_b")
    await protocol.start()

    @protocol.message_handler("calculate")
    async def handle_calculate(message):
        data = message.payload.data
        result = data["x"] + data["y"] if data["operation"] == "add" else 0

        return AgentMessage.create_response(
            original_message=message,
            action="calculate_result",
            data={"result": result}
        )
```

### Distributed Processing

```python
async def distributed_processing_example():
    # Master agent
    master = AgentCommunicationProtocol("master_agent")
    await master.start()

    # Find worker agents
    workers = await master.discover_agents("worker_agent")

    # Distribute work
    tasks = [{"data": f"task_{i}"} for i in range(100)]
    results = []

    for i, task in enumerate(tasks):
        worker_id = workers[i % len(workers)]
        response = await master.send_message(
            recipient_id=worker_id,
            action="process_task",
            data=task
        )
        results.append(response.payload.data)

    print(f"Processed {len(results)} tasks")
```

## Troubleshooting

### Common Issues

#### 1. Message Type Parsing Errors
```python
# Problem: MessageType.BROADCAST is not a valid MessageType
# Solution: Proper enum parsing
def parse_message_type(value):
    if isinstance(value, str) and value.startswith('MessageType.'):
        value = value.split('.')[-1].lower()
    return MessageType(value)
```

#### 2. Redis Connection Issues
```python
# Check Redis connectivity
async def check_redis_connection():
    try:
        await asyncio.to_thread(redis_client.ping)
        return True
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        return False
```

#### 3. Message Delivery Timeouts
```python
# Configure appropriate timeouts
protocol.configure_timeouts(
    send_timeout=10.0,
    receive_timeout=30.0,
    response_timeout=60.0
)
```

### Debug Logging

```python
import logging

# Enable debug logging
logging.getLogger('agent_communication').setLevel(logging.DEBUG)

# Log message flow
logger.debug(f"Sending message: {message.header.message_id}")
logger.debug(f"Message route: {sender_id} -> {recipient_id}")
logger.debug(f"Message payload: {message.payload.action}")
```

## Future Enhancements

### Planned Features

1. **Message Persistence**: Store messages for offline agents
2. **Load Balancing**: Distribute messages across agent instances
3. **Circuit Breaker**: Prevent cascade failures
4. **Message Compression**: Reduce network overhead
5. **Monitoring Dashboard**: Real-time communication metrics

### Protocol Versioning

The protocol supports versioning for backward compatibility:

```python
# Version 2.0 features
protocol = AgentCommunicationProtocol(
    agent_id="modern_agent",
    protocol_version="2.0",
    features=["compression", "encryption", "batching"]
)
```

## Configuration

### Environment Variables

```bash
# Redis configuration
AGENT_REDIS_HOST=localhost
AGENT_REDIS_PORT=6379
AGENT_REDIS_DB=0

# Protocol settings
AGENT_MESSAGE_TTL=300
AGENT_MAX_RETRIES=3
AGENT_TIMEOUT=30

# Security settings
AGENT_ENCRYPTION_ENABLED=true
AGENT_AUTH_REQUIRED=false
```

### Configuration File

```yaml
# agent_communication.yaml
protocol:
  version: "1.0"
  timeout: 30
  max_retries: 3

redis:
  host: localhost
  port: 6379
  db: 0
  channel_prefix: "autobot_agents"

security:
  encryption_enabled: false
  auth_required: false
  allowed_agents: []

performance:
  batch_size: 100
  compression: true
  keep_alive: 30
```

This protocol ensures reliable, scalable communication between agents while maintaining security and performance standards.
