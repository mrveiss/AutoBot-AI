# AutoBot SDK

Official SDK packages for integrating with the AutoBot API.

---

## Available SDKs

| Language | Package | Status | Guide |
|----------|---------|--------|-------|
| Python | `autobot-sdk` | Planned | [Python Quickstart](python-quickstart.md) |
| TypeScript | `@autobot/sdk` | Planned | [TypeScript Quickstart](typescript-quickstart.md) |

---

## Quick Comparison

### Python

```python
from autobot_sdk import AutoBotClient

client = AutoBotClient(
    base_url="https://autobot.example.com:8443",
    api_key="your-api-key",
)

response = client.chat.send("How do I scan a network?")
print(response.content)
```

### TypeScript

```typescript
import { AutoBotClient } from '@autobot/sdk';

const client = new AutoBotClient({
  baseUrl: 'https://autobot.example.com:8443',
  apiKey: 'your-api-key',
});

const response = await client.chat.send('How do I scan a network?');
console.log(response.content);
```

---

## Core Concepts

### Authentication

All SDK clients require either an API key or JWT credentials. API keys are the recommended approach for server-to-server integrations:

```python
# API key (recommended for server-to-server)
client = AutoBotClient(api_key="ak_...")

# JWT credentials (for user-context operations)
client = AutoBotClient(username="user", password="pass")
```

### Sessions

Chat interactions are organized into sessions. You can create a session explicitly or let the SDK create one automatically:

```python
# Automatic session
response = client.chat.send("Hello")

# Explicit session
session = client.chat.create_session(title="My Project")
response = session.send("Hello")
```

### Streaming

All chat and agent endpoints support streaming responses:

```python
for chunk in client.chat.stream("Explain network scanning"):
    print(chunk.content, end="", flush=True)
```

### Error Handling

SDKs raise typed exceptions that map to HTTP status codes:

```python
from autobot_sdk.exceptions import (
    AuthenticationError,   # 401
    PermissionError,       # 403
    NotFoundError,         # 404
    RateLimitError,        # 429
    AutoBotAPIError,       # 500+
)
```

---

## API Reference

For the complete API reference with all endpoints, request/response schemas, and examples, see:

- [Public API Reference](../api/public-api-reference.md)
- [API Versioning Strategy](../api/api-versioning.md)

---

## Feature Coverage

| Feature | Python | TypeScript |
|---------|--------|------------|
| Chat (send/stream) | Yes | Yes |
| Chat sessions | Yes | Yes |
| Knowledge base CRUD | Yes | Yes |
| Knowledge search/query | Yes | Yes |
| Collections | Yes | Yes |
| Agent invocation | Yes | Yes |
| Multi-agent coordination | Yes | Yes |
| Workflow execution | Yes | Yes |
| Model listing | Yes | Yes |
| Voice (TTS/STT) | Yes | Planned |
| Multimodal processing | Yes | Planned |
| File upload | Yes | Yes |
| WebSocket streaming | Yes | Planned |

---

## Contributing

SDK source code will be published to separate repositories:

- `github.com/mrveiss/autobot-python-sdk`
- `github.com/mrveiss/autobot-typescript-sdk`

Contributions are welcome. See each repository's CONTRIBUTING.md for guidelines.
