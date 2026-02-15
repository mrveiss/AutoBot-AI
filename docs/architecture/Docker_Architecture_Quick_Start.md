# AutoBot Docker Architecture - Quick Start Guide

## 🚀 Overview

AutoBot now features a comprehensive Docker architecture with three deployment modes:

1. **Standard Mode**: Basic hybrid setup (local + Docker containers)
2. **Centralized Logging Mode**: All logs collected in one place with ELK stack
3. **Redis Separation Mode**: Isolated databases for different data types

## 📋 Prerequisites

- Docker and Docker Compose installed
- At least 4GB RAM available
- Ports 8001, 5173, 6379, 24224, 9200, 5341 available

## 🏁 Quick Start Commands

### 1. Initial Setup
```bash
# Run setup script to install all dependencies
# Deploy with Ansible: cd autobot-slm-backend/ansible && ansible-playbook playbooks/deploy-full.yml

# Create Docker volumes and configuration
mkdir -p docker/volumes/{prompts,knowledge_base,config,uploads}
mkdir -p logs/autobot-centralized
```

### 2. Choose Your Deployment Mode

#### Standard Mode (Recommended for development)
```bash
./run_agent.sh
```

#### Centralized Logging Mode (All logs in one place)
```bash
./run_agent.sh --centralized-logs
```
- **Log Viewer**: http://localhost:5341
- **Elasticsearch**: http://localhost:9200
- **All logs location**: `./logs/autobot-centralized/`

#### Redis Separation Mode (Isolated databases)
```bash
./run_agent.sh --redis-separation
```
- **11 isolated databases**: main(0), knowledge(1), prompts(2), agents(3), etc.
- **Configuration**: `docker/volumes/config/redis-databases.yaml`

#### Full Docker Setup (All containers)
```bash
./run_agent.sh --all-containers --centralized-logs --redis-separation
```

### 3. Access Your Services

| Service | URL | Purpose |
|---------|-----|---------|
| **AutoBot Frontend** | http://localhost:5173 | Main application interface |
| **AutoBot Backend** | http://localhost:8001 | API and backend services |
| **Redis** | localhost:6379 | Data storage |
| **Log Viewer** | http://localhost:5341 | Centralized logs (if enabled) |
| **NPU Worker** | http://localhost:8081 | Code search acceleration |
| **Playwright** | http://localhost:3000 | Browser automation |

## 🔧 Configuration Files

### Redis Database Separation
Located at: `docker/volumes/config/redis-databases.yaml`
```yaml
redis_databases:
  main: {db: 0, description: "Main application data"}
  knowledge: {db: 1, description: "Knowledge base documents"}
  prompts: {db: 2, description: "Prompt templates"}
  agents: {db: 3, description: "Agent communication"}
  # ... 7 more databases
```

### Centralized Logging
Located at: `docker/volumes/fluentd/fluent.conf`
- Collects logs from ALL containers
- Stores in single location: `logs/autobot-centralized/`
- Indexes in Elasticsearch for searching

## 📊 New Features Available

### Codebase Analytics
- **Frontend**: Navigate to "Analytics" tab in web interface
- **API Endpoints**:
  - `/api/code_search/analytics/declarations`
  - `/api/code_search/analytics/duplicates`
- **NPU Acceleration**: Hardware-accelerated code search when available

### Centralized Volume Management
All Docker volumes are now organized in `docker/volumes/`:
```
docker/volumes/
├── prompts/          # Centralized prompt storage
├── knowledge_base/   # Knowledge base documents
├── config/          # Configuration files
├── uploads/         # File uploads
└── fluentd/         # Logging configuration
```

## 🐛 Troubleshooting

### Network Issues
If you get network errors:
```bash
# Clean up networks
docker network prune -f

# Restart with logging
./run_agent.sh --centralized-logs
```

### Container Issues
```bash
# Check container status
docker ps -a

# View logs
docker logs autobot-log-collector
docker logs autobot-redis

# Clean restart
docker-compose -f docker-compose.centralized-logs.yml down
docker-compose -f docker-compose.centralized-logs.yml up -d
```

### Redis Database Issues
```bash
# Test Redis separation
PYTHONPATH=. python -c "
from src.utils.redis_database_manager import redis_db_manager
print(redis_db_manager.validate_database_separation())
"
```

## 📈 Performance Optimization

### Resource Allocation
- **Minimum**: 4GB RAM, 2 CPU cores
- **Recommended**: 8GB RAM, 4 CPU cores
- **Heavy analytics**: 16GB RAM, 8 CPU cores

### Database Optimization
- Use `--redis-separation` for better data isolation
- Monitor database usage: `redis-cli info memory`
- Configure TTL values in `redis-databases.yaml`

### Logging Optimization
- Centralized logging uses ~500MB RAM
- Log retention: 7 days by default
- Adjust in `docker/volumes/fluentd/fluent.conf`

## 🔒 Security Considerations

### Database Security
- Databases isolated by number (0-15)
- Different security levels per database type
- Encryption enabled for high-security databases

### Network Security
- All services on isolated Docker network
- No external access except defined ports
- Container-to-container communication only

### Log Security
- Sensitive data filtered before logging
- Structured logging with proper field isolation
- Log rotation and retention policies

## 🚀 Advanced Usage

### Custom Docker Compose Files
```bash
# Use specific compose file
./run_agent.sh --compose-file docker/compose/my-custom.yml

# Combine multiple features
./run_agent.sh --centralized-logs --redis-separation --all-containers
```

### Development Mode
```bash
# Test mode with additional validation
./run_agent.sh --test-mode --centralized-logs
```

### Scaling Options
- Ready for Kubernetes migration
- Horizontal scaling of agent containers
- Load balancing between agent replicas
- See `docs/Kubernetes_Migration_Strategy.md` for details

## 📚 Additional Documentation

- **Complete setup**: See `scripts/setu# Deploy with Ansible: cd autobot-slm-backend/ansible && ansible-playbook playbooks/deploy-full.yml`
- **Kubernetes migration**: See `docs/Kubernetes_Migration_Strategy.md`
- **API documentation**: See `docs/API_Duplication_Analysis.md`
- **Redis configuration**: See `docker/volumes/config/redis-databases.yaml`
- **Codebase analytics**: Frontend Analytics tab

## 💡 Pro Tips

1. **Always use centralized logging in production**: `--centralized-logs`
2. **Enable Redis separation for better performance**: `--redis-separation`
3. **Monitor resource usage**: Check Docker stats regularly
4. **Use the Analytics tab**: Great for code quality insights
5. **Keep scripts updated**: They're the single source of truth!

---

**Need help?** Check `./run_agent.sh --help` for all available options.
