# Backend & API Development Guide

## 🌐 API Development Standards

**CRITICAL: ALWAYS CHECK FOR EXISTING ENDPOINTS BEFORE CREATING NEW ONES**

### 🔍 Pre-Development API Audit (MANDATORY)
Before creating ANY new API endpoint, you MUST:

1. **Search existing endpoints**:
   ```bash
   # Search all backend API files for similar endpoints
   find backend/api -name "*.py" | xargs grep -h "@router\." | grep -i "keyword"

   # Check for similar functionality
   grep -r "function_name\|endpoint_pattern" backend/api/

   # Verify frontend usage patterns
   find autobot-vue -name "*.js" -o -name "*.vue" | xargs grep -l "api/"
   ```

2. **Audit existing implementations**:
   - Check if similar functionality already exists
   - Identify any duplicate or overlapping endpoints
   - Verify if existing endpoints can be extended instead

3. **Document justification** if new endpoint is truly needed:
   - Why existing endpoints cannot be used/extended
   - What unique functionality this provides
   - How it differs from similar endpoints

### 🚫 FORBIDDEN: API Duplication Patterns
**NEVER CREATE** these duplicate patterns:

❌ **Multiple health/status endpoints**:
- Use existing `/api/system/health` for all health checks
- Add module-specific details to single response

❌ **Similar endpoint names**:
- `/api/chat` vs `/api/chats` (confusing!)
- `/api/config` vs `/api/settings` vs `/api/configuration`
- `/api/status` vs `/api/health` vs `/api/info`

❌ **Functional duplicates**:
- Multiple terminal implementations
- Multiple workflow systems
- Multiple WebSocket handlers for same purpose

❌ **Version confusion**:
- `/api/endpoint` vs `/api/v1/endpoint` vs `/api/v2/endpoint`
- Keep single versioned API pattern

### ✅ REQUIRED: API Design Standards
**ALWAYS FOLLOW** these patterns:

✅ **RESTful naming conventions**:
```
GET    /api/{resource}           # List all
POST   /api/{resource}           # Create new
GET    /api/{resource}/{id}      # Get specific
PUT    /api/{resource}/{id}      # Update specific
DELETE /api/{resource}/{id}      # Delete specific
```

✅ **Consistent response format**:
```json
{
  "status": "success|error",
  "data": {...},
  "message": "descriptive message",
  "timestamp": "ISO-8601",
  "request_id": "unique-id"
}
```

✅ **Single responsibility per endpoint**:
- One endpoint = one clear purpose
- Avoid kitchen-sink endpoints that do multiple things
- Use query parameters for filtering/options

✅ **Logical grouping by functionality**:
```
/api/chat/*          # All chat operations
/api/terminal/*      # All terminal operations
/api/workflow/*      # All workflow operations
/api/system/*        # All system operations
```

### 🔧 API Consolidation Process
When you find duplicate endpoints:

1. **Immediate action**:
   - Document the duplication in `/docs/API_Duplication_Analysis.md`
   - Do NOT create additional duplicates
   - Use existing endpoint or consolidate first

2. **Consolidation steps**:
   - Identify which implementation is most complete/used
   - Plan migration for deprecated endpoints
   - Add deprecation warnings to old endpoints
   - Update frontend to use consolidated endpoint
   - Remove deprecated code after grace period

3. **Prevention measures**:
   - Update this guide with any new patterns found
   - Add API design review to commit checklist
   - Document API decision rationale in code comments

### 📋 API Development Checklist
Before creating new API endpoints:

- [ ] Searched for existing similar endpoints
- [ ] Verified no functional duplicates exist
- [ ] Checked frontend usage patterns
- [ ] Followed RESTful naming conventions
- [ ] Implemented consistent response format
- [ ] Added proper error handling
- [ ] Updated API documentation
- [ ] Added appropriate tests
- [ ] Verified no breaking changes to existing endpoints

### 🚨 API Emergency Procedures
If you discover major API duplications:

1. **Stop development** on duplicate endpoints
2. **Create consolidation plan** (see `/docs/API_Consolidation_Priority_Plan.md`)
3. **Fix critical missing endpoints** first (broken functionality)
4. **Implement backward compatibility** during consolidation
5. **Test thoroughly** before removing old endpoints

