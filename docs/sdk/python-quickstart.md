# Python SDK Quickstart

This guide shows how to integrate with AutoBot from Python. It has two halves,
and which one you want depends on the endpoint:

1. **The SDK.** `autobot_sdk` covers sessions, agents, the knowledge base and
   analytics. Every URL it builds and every body it sends is pinned against the
   backend's own route table and request models by the guards in `repo_tests/`,
   so those calls cannot drift from the API without a test going red. Use it for
   anything it covers.
2. **Raw HTTP.** The SDK has four resources; the API has many more. Chat,
   streaming, workflows, models, collections and file upload have no SDK method
   at all, so this guide shows them as direct `httpx` calls. Those snippets carry
   no guarantee beyond `repo_tests/sdk_docs_paths_test.py` checking that each
   path names a route the backend serves.

---

## Installation

### The SDK

`autobot-sdk` is **not published to PyPI yet**. It is checked in at
`libs/autobot-sdk-python` and is installed from there:

```bash
pip install ./libs/autobot-sdk-python
```

Its only dependencies are `httpx` and `pydantic`.

### Direct HTTP

For the endpoints the SDK does not cover:

```bash
pip install httpx
```

---

## Using the SDK

The client is **async only**: `AutoBot` is an async context manager and every
resource method is a coroutine. `AutoBotClient` is the HTTP base class and has no
resource namespaces — `AutoBot` is the one you want.

```python
import asyncio
import os

from autobot_sdk import AutoBot


async def main():
    async with AutoBot(
        base_url="https://autobot.example.com:8443",
        token=os.environ["AUTOBOT_API_TOKEN"],
    ) as bot:
        ...


asyncio.run(main())
```

`base_url` is the backend origin; the client adds the `/api` root itself. Omit it
and the origin comes from `AUTOBOT_BASE_URL`, or from `AUTOBOT_BACKEND_HOST` and
`AUTOBOT_BACKEND_PORT`. Omit `token` and it comes from `AUTOBOT_API_TOKEN`.

### Sessions

```python
created = await bot.sessions.create(title="Security Research")
session_id = created.data.id

# scope is "user" (the default), "org", "team" or "shared";
# team_id is required when scope="team". The route is not paginated.
listed = await bot.sessions.list(scope="user")

# The message history, page by page.
messages = await bot.sessions.get(session_id, page=1, per_page=50)

await bot.sessions.update(session_id, title="Renamed")
await bot.sessions.delete(session_id)
```

### Knowledge base

```python
stats = await bot.knowledge.stats()

await bot.knowledge.add_text(
    "AutoBot supports Intel NPU acceleration for local AI inference.",
    category="hardware",
    source="handbook",
)

results = await bot.knowledge.search("How does NPU acceleration work?", limit=3)

# Cursor pagination: pass the previous page's next_cursor to advance.
page = await bot.knowledge.get_entries(limit=50, category="hardware")
if page.has_more:
    page = await bot.knowledge.get_entries(limit=50, cursor=page.next_cursor)
```

### Agents

```python
health = await bot.agents.health()
config = await bot.agents.get_config("research")
await bot.agents.set_model("research", "llama3", provider="ollama")
await bot.agents.set_enabled("research", True)
```

`bot.agents.send_command(...)` exists but cannot succeed: its route,
`POST /api/agent/execute_command`, declares a `dict` body parameter alongside a
`Form` field, so FastAPI publishes it as form-encoded while requiring a field
that can only arrive as JSON. Every candidate body answers 422. Do not build on
it until the route is fixed.

### Analytics

```python
usage = await bot.analytics.usage()
performance = await bot.analytics.performance()
```

Neither route takes a time window — both report over the collector's own.

### Errors

The SDK calls `raise_for_status()` and does not translate, so failures surface as
`httpx.HTTPStatusError`. There is no `autobot_sdk.exceptions` module.

```python
import httpx

try:
    stats = await bot.knowledge.stats()
except httpx.HTTPStatusError as exc:
    print(exc.response.status_code, exc.response.text)
```

---

# Direct HTTP

Everything below calls the API without the SDK, because none of these endpoints
has an SDK method. The paths are checked against the backend route table by
`repo_tests/sdk_docs_paths_test.py`, but the request and response shapes are not
guarded the way the SDK's are — read the
[Public API Reference](../api/public-api-reference.md) alongside them.

---

## Configuration

```python
import httpx

BASE_URL = "https://autobot.example.com:8443/api"
API_KEY = "your-api-key"

# Shared client with authentication
client = httpx.Client(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {API_KEY}"},
    timeout=30.0,
    verify=True,  # Set to False for self-signed certs in dev
)
```

For async usage:

```python
async_client = httpx.AsyncClient(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {API_KEY}"},
    timeout=30.0,
)
```

---

## Authentication

### Login with credentials

```python
def login(username: str, password: str) -> str:
    """Authenticate and return a JWT token."""
    response = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    return response.json()["token"]

token = login("myuser", "mypassword")
client = httpx.Client(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {token}"},
    timeout=30.0,
)
```

---

## Chat

### Send a message

