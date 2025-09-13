# 🐳 Centralized Data Management for Docker Containers

## Overview

AutoBot uses a centralized volume system to ensure all containers have consistent access to:
- **Prompts**: AI agent prompt templates
- **Knowledge Base**: System documentation and guides
- **Models**: Shared AI models
- **Configuration**: Shared configuration files

## Architecture

```
docker/volumes/
├── prompts/          # All prompt templates (read-only in containers)
├── knowledge_base/   # System documentation (read-only in containers)
├── models/          # Shared AI models (read-write)
└── config/          # Shared configuration (read-only in containers)
```

## Setup

### 1. Initial Setup

Run the setup script to create the volume structure and copy files:

```bash
./scripts/setup_docker_volumes.sh
```

This script:
- Creates the volume directory structure
- Copies prompts from `prompts/` to `docker/volumes/prompts/`
- Copies documentation to the knowledge base
- Creates a knowledge base index
- Sets proper permissions

### 2. Docker Compose Configuration

The volumes are automatically configured in:
- `docker/compose/docker-compose.hybrid.yml` (for hybrid deployment)
- `docker-compose.volumes.yml` (override file for standard deployment)

## Volume Mappings

### AI Stack Container
```yaml
volumes:
  - ./docker/volumes/prompts:/app/prompts:ro
  - ./docker/volumes/knowledge_base:/app/knowledge_base:ro
  - ./docker/volumes/models:/app/models
  - ./docker/volumes/config:/app/config:ro
```

### NPU Worker Container
```yaml
volumes:
  - ./docker/volumes/prompts:/app/prompts:ro
  - ./docker/volumes/knowledge_base:/app/knowledge_base:ro
  - ./docker/volumes/models:/app/models
  - ./docker/volumes/config:/app/config:ro
```

## Knowledge Base Management

### Structure

```
knowledge_base/
├── index.json        # Knowledge base index and metadata
├── system_docs/      # Core system documentation
├── user_guides/      # End-user documentation
├── api_docs/         # API documentation
├── architecture/     # Architecture documents
└── load_to_db.py     # Script to load docs into vector DB
```

### Loading Documentation

To load documentation into the vector database:

```bash
# Inside the AI stack container
docker exec -it autobot-ai-stack python /app/knowledge_base/load_to_db.py

# Or during container startup (automatic)
# Set environment variable: LOAD_KNOWLEDGE_BASE=true
```

### Adding New Documentation

1. Add documents to appropriate category:
   ```bash
   # For system documentation
   cp my_doc.md docker/volumes/knowledge_base/system_docs/

   # For API documentation
   cp api_guide.md docker/volumes/knowledge_base/api_docs/
   ```

2. Update the index if needed:
   ```bash
   vim docker/volumes/knowledge_base/index.json
   ```

3. Reload in container:
   ```bash
   docker exec -it autobot-ai-stack python /app/knowledge_base/load_to_db.py
   ```

## Prompt Management

### Structure

All prompts are organized by category:
```
prompts/
├── default/          # Default agent prompts
├── orchestrator/     # Orchestrator prompts
├── reflection/       # Reflection prompts
├── developer/        # Developer agent prompts
├── researcher/       # Research agent prompts
└── ...
```

### Updating Prompts

1. Edit prompts in the centralized location:
   ```bash
   vim docker/volumes/prompts/default/agent.system.main.md
   ```

2. Restart containers to reload prompts:
   ```bash
   docker-compose -f docker/compose/docker-compose.hybrid.yml restart autobot-ai-stack
   ```

## Troubleshooting

### Missing Prompts Error

If you see errors like:
```
Base composite prompt file not found: prompts/reflection/agent.system.main.role.md
```

**Solution**:
1. Run setup script: `./scripts/setup_docker_volumes.sh`
2. Verify prompts exist: `ls docker/volumes/prompts/`
3. Check container volumes: `docker inspect autobot-ai-stack | grep -A 10 Mounts`

### Knowledge Base Not Loading

If knowledge base is empty:

**Solution**:
1. Check index exists: `cat docker/volumes/knowledge_base/index.json`
2. Manually load: `docker exec -it autobot-ai-stack python /app/knowledge_base/load_to_db.py`
3. Check logs: `docker logs autobot-ai-stack`

### Permission Issues

If containers can't read files:

**Solution**:
1. Check permissions: `ls -la docker/volumes/`
2. Fix permissions: `chmod -R 755 docker/volumes/prompts docker/volumes/knowledge_base`

## Best Practices

1. **Always use the setup script** for initial setup
2. **Keep documentation updated** in the knowledge base
3. **Test prompt changes** before deploying to production
4. **Monitor container logs** for loading errors
5. **Backup volumes** before major updates

## Maintenance

### Updating Content

```bash
# Update prompts
cp new_prompts/* docker/volumes/prompts/category/

# Update documentation
cp new_docs/* docker/volumes/knowledge_base/system_docs/

# Reload in containers
docker-compose -f docker/compose/docker-compose.hybrid.yml restart
```

### Backup

```bash
# Backup all volumes
tar -czf autobot-volumes-backup-$(date +%Y%m%d).tar.gz docker/volumes/

# Restore from backup
tar -xzf autobot-volumes-backup-20240820.tar.gz
```

## Integration with Development

When developing locally, you can:

1. **Use the same prompts** as containers:
   ```python
   # In your code
   PROMPTS_DIR = "docker/volumes/prompts"
   ```

2. **Test with production knowledge base**:
   ```python
   KB_PATH = "docker/volumes/knowledge_base"
   ```

This ensures consistency between development and containerized environments.
