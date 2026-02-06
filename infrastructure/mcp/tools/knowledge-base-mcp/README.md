# AutoBot Knowledge Base MCP Server

A true Model Context Protocol (MCP) server that provides direct access to AutoBot's knowledge base for Claude and other MCP-compatible LLMs.

## Features

- **Semantic Search** - Search the knowledge base using natural language
- **Vector Similarity** - Direct vector similarity search with threshold filtering
- **Document Addition** - Add new knowledge to the vector store
- **Topic Summarization** - Get AI-generated summaries of knowledge topics
- **Statistics** - Query knowledge base metrics and health

## Installation

```bash
cd mcp-tools/knowledge-base-mcp
pip install -e .
```

## Usage

### As Claude Code MCP Server

Add to your Claude configuration (`~/.claude.json` or project `.claude/settings.json`):

```json
{
  "mcpServers": {
    "autobot-knowledge": {
      "command": "python",
      "args": ["-m", "autobot_knowledge_mcp.server"],
      "cwd": "/home/kali/Desktop/AutoBot/mcp-tools/knowledge-base-mcp",
      "env": {
        "AUTOBOT_BACKEND_HOST": "172.16.168.20",
        "AUTOBOT_BACKEND_PORT": "8001"
      }
    }
  }
}
```

### As Standalone Server

```bash
# Set environment variables
export AUTOBOT_BACKEND_HOST=172.16.168.20
export AUTOBOT_BACKEND_PORT=8001

# Run the server
python -m autobot_knowledge_mcp.server
```

### Embedded Client (For Agents)

For in-process access without network overhead (recommended for KB Librarian):

```python
from autobot_knowledge_mcp.embedded import create_knowledge_client

# Create client
client = create_knowledge_client(knowledge_base=kb)

# Search
results = await client.search("Redis configuration", top_k=5)
for r in results:
    print(f"[{r.score:.3f}] {r.content[:100]}")

# Add document
result = await client.add(
    content="New knowledge about system configuration",
    source="librarian",
    metadata={"category": "configuration"}
)

# Batch operations
async with client.batch() as batch:
    batch.add("Document 1", source="research")
    batch.add("Document 2", source="research")
# All committed when context exits

# Get stats
stats = await client.stats(include_details=True)
print(f"Documents: {stats.total_documents}")
```

## Available Tools

| Tool | Description |
|------|-------------|
| `search_knowledge` | Semantic search across the knowledge base |
| `add_knowledge` | Add new documents to the knowledge base |
| `knowledge_stats` | Get knowledge base statistics |
| `summarize_topic` | AI-powered topic summarization |
| `vector_search` | Direct vector similarity search |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_BACKEND_HOST` | `172.16.168.20` | AutoBot backend API host |
| `AUTOBOT_BACKEND_PORT` | `8001` | AutoBot backend API port |
| `AUTOBOT_KB_TIMEOUT` | `30` | Request timeout in seconds |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude / LLM                             │
└─────────────────────────┬───────────────────────────────────┘
                          │ MCP Protocol (stdio)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              AutoBot Knowledge MCP Server                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │search_knowledge│  │add_knowledge │  │knowledge_stats│     │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP (or embedded)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                 AutoBot Backend API                          │
│              /api/knowledge/mcp/*                            │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Knowledge Base                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  LlamaIndex   │  │   Ollama     │  │    Redis     │       │
│  │  (Indexing)   │  │ (Embeddings) │  │  (Vectors)   │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Efficiency Comparison

| Aspect | HTTP REST | MCP (stdio) | Embedded |
|--------|-----------|-------------|----------|
| Latency | ~10-20ms | ~1-5ms | <1ms |
| Connection | Per-request | Persistent | In-process |
| Claude Support | Custom adapter | Native | Agent-only |
| Use Case | External APIs | Claude Code | KB Librarian |

## License

MIT - mrveiss 2025