```python
def send_message(content: str, session_id: str = None) -> dict:
    """Send a chat message and get a response."""
    payload = {"content": content, "role": "user"}
    if session_id:
        payload["session_id"] = session_id

    response = client.post("/chat", json=payload)
    response.raise_for_status()
    return response.json()

result = send_message("How do I configure network scanning?")
print(result["response"])
```

### Stream a response

```python
def stream_message(content: str, session_id: str = None):
    """Send a message and stream the response token by token."""
    payload = {"content": content, "role": "user"}
    if session_id:
        payload["session_id"] = session_id

    with client.stream("POST", "/chat/stream", json=payload) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith("data: "):
                import json
                data = json.loads(line[6:])
                if data.get("type") == "token":
                    print(data["content"], end="", flush=True)
                elif data.get("type") == "done":
                    print()  # newline after stream
                    return data

stream_message("Explain NPU acceleration in detail")
```

### Manage sessions

```python
def create_session(title: str = "New conversation") -> dict:
    """Create a new chat session."""
    response = client.post("/chat/sessions", json={"title": title})
    response.raise_for_status()
    return response.json()

def list_sessions() -> dict:
    """List chat sessions.

    ``GET /api/chats`` (``list_chats``) declares no query parameters at all, so a
    ``limit`` would be dropped by FastAPI and the caller's paging would silently
    not apply. It returns the caller's whole list; slice the result instead.
    """
    response = client.get("/chats")
    response.raise_for_status()
    return response.json()

def get_session(session_id: str) -> dict:
    """Get a session with message history."""
    response = client.get(f"/chat/sessions/{session_id}")
    response.raise_for_status()
    return response.json()

def delete_session(session_id: str) -> dict:
    """Delete a chat session."""
    response = client.delete(f"/chats/{session_id}")
    response.raise_for_status()
    return response.json()

# Usage
session = create_session("Security Research")
session_id = session["session_id"]

# Send messages within the session
send_message("What are the OWASP top 10?", session_id=session_id)
history = get_session(session_id)
```

---

## Knowledge Base

### Add content

```python
def add_fact(content: str, title: str = "", category: str = "general",
             tags: list = None) -> dict:
    """Add text content to the knowledge base."""
    response = client.post("/knowledge_base/facts", json={
        "content": content,
        "title": title,
        "category": category,
        "tags": tags or [],
    })
    response.raise_for_status()
    return response.json()

add_fact(
    content="AutoBot supports Intel NPU acceleration for local AI inference.",
    title="NPU Support",
    category="hardware",
    tags=["npu", "intel", "acceleration"],
)
```

### Upload a document

```python
from pathlib import Path

def upload_document(file_path: str, category: str = "general") -> dict:
    """Upload a document file to the knowledge base."""
    path = Path(file_path)
    with open(path, "rb") as f:
        response = client.post(
            "/knowledge_base/upload",
            files={"file": (path.name, f)},
            data={"category": category},
        )
    response.raise_for_status()
    return response.json()

result = upload_document("docs/architecture.pdf", category="architecture")
print(f"Created {result['chunks_created']} chunks")
```

### Add content from URL

```python
def add_url(url: str, title: str = "", category: str = "web") -> dict:
    """Add content from a URL to the knowledge base."""
    response = client.post("/knowledge_base/url", json={
        "url": url,
        "title": title,
        "category": category,
    })
    response.raise_for_status()
    return response.json()

add_url("https://example.com/security-guide", title="Security Guide")
```

### Query the knowledge base

```python
def query_knowledge(query: str, top_k: int = 5,
                    category: str = None) -> dict:
    """Query the knowledge base."""
    payload = {"query": query, "top_k": top_k}
    if category:
        payload["category"] = category

    response = client.post("/knowledge_base/query", json=payload)
    response.raise_for_status()
    return response.json()

results = query_knowledge("How does NPU acceleration work?", top_k=3)
for result in results.get("results", []):
    print(f"[{result['score']:.2f}] {result['content'][:100]}...")
```

### Search with filters

```python
def search_knowledge(query: str, search_type: str = "hybrid",
                     categories: list = None, tags: list = None,
                     top_k: int = 10) -> dict:
    """Search with advanced filtering."""
    payload = {
        "query": query,
        "search_type": search_type,
        "top_k": top_k,
        "filters": {},
    }
    if categories:
        payload["filters"]["categories"] = categories
    if tags:
        payload["filters"]["tags"] = tags

    response = client.post("/knowledge_base/search", json=payload)
    response.raise_for_status()
    return response.json()

results = search_knowledge(
    "network scanning tools",
    categories=["security", "tools"],
    tags=["network"],
)
```

### Collections

```python
def create_collection(name: str, description: str = "") -> dict:
    """Create a knowledge base collection."""
    response = client.post("/knowledge_base/collections", json={
        "name": name,
        "description": description,
    })
    response.raise_for_status()
    return response.json()

def list_collections() -> dict:
    """List all collections."""
    response = client.get("/knowledge_base/collections")
    response.raise_for_status()
    return response.json()

collection = create_collection("Security Playbooks", "Automation playbooks for security")
```

---

## Agents

### List available agents

