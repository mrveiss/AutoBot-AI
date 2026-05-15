# Configure the AutoBot Chat module to use a local Ollama instance for processing natural language prompts

AutoBot's chat module selects its Ollama endpoint and model from environment variables and a runtime-configurable settings store.  A local Ollama instance can be pointed to in seconds via environment variables; the admin API allows changing it without a restart.

## Quickstart — environment variables

Set these before starting AutoBot backend:

```bash
# URL of your local Ollama API server
export AUTOBOT_OLLAMA_ENDPOINT="http://localhost:11434"
export AUTOBOT_OLLAMA_HOST="localhost"

# Default model to use for chat
export AUTOBOT_DEFAULT_LLM_MODEL="llama3:8b"

# Optional: separate GPU-accelerated endpoint
export AUTOBOT_OLLAMA_GPU_ENDPOINT="http://localhost:11434"
```

Restart the AutoBot backend after setting these variables.  The chat module picks them up at startup.

## Configure via the admin API (no restart required)

```python
import httpx

SLM_URL = "https://slm.example.com"
TOKEN   = "your-admin-jwt-token"

client = httpx.Client(
    base_url=SLM_URL,
    headers={"Authorization": f"Bearer {TOKEN}"},
    verify=False,
)

# 1. Set the Ollama configuration
client.put("/api/settings/admin/llm", json={
    "active_provider": "ollama",
    "ollama_host":     "localhost",
    "ollama_port":     11434,
    "selected_model":  "llama3:8b",
    "cpu_models":      ["llama3:8b", "mistral:7b", "phi3:mini"],
    "gpu_models":      ["qwen3.5:9b", "llama3:70b"],
})

# 2. Test connectivity
test = client.post("/api/settings/admin/llm/test", json={
    "provider": "ollama",
    "endpoint": "http://localhost:11434",
    "model":    "llama3:8b",
}).json()
print(f"Connection test: {test['status']}")

# 3. Read back the current config
config = client.get("/api/settings/admin/llm").json()
print(f"Active provider: {config['active_provider']}")
print(f"Selected model:  {config['selected_model']}")
```

## Apply configuration across the entire fleet via Ansible

After saving the config, push it to all fleet nodes:

```python
apply = client.post("/api/settings/admin/llm/apply").json()
print(f"Apply status: {apply['status']}")
# Triggers: ansible-playbook playbooks/update-llm-config.yml
```

## How the chat module selects the Ollama endpoint

`autobot-backend/chat_workflow/llm_handler.py` resolves the endpoint in this priority order:

```
1. SLM service discovery  (fleet-managed; auto-discovered from SLM if available)
2. Model-based routing    (GPU models → AUTOBOT_OLLAMA_GPU_ENDPOINT,
                           CPU models → AUTOBOT_OLLAMA_ENDPOINT)
3. Config-based default   (from settings store / environment variable fallback)
```

For a local single-machine setup, only priority 3 applies.  The chat module calls:

```
POST {AUTOBOT_OLLAMA_ENDPOINT}/api/generate
{
  "model":  "llama3:8b",
  "prompt": "<assembled full prompt>",
  "stream": true
}
```

## Model routing — GPU vs CPU

When both a GPU and a CPU Ollama endpoint are available, the chat module routes automatically:

```python
# autobot_shared/ssot_config.py (simplified)
def get_ollama_endpoint_for_model(self, model_name: str) -> str:
    if model_name in self.gpu_models:
        return self.ollama_gpu_endpoint   # AUTOBOT_OLLAMA_GPU_ENDPOINT
    return self.ollama_endpoint           # AUTOBOT_OLLAMA_ENDPOINT
```

To force all requests to a single local Ollama, set both env vars to the same URL:

```bash
export AUTOBOT_OLLAMA_ENDPOINT="http://localhost:11434"
export AUTOBOT_OLLAMA_GPU_ENDPOINT="http://localhost:11434"
```

## Verify the active model from the chat frontend

A chat message is processed via:

```
POST /api/chat/message
{
  "session_id": "<session>",
  "message":    "Which model are you running on?"
}
```

AutoBot appends model metadata to the response so the frontend can display the active endpoint and model name.

## Environment variable reference

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_OLLAMA_ENDPOINT` | `http://localhost:11434` | Ollama base URL for CPU models |
| `AUTOBOT_OLLAMA_GPU_ENDPOINT` | same as above | Ollama base URL for GPU models |
| `AUTOBOT_OLLAMA_HOST` | `localhost` | Hostname component (used by admin UI) |
| `AUTOBOT_DEFAULT_LLM_MODEL` | `qwen3.5:9b` | Default model name |

## Architecture reference

- **Endpoint resolution** — `autobot-backend/chat_workflow/llm_handler.py` (`_get_ollama_endpoint`, `_get_ollama_endpoint_for_model`, `_prepare_llm_request_params`)
- **Config definition** — `autobot_shared/ssot_config.py` (`LLMConfig`, `get_ollama_url`, `get_ollama_url_for_model`)
- **Admin API** — `autobot-slm-backend/api/llm_config.py` (`GET/PUT /settings/admin/llm`, `POST /settings/admin/llm/test`, `POST /settings/admin/llm/apply`)
- **Env var mappings** — `autobot-backend/config/loader.py` (`ENV_VAR_MAPPINGS`)
