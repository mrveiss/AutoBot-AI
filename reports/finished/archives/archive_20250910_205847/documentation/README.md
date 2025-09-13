# Docker Volumes for Centralized Data Management

This directory contains shared data that needs to be accessible across all AutoBot containers.

## Structure

```
docker/volumes/
├── prompts/          # All prompt templates
├── knowledge_base/   # System documentation and knowledge
├── models/          # Shared AI models
└── config/          # Shared configuration files
```

## Volume Mapping

Each container should mount these volumes:

```yaml
volumes:
  - ./docker/volumes/prompts:/app/prompts:ro
  - ./docker/volumes/knowledge_base:/app/knowledge_base:ro
  - ./docker/volumes/models:/app/models
  - ./docker/volumes/config:/app/config:ro
```

## Data Organization

### Prompts
All prompt templates used by AI agents and LLM interfaces.

### Knowledge Base
- System documentation
- User guides
- API documentation
- Architecture documents
- Migration guides

### Models
Shared model files that can be accessed by multiple containers.

### Config
Shared configuration files that override container-specific settings.
