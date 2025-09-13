# AutoBot Docker Architecture

## Overview

This document describes the containerized architecture for AutoBot components that don't require direct OS access. The design separates stateless services into containers while keeping hardware-dependent components on the host.

## Architecture Diagram

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │  Chat Agent     │    │  RAG Agent      │
│   (Vue 3)       │    │  (Lightweight)  │    │  (Document AI)  │
│   Port: 5173    │    │  Port: 8004     │    │  Port: 8003     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
         ┌─────────────────┐    ┌┴─────────────────┐
         │ Knowledge Base  │    │      Redis       │
         │ (ChromaDB)      │    │   (Data Layer)   │
         │ Port: 8002      │    │   Port: 6379     │
         └─────────────────┘    └──────────────────┘
                 │                       │
                 └───────────────────────┘

         ╔═══════════════════════════════════════╗
         ║              HOST SYSTEM              ║
         ║  ┌─────────────┐  ┌─────────────────┐ ║
         ║  │ Orchestrator│  │ System Commands │ ║
         ║  │ (Coordinator)│  │ (OS Access)     │ ║
         ║  └─────────────┘  └─────────────────┘ ║
         ║  ┌─────────────┐  ┌─────────────────┐ ║
         ║  │ Research    │  │ Hardware Accel  │ ║
         ║  │ (Playwright)│  │ (NPU/GPU)       │ ║
         ║  └─────────────┘  └─────────────────┘ ║
         ╚═══════════════════════════════════════╝
```

## Containerized Components

### 1. Redis Stack (Data Layer)
- **Purpose**: Data persistence, caching, and pub/sub messaging
- **Container**: `redis/redis-stack:latest`
- **Resources**: 1GB memory limit
- **Volumes**: Persistent data storage
- **Benefits**: Isolated data layer, easy backup/restore

### 2. Knowledge Base Service
- **Purpose**: Vector database and embedding operations
- **Components**: ChromaDB, sentence transformers, FAISS
- **Port**: 8002
- **Resources**: 2GB memory limit
- **Benefits**: Isolated vector operations, scalable

### 3. RAG Agent
- **Purpose**: Document processing and synthesis
- **Model**: `artifish/llama3.2-uncensored:latest` (2.2GB)
- **Port**: 8003
- **Resources**: 3GB memory limit
- **Benefits**: Dedicated document AI processing

### 4. Chat Agent
- **Purpose**: Lightweight conversational interactions
- **Model**: `llama3.2:3b-instruct-q4_K_M` (2GB)
- **Port**: 8004
- **Resources**: 2GB memory limit
- **Benefits**: Fast response times, isolated chat processing

### 5. Frontend
- **Purpose**: Vue 3 web application
- **Port**: 5173
- **Resources**: 512MB memory limit
- **Benefits**: Static file serving, development hot-reload

## Host System Components

These components remain on the host due to hardware/OS requirements:

### 1. Orchestrator
- **Reason**: Coordinates all services and requires system-level access
- **Hardware**: Needs GPU/NPU access for large models

### 2. System Commands Agent
- **Reason**: Executes shell commands and file operations
- **Requirements**: Direct OS access, file system manipulation

### 3. Research Agent
- **Reason**: Uses Playwright for web scraping and browser automation
- **Requirements**: Display server access, browser binaries

### 4. Hardware Acceleration Manager
- **Reason**: Manages NPU/GPU resources and driver communication
- **Requirements**: Direct hardware access, driver binaries

## Deployment Instructions

### 1. Prerequisites
```bash
# Install Docker and Docker Compose
sudo apt install docker.io docker-compose

# Enable Docker service
sudo systemctl enable docker
sudo systemctl start docker
```

### 2. Environment Setup
```bash
# Source GPU optimizations (if available)
source gpu_env_config.sh

