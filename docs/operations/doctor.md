# autobot doctor

Startup-repair and environment-health CLI tool.

## Usage

```bash
# Check only (default)
python -m autobot_backend.cli.doctor
python -m autobot_backend.cli.doctor --check

# Check and auto-repair fixable issues
python -m autobot_backend.cli.doctor --fix
```

## Checks

| Check | Fixable | Description |
|-------|---------|-------------|
| Redis schemas | No | Verifies Redis schemas for main, knowledge, prompts, analytics |
| ChromaDB collections | Yes | Verifies required collections exist; creates them if missing |
| Env file | No | Validates required environment variables are present |
| NPU worker registry | No | Verifies NPU workers are responsive |

## Background

Prior to issue #7371, repair logic ran during boot — causing 4× redundant repairs across uvicorn workers and masking boot failures. Boot path now only performs fast, idempotent, read-only operations.

## Deployment

Add to Ansible playbook post-deploy step:

```yaml
- name: Run autobot doctor
  command: python -m autobot_backend.cli.doctor --fix
  become: yes
  become_user: autobot
```
