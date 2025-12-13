# ADR-001: Distributed 6-VM Architecture

## Status

**Status**: Accepted

## Date

**Date**: 2025-01-01

## Context

AutoBot is an AI-powered automation platform that requires multiple specialized services:
- Backend API processing
- Frontend web interface
- Redis data storage
- AI/ML model serving
- Browser automation
- Hardware-accelerated AI (NPU)

Running all services on a single machine creates several problems:
1. **Resource contention**: AI workloads compete with API requests
2. **Single point of failure**: One crash affects all services
3. **Scaling limitations**: Cannot scale individual components
4. **Security concerns**: Browser automation needs isolation
5. **Hardware requirements**: NPU acceleration requires specific hardware

## Decision

We adopt a distributed 6-VM architecture where each VM serves a specific purpose:

| VM | IP Address | Port | Purpose |
|----|------------|------|---------|
| **Main (WSL)** | 172.16.168.20 | 8001, 6080 | Backend API + VNC Desktop |
| **VM1 Frontend** | 172.16.168.21 | 5173 | Web interface (Vite dev server) |
| **VM2 NPU Worker** | 172.16.168.22 | 8081 | Hardware AI acceleration |
| **VM3 Redis** | 172.16.168.23 | 6379 | Data layer (Redis Stack) |
| **VM4 AI Stack** | 172.16.168.24 | 8080 | AI processing (Ollama, LLM) |
| **VM5 Browser** | 172.16.168.25 | 3000 | Web automation (Playwright) |

### Alternatives Considered

1. **Single Machine (Monolithic)**
   - Pros: Simple deployment, no network complexity
   - Cons: Resource contention, no isolation, can't scale, single point of failure

2. **Docker Containers on Single Host**
   - Pros: Better isolation than monolithic, easier deployment
   - Cons: Still shares resources, NPU passthrough complex, browser automation unreliable

3. **Kubernetes Cluster**
   - Pros: Industry standard, auto-scaling, self-healing
   - Cons: Overkill for single-user platform, complex NPU integration, high overhead

4. **Distributed VMs (Chosen)**
   - Pros: Complete isolation, dedicated resources, hardware passthrough, independent scaling
   - Cons: More complex networking, requires sync scripts

## Consequences

### Positive

- **Resource Isolation**: Each service has dedicated resources
- **Independent Scaling**: Can allocate more resources to specific VMs
- **Hardware Passthrough**: NPU VM can have direct hardware access
- **Security**: Browser automation isolated from sensitive data
- **Fault Tolerance**: One VM failure doesn't crash entire system
- **Development Flexibility**: Can restart individual services without affecting others

### Negative

- **Network Complexity**: Must manage inter-VM communication
- **Sync Overhead**: Code changes require syncing to VMs
- **Configuration Management**: Multiple machines to configure
- **Monitoring Complexity**: Must monitor 6 machines instead of 1

### Neutral

- Requires SSH key management for secure VM access
- Development workflow changes (edit locally, sync to VMs)

## Implementation Notes

### Key Files

- `run_autobot.sh` - Main startup script orchestrating all VMs
- `scripts/utilities/sync-to-vm.sh` - File synchronization utility
- `~/.ssh/autobot_key` - SSH key for VM authentication

### Network Configuration

All VMs are on the same subnet (172.16.168.0/24) for low-latency communication.

```bash
# SSH access pattern
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21

# Sync files to VM
./scripts/utilities/sync-to-vm.sh frontend autobot-vue/src/ /home/autobot/autobot-vue/src/
```

### Health Checks

```bash
# Backend API
curl http://localhost:8001/api/health

# Redis
redis-cli -h 172.16.168.23 ping

# Frontend (from main machine)
curl http://172.16.168.21:5173
```

### Critical Rules

1. **Never run frontend on main machine** - Only VM1 serves frontend
2. **Never edit code directly on VMs** - Edit locally, sync to VMs
3. **Always use sync scripts** - Manual copying leads to inconsistency

## Related ADRs

- [ADR-002](002-redis-database-separation.md) - Redis runs on dedicated VM3
- [ADR-003](003-npu-integration-strategy.md) - NPU worker on dedicated VM2
- [ADR-005](005-single-frontend-mandate.md) - Frontend exclusively on VM1

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
