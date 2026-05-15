# Python SDK Quickstart

This guide shows how to integrate with AutoBot using Python. Until the official `autobot-sdk` package is published, you can call the API directly with `httpx` or `requests`.

---

## Installation

### Official SDK (planned)

```bash
pip install autobot-sdk
```

### Direct HTTP (available now)

```bash
pip install httpx
```

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

def list_sessions(limit: int = 50) -> dict:
    """List chat sessions."""
    response = client.get("/chats", params={"limit": limit})
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