```python
def list_agents() -> dict:
    """List available agents and their capabilities."""
    response = client.get("/agent/agents/available")
    response.raise_for_status()
    return response.json()

agents = list_agents()
for agent in agents.get("agents", []):
    print(f"{agent['name']}: {agent['description']}")
```

### Execute an agent goal

```python
def execute_goal(goal: str, agent: str = "research") -> dict:
    """Execute an agent goal."""
    response = client.post("/agent/goal", json={
        "goal": goal,
        "agent": agent,
    })
    response.raise_for_status()
    return response.json()

result = execute_goal(
    "Research the latest network vulnerability disclosures",
    agent="research",
)
print(f"Task ID: {result['task_id']}, Status: {result['status']}")
```

### Multi-agent coordination

```python
def coordinate_agents(task: str, agents: list,
                      mode: str = "sequential") -> dict:
    """Coordinate multiple agents on a task."""
    response = client.post("/agent/multi-agent/coordinate", json={
        "task": task,
        "agents": agents,
        "coordination_mode": mode,
    })
    response.raise_for_status()
    return response.json()

result = coordinate_agents(
    task="Research and document network scanning best practices",
    agents=["research", "rag", "knowledge_extraction"],
)
```

---

## Workflows

### Trigger a workflow

```python
def execute_workflow(workflow_type: str, parameters: dict = None) -> dict:
    """Trigger a workflow execution."""
    response = client.post("/workflow/execute", json={
        "workflow_type": workflow_type,
        "parameters": parameters or {},
    })
    response.raise_for_status()
    return response.json()

workflow = execute_workflow(
    "research_and_document",
    parameters={"topic": "Zero trust architecture", "output_format": "report"},
)
workflow_id = workflow["workflow_id"]
```

### Check workflow status

```python
import time

def wait_for_workflow(workflow_id: str, poll_interval: int = 5,
                      timeout: int = 300) -> dict:
    """Poll workflow status until completion or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        response = client.get(f"/workflow/workflow/{workflow_id}/status")
        response.raise_for_status()
        status = response.json()

        if status["status"] in ("completed", "failed", "cancelled"):
            return status

        print(f"Progress: {status.get('progress', 0):.0%} "
              f"(step {status.get('current_step')}/{status.get('total_steps')})")
        time.sleep(poll_interval)

    raise TimeoutError(f"Workflow {workflow_id} did not complete within {timeout}s")

final_status = wait_for_workflow(workflow_id)
print(f"Workflow finished: {final_status['status']}")
```

### Get workflow details

```python
def get_workflow(workflow_id: str) -> dict:
    """Get full workflow details including step results."""
    response = client.get(f"/workflow/workflow/{workflow_id}")
    response.raise_for_status()
    return response.json()

details = get_workflow(workflow_id)
for step in details["workflow"]["steps"]:
    print(f"Step {step['step']}: {step['agent']} - {step['status']}")
```

---

## Models

### List available models

```python
def list_models() -> dict:
    """List available LLM models."""
    response = client.get("/llm/models")
    response.raise_for_status()
    return response.json()

models = list_models()
for model in models.get("models", []):
    status = "available" if model.get("available") else "unavailable"
    print(f"{model['name']} ({model['provider']}) - {status}")
```

### Get current model

```python
def get_current_model() -> dict:
    """Get the currently active model."""
    response = client.get("/llm/current")
    response.raise_for_status()
    return response.json()
```

---

## Async Usage

All examples above work with `httpx.AsyncClient` for async/await patterns:

```python
import asyncio
import httpx

async def main():
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=30.0,
    ) as client:
        # Send a chat message
        response = await client.post("/chat", json={
            "content": "What is AutoBot?",
            "role": "user",
        })
        result = response.json()
        print(result["response"])

        # Query knowledge base
        response = await client.post("/knowledge_base/query", json={
            "query": "NPU acceleration",
            "top_k": 3,
        })
        results = response.json()
        for r in results.get("results", []):
            print(f"[{r['score']:.2f}] {r['content'][:80]}...")

asyncio.run(main())
```

---

## Error Handling

```python
import httpx

def safe_api_call(method: str, path: str, **kwargs) -> dict:
    """Make an API call with error handling."""
    try:
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        body = e.response.json() if e.response.headers.get(
            "content-type", ""
        ).startswith("application/json") else {}

        if status == 401:
            raise RuntimeError("Authentication failed. Check your API key.")
        elif status == 429:
            retry_after = int(e.response.headers.get("Retry-After", 60))
            raise RuntimeError(f"Rate limited. Retry after {retry_after} seconds.")
        elif status == 404:
            raise RuntimeError(f"Resource not found: {path}")
        else:
            raise RuntimeError(
                f"API error {status}: {body.get('message', 'Unknown error')}"
            )
    except httpx.ConnectError:
        raise RuntimeError(f"Cannot connect to AutoBot at {BASE_URL}")
```

---

## Next Steps

- See the full [API Reference](../api/public-api-reference.md) for all endpoints
- Read the [API Versioning Strategy](../api/api-versioning.md) for stability guarantees
- Check the [TypeScript Quickstart](typescript-quickstart.md) for frontend/Node.js usage
