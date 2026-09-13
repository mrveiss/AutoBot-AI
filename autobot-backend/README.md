# AutoBot User Backend

> **Deploys to:** 172.16.168.20 (Main Server)

Core AutoBot backend - AI agents, chat workflows, and API endpoints.

## Structure

| Directory | Purpose |
|-----------|---------|
| `api/` | FastAPI endpoint routers |
| `services/` | Business logic services |
| `models/` | SQLAlchemy database models |
| `agents/` | AI agent implementations |
| `tools/` | Agent tools |
| `resources/` | Prompts, templates, content |
| `migrations/` | Database migrations |

## Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

## Deployment

```bash
./autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh main autobot-backend/
```

## Infrastructure

Component-specific infrastructure is located at:

```text
autobot-infrastructure/autobot-backend/
├── docker/      # Docker configurations
├── tests/       # Component-specific tests
├── config/      # Configuration files
├── scripts/     # Deployment scripts
└── templates/   # Service templates
```