# Source NPU optimizations (if available on native Linux/Windows)
source npu_env_config.sh
```

### 3. Container Deployment
```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Scale specific services
docker-compose up -d --scale chat-agent=2
```

### 4. Health Monitoring
```bash
# Check service health
docker-compose ps

# Monitor resource usage
docker stats

# View Redis data
docker exec -it autobot-redis redis-cli
```

## Resource Requirements

| Service | CPU | Memory | Disk | Notes |
|---------|-----|--------|------|-------|
| Redis | 0.5 cores | 1GB | 10GB | Persistent storage |
| Knowledge Base | 1 core | 2GB | 20GB | Vector storage |
| RAG Agent | 2 cores | 3GB | 5GB | Model cache |
| Chat Agent | 1 core | 2GB | 3GB | Model cache |
| Frontend | 0.2 cores | 512MB | 1GB | Static files |
| **Total** | **4.7 cores** | **8.5GB** | **39GB** | |

## Network Architecture

- **Network**: Custom bridge network `autobot-network`
- **Subnet**: 172.20.0.0/16
- **Inter-service Communication**: Container names as hostnames
- **External Access**: Host ports exposed for web interfaces

## Security Considerations

### Container Security
- Non-root users in all containers
- Read-only volume mounts where possible
- Network isolation with custom bridge
- Resource limits to prevent DoS

### Data Security
- Redis password authentication
- Volume encryption (optional)
- TLS termination at reverse proxy (recommended)

## Monitoring and Logging

### Health Checks
- HTTP health endpoints for all services
- Docker health check integration
- Automatic container restart on failure

### Logging Strategy
- Centralized logging with Docker logs
- Log rotation and retention policies
- Structured JSON logging format

## Scaling Strategies

### Horizontal Scaling
```bash
# Scale chat agents for high load
docker-compose up -d --scale chat-agent=3

# Load balance with nginx
# (nginx config not included - use your preferred solution)
```

### Vertical Scaling
```yaml
# Increase memory limits in docker-compose.yml
deploy:
  resources:
    limits:
      memory: 4G  # Increased from 2G
```

## Backup and Recovery

### Data Backup
```bash
# Backup Redis data
docker exec autobot-redis redis-cli BGSAVE
docker cp autobot-redis:/data/dump.rdb ./backup/

# Backup knowledge base vectors
docker cp autobot-knowledge-base:/app/vector_store ./backup/
```

### Service Recovery
```bash
# Restart failed service
docker-compose restart knowledge-base

# Full system recovery
docker-compose down && docker-compose up -d
```

## Integration with Host System

The containerized services integrate with host components through:

1. **Redis PubSub**: Message passing between containers and host
2. **HTTP APIs**: RESTful communication on defined ports
3. **Shared Volumes**: Configuration and data sharing
4. **Environment Variables**: Dynamic configuration

## Performance Optimizations

### Memory Optimization
- Model quantization (q4_K_M) for reduced memory usage
- Shared model caches between similar agents
- Memory limits prevent OOM on host system

### CPU Optimization
- CPU affinity for container processes
- Thread limits aligned with available cores
- Load balancing across multiple agent instances

### I/O Optimization
- SSD storage for vector databases
- Async I/O operations
- Connection pooling for Redis

## Troubleshooting Guide

### Common Issues

1. **Container won't start**
   ```bash
   docker-compose logs service-name
   docker inspect container-name
   ```

2. **Out of memory errors**
   ```bash
   # Increase memory limits in docker-compose.yml
   # Monitor with: docker stats
   ```

3. **Network connectivity issues**
   ```bash
   docker network inspect autobot-network
   docker exec container-name ping other-container
   ```

4. **Model loading failures**
   ```bash
   # Check model availability
   docker exec rag-agent ollama list
   # Pull missing models
   docker exec rag-agent ollama pull model-name
   ```

This Docker architecture provides a scalable, maintainable deployment strategy for AutoBot components while preserving the performance benefits of hardware acceleration on the host system.
