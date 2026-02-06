# AutoBot Environment Files Documentation

This document describes the standardized environment file system for AutoBot, their relationships, and usage patterns.

## ENVIRONMENT FILE HIERARCHY

All environment files are **generated from** `config/complete.yaml` using the standardization script:
```bash
python scripts/generate-env-files.py
```

### 🔄 Generation System

**DO NOT EDIT ENVIRONMENT FILES MANUALLY** - They are auto-generated and will be overwritten.

To make changes:
1. Edit `config/complete.yaml`
2. Run `python scripts/generate-env-files.py`
3. All environment files will be regenerated consistently

## 📁 STANDARDIZED ENVIRONMENT FILES

### 1. **`.env` (Main Backend Environment)**
- **Purpose**: Primary backend configuration for production/hybrid mode
- **Scope**: Backend services, Redis, LLM services
- **Mode**: `AUTOBOT_DEPLOYMENT_MODE=hybrid`
- **Network**: Uses distributed IP addresses (172.16.168.x)
- **Used by**: Backend FastAPI application, system services

### 2. **`.env.localhost` (Local Development)**
- **Purpose**: Local development with all services on localhost
- **Scope**: All services running on 127.0.0.1
- **Mode**: `AUTOBOT_DEPLOYMENT_MODE=local`
- **Network**: Localhost only (127.0.0.1)
- **Used by**: Development workflows, testing

### 3. **`.env.native-vm` (Distributed VM Deployment)**
- **Purpose**: Production distributed VM architecture
- **Scope**: Each service on dedicated VM
- **Mode**: `AUTOBOT_DEPLOYMENT_MODE=distributed`
- **Network**: Distributed VMs (172.16.168.x subnet)
- **Used by**: Production VM deployments, scaling scenarios

### 4. **`.env.network` (Network Configuration)**
- **Purpose**: Centralized network configuration
- **Scope**: Service IP mappings, URL construction
- **Network**: Complete service topology
- **Used by**: Network troubleshooting, service discovery

### 5. **`autobot-vue/.env` (Frontend Configuration)**
- **Purpose**: Vue.js frontend specific configuration
- **Scope**: VITE_* variables, API endpoints, UI settings
- **Network**: Uses backend API endpoints and service URLs
- **Used by**: Vue.js build system, frontend development

### 6. **`docker/compose/.env.production` (Docker Production)**
- **Purpose**: Docker Compose production deployment
- **Scope**: Container orchestration, volume mounts, ports
- **Mode**: Production containers with proper security
- **Used by**: Docker Compose, container deployments

## 🏗️ CONFIGURATION ARCHITECTURE

```
config/complete.yaml (SINGLE SOURCE OF TRUTH)
           ↓
scripts/generate-env-files.py (GENERATOR)
           ↓
┌──────────────────────────────────────┐
│          Generated Files             │
├──────────────────────────────────────┤
│ .env                                 │ ← Backend production
│ .env.localhost                       │ ← Local development  
│ .env.native-vm                       │ ← Distributed VMs
│ .env.network                         │ ← Network topology
│ autobot-vue/.env                     │ ← Frontend config
│ docker/compose/.env.production       │ ← Docker production
└──────────────────────────────────────┘
```

## 🎯 DEPLOYMENT MODE MAPPING

| Deployment Scenario | Environment File | Mode Setting |
|---------------------|------------------|--------------|
| **Development** | `.env.localhost` | `local` |
| **Testing** | `.env.localhost` | `local` |
| **Hybrid (Default)** | `.env` | `hybrid` |
| **Production VMs** | `.env.native-vm` | `distributed` |
| **Docker Production** | `.env.production` | `production` |

## 📊 VARIABLE STANDARDIZATION

### Naming Conventions

All variables follow consistent patterns:

```bash
# Service hosts
AUTOBOT_[SERVICE]_HOST=<ip_address>

# Service ports  
AUTOBOT_[SERVICE]_PORT=<port_number>

# Service URLs (computed)
AUTOBOT_[SERVICE]_URL=<protocol>://<host>:<port>

# Redis databases
AUTOBOT_REDIS_DB_[PURPOSE]=<db_number>

# Frontend variables
VITE_[SETTING]=<value>

# Feature flags
AUTOBOT_[FEATURE]_ENABLED=<true|false>
```

### Resolved Conflicts

The standardization process resolved these critical conflicts:

1. **IP Address Consistency**: All files now use correct 172.16.168.x subnet
2. **Redis Database Mapping**: Standardized database assignments across all files
3. **Port Standardization**: Consistent port assignments from unified config
4. **Variable Naming**: All variables follow AUTOBOT_* or VITE_* patterns
5. **URL Construction**: Computed URLs consistent across all environments
6. **Legacy Compatibility**: Maintained backward compatibility variables

## 🔧 USAGE EXAMPLES

### Switching Deployment Modes

```bash
# Use local development
cp .env.localhost .env

# Use distributed VMs  
cp .env.native-vm .env

# Use hybrid mode (default)
python scripts/generate-env-files.py  # Regenerates .env as hybrid
```

### Updating Configuration

```bash
# 1. Edit unified configuration
vim config/complete.yaml

# 2. Regenerate all environment files
python scripts/generate-env-files.py

# 3. Restart services to pick up changes
./run_agent_unified.sh --dev
```

### Validating Environment

```bash
# Check Redis connectivity
docker exec autobot-redis redis-cli ping

# Test backend API
curl http://$(grep AUTOBOT_BACKEND_HOST .env | cut -d= -f2):$(grep AUTOBOT_BACKEND_PORT .env | cut -d= -f2)/api/health

# Validate environment consistency
python scripts/validate-env-files.py  # TODO: Create this script
```

## 🛡️ SECURITY CONSIDERATIONS

### Sensitive Data

Environment files may contain:
- Service endpoints and ports
- Development configuration
- Network topology information

**NO SECRETS**: All authentication tokens, passwords, and secrets are stored separately in secure vaults.

### File Permissions

```bash
# Ensure proper permissions
chmod 644 .env*
chmod 644 autobot-vue/.env
chmod 644 docker/compose/.env.production
```

## 🔍 TROUBLESHOOTING

### Common Issues

1. **Service Connection Failures**
   - Check IP addresses in environment files match actual service locations
   - Verify ports are not blocked by firewall
   - Ensure services are running on expected hosts

2. **Frontend API Errors**  
   - Verify `autobot-vue/.env` has correct backend URLs
   - Check CORS settings in backend for frontend origins
   - Validate WebSocket endpoints

3. **Redis Connection Issues**
   - Confirm Redis host/port in environment files
   - Check Redis database numbers are not conflicting
   - Verify Redis service is accessible from backend host

### Debugging Commands

```bash
# Show current environment settings
env | grep AUTOBOT_ | sort

# Test service connectivity
nc -zv <host> <port>

# Validate Redis connectivity
redis-cli -h <redis_host> -p <redis_port> ping

# Check backend health
curl -f http://<backend_host>:<backend_port>/api/health
```

## 📈 MAINTENANCE

### Regular Tasks

1. **Weekly**: Validate environment file consistency
2. **On Config Changes**: Regenerate all files using the script
3. **Before Deployment**: Verify environment matches deployment target
4. **After Updates**: Test connectivity between all configured services

### Monitoring

Monitor these metrics to ensure environment configuration is working:
- Service connectivity success rates
- API response times from configured endpoints  
- Redis connection pool utilization
- Frontend-to-backend communication success

---

**Generated**: $(date)
**Last Updated**: Environment files standardized by SUBAGENT HOTEL Phase 2
**Next Review**: After major infrastructure changes