## 🏗️ Default Deployment Architecture

**AutoBot uses a HYBRID deployment model by default:**
- **Backend/Frontend**: Run on host system (localhost)
- **Services**: Run in Docker containers with exposed ports
- **Connection**: Host processes connect to containerized services via localhost ports

**Default Architecture:**
```
Host System (localhost)
├── Backend API           → http://localhost:8001 (host process)
├── Frontend UI           → http://localhost:5173 (host process)
└── Docker Containers     → Exposed on localhost ports
    ├── Redis             → redis://localhost:6379
    ├── AI Stack          → http://localhost:8080
    ├── NPU Worker        → http://localhost:8081
    └── Playwright VNC    → http://localhost:3000
```

## 🛠️ Backend Quick Commands

```bash
# APPLICATION LIFECYCLE (USER CONTROLLED)
./setup_agent.sh              # Initial setup and configuration
./run_agent.sh                # Start application (centralized logging by default)
./run_agent.sh --test-mode     # Start in test mode
./run_agent.sh --help          # Show available options

# CENTRALIZED LOGGING ACCESS
# Log Viewer (Seq): http://localhost:5341
# Credentials: admin / Autobot123!

# DISTRIBUTED DEPLOYMENT
./run_agent.sh --distributed --config=production.yml  # Distributed mode
export AUTOBOT_DEPLOYMENT_MODE=distributed           # Set deployment mode
export AUTOBOT_DOMAIN=autobot.prod                  # Set production domain

# SERVICE REGISTRY & DISCOVERY
# Location: src/utils/service_registry.py
# Modes: local, docker_local, distributed, kubernetes
# Health checks: Circuit breakers, automatic failover
# Config files: config/deployment/{mode}.yml

# DEVELOPMENT & TESTING
flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503  # Quality check

# API DUPLICATION PREVENTION (MANDATORY BEFORE NEW ENDPOINTS)
find backend/api -name "*.py" | xargs grep -h "@router\." | grep -i "keyword"  # Search existing endpoints
find autobot-vue -name "*.js" -o -name "*.vue" | xargs grep -l "api/"         # Check frontend usage

# CODE ANALYSIS & PROFILING
python src/agents/npu_code_search_agent.py --query "search_term"    # NPU code search
python scripts/comprehensive_code_profiler.py                       # Codebase analysis
python scripts/profile_api_endpoints.py                            # API performance

# IMPORTANT: ALL APPLICATION RESTARTS MUST BE DONE BY USER
# Do not programmatically restart, stop, or kill application processes
```

## 🚀 NPU Worker and Redis Code Search Capabilities

**YOU ARE AUTHORIZED TO USE NPU WORKER AND REDIS FOR ADVANCED CODE ANALYSIS**

### Available Tools
- `src/agents/npu_code_search_agent.py` - High-performance code searching
- `/api/code_search/` endpoints - Code analysis tasks
- NPU acceleration for semantic code similarity (when hardware supports)
- Redis-based indexing for fast code element lookup

### 🎯 APPROVED DEVELOPMENT SPEEDUP TASKS
- Code duplicate detection and removal
- Cross-codebase pattern analysis and comparisons
- Semantic code similarity searches
- Function/class dependency mapping
- Import optimization and unused code detection
- Architecture pattern identification
- Code quality consistency analysis
- Dead code elimination assistance
- Refactoring opportunity identification

## 🔐 Secrets Management Requirements

**IMPLEMENT COMPREHENSIVE SECRETS MANAGEMENT SYSTEM**

### Dual-Scope Architecture
- **Chat-scoped**: Conversation-only secrets
- **General-scoped**: Available across all chats

### Features Required
- **Multiple input methods**: GUI secrets management tab + chat-based entry
- **Secret types**: SSH keys, passwords, API keys for agent resource access
- **Transfer capability**: Move chat secrets to general pool when needed
- **Cleanup dialogs**: On chat deletion, prompt for secret/file transfer or deletion
- **Security isolation**: Chat secrets only accessible within originating conversation
- **Agent integration**: Seamless access to appropriate secrets based on scope
