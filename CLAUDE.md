# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🚀 QUICK REFERENCE FOR CLAUDE CODE

### Critical Rules for Autonomous Operations
1. **ALWAYS** run flake8 checks before committing: `flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503`
2. **NEVER** hardcode values - use `src/config.py` for all configuration
3. **ALWAYS** test changes with: `./run_agent.sh --test-mode` before full deployment
4. **REQUIRED**: Update docstrings following Google style for any function changes
5. **CRITICAL**: Backup `data/` before schema changes to knowledge_base.db

### Immediate Safety Checks
```bash
# Before any code changes - verify system state
curl -s "http://localhost:8001/api/system/health" || echo "Backend not running"
docker ps | grep redis || echo "Redis not running"
ls data/knowledge_base.db || echo "Database missing"
```

### Emergency Recovery
```bash
# If system breaks during development
pkill -f uvicorn; docker stop autobot-redis
./setup_agent.sh --force-reinstall
./run_agent.sh
```

## 📋 PROJECT OVERVIEW

AutoBot is an enterprise-grade autonomous AI platform with Vue 3 frontend and FastAPI backend.

**Status**: Production-ready Phase 4 | **Architecture**: Microservices | **Stack**: Python 3.10.13, Vue 3, Redis

### Key Components for Code Changes
```
src/
├── orchestrator.py      # ⚠️  CRITICAL - Task planning engine
├── llm_interface.py     # 🔧 COMMON - LLM integrations
├── knowledge_base.py    # 📊 DATA - RAG + ChromaDB
├── worker_node.py       # ⚙️  BACKGROUND - Task execution
├── gui_controller.py    # 🖥️  GUI - Automation layer
└── config.py           # ⚙️  CONFIG - All settings

backend/api/
├── chat.py             # 💬 API - Chat endpoints
├── goal.py            # 🎯 API - Task planning
└── knowledge_base.py  # 🔍 API - KB operations
```

## 🛠️ DEVELOPMENT COMMANDS

### Essential Operations
```bash
# Complete setup (run once)
./setup_agent.sh

# Start full system
./run_agent.sh

# Development mode (auto-reload)
source venv/bin/activate && python main.py --dev

# Code quality check (REQUIRED before commits)
flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503
black src/ backend/ --line-length=88
isort src/ backend/

# Quick tests
python -m pytest tests/ -v --tb=short
```

### Frontend Development
```bash
cd autobot-vue
npm run dev          # Development server
npm run lint         # ESLint + oxlint
npm run format       # Prettier
npm run type-check   # TypeScript validation
npm run test:unit    # Vitest tests
```

## 🏗️ CODE QUALITY REQUIREMENTS

### Flake8 Configuration (.flake8 file)
```ini
[flake8]
max-line-length = 88
extend-ignore =
    E203,  # Whitespace before ':'
    W503,  # Line break before binary operator
    F401,  # Module imported but unused (in __init__.py)
exclude =
    .git,
    __pycache__,
    venv,
    build,
    dist,
    *.egg-info
```

### Python Code Standards
```python
# ✅ CORRECT: Function with proper docstring and typing
def process_knowledge_query(
    query: str,
    limit: int = 5,
    similarity_threshold: float = 0.7
) -> List[Dict[str, Any]]:
    """Search knowledge base with vector similarity.

    Args:
        query: Search query string
        limit: Maximum results to return
        similarity_threshold: Minimum similarity score (0.0-1.0)

    Returns:
        List of matching documents with metadata

    Raises:
        ValueError: If similarity_threshold not in valid range
    """
    if not 0.0 <= similarity_threshold <= 1.0:
        raise ValueError("similarity_threshold must be between 0.0 and 1.0")

    # Implementation here...
    return results

# ❌ INCORRECT: No typing, hardcoded values, no docstring
def search_kb(q, n=5):
    return chroma_client.query(q, n_results=n, where={"db": "main"})
```

### Import Organization (isort compatible)
```python
# Standard library
import asyncio
import json
from typing import Dict, List, Optional

# Third-party packages
import redis
import uvicorn
from fastapi import FastAPI, HTTPException

# Local imports
from src.config import Config
from src.llm_interface import LLMInterface
```

## 🔧 COMMON DEVELOPMENT SCENARIOS

### Adding New API Endpoints
1. **Create route handler** in `backend/api/[module].py`:
```python
@router.post("/new-endpoint")
async def new_endpoint(request: NewRequest) -> Dict[str, Any]:
    """Handle new functionality.

    Args:
        request: Validated request model

    Returns:
        Response with operation results
    """
    try:
        result = await some_operation(request.data)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"New endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

2. **Add request/response models** in same file:
```python
class NewRequest(BaseModel):
    data: str
    options: Optional[Dict[str, Any]] = None
```

3. **Update frontend service** in `autobot-vue/src/services/api.ts`:
```typescript
export const newEndpoint = async (data: NewRequest): Promise<ApiResponse> => {
  return apiClient.post('/new-endpoint', data);
};
```

### Modifying Database Schema
```python
# ALWAYS backup before schema changes
import shutil
from datetime import datetime

# Backup database
backup_path = f"data/knowledge_base.db.backup.{datetime.now().isoformat()}"
shutil.copy("data/knowledge_base.db", backup_path)

# Make changes with proper migration
def migrate_database():
    """Migrate database to new schema version."""
    conn = sqlite3.connect("data/knowledge_base.db")
    cursor = conn.cursor()

    try:
        # Check current schema version
        cursor.execute("PRAGMA user_version")
        current_version = cursor.fetchone()[0]

        if current_version < 2:
            # Apply migration
            cursor.execute("ALTER TABLE documents ADD COLUMN new_field TEXT")
            cursor.execute("PRAGMA user_version = 2")

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
```

### Adding LLM Models
```python
# In src/llm_interface.py
def add_new_llm_provider(self, provider_name: str, config: Dict[str, Any]):
    """Add new LLM provider configuration.

    Args:
        provider_name: Unique identifier for provider
        config: Provider configuration dict

    Raises:
        ValueError: If provider already exists
    """
    if provider_name in self.providers:
        raise ValueError(f"Provider {provider_name} already exists")

    # Validate required config keys
    required_keys = ["api_key", "base_url", "model_name"]
    if not all(key in config for key in required_keys):
        raise ValueError(f"Missing required config keys: {required_keys}")

    self.providers[provider_name] = LLMProvider(config)
```

## 🚨 TROUBLESHOOTING GUIDE

### Backend Issues

**Import Errors**
```bash
# Symptom: ModuleNotFoundError
# Fix: Check Python path and virtual environment
source venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH="$PWD:$PYTHONPATH"
```

**Port Already in Use**
```bash
# Find and kill process using port 8001
lsof -ti:8001 | xargs kill -9
# Or use different port
export AUTOBOT_BACKEND_PORT=8002
```

**Redis Connection Failed**
```bash
# Check Redis container status
docker ps | grep redis
# Restart Redis
docker stop autobot-redis && docker rm autobot-redis
./run_agent.sh  # Will recreate Redis container
```

**Database Corruption**
```bash
# Restore from backup
cp data/knowledge_base.db.backup.* data/knowledge_base.db
# Or reinitialize
rm data/knowledge_base.db && python -c "from src.knowledge_base import KnowledgeBase; KnowledgeBase()"
```

### Frontend Issues

**Build Failures**
```bash
cd autobot-vue
rm -rf node_modules package-lock.json
npm install
npm run type-check  # Fix TypeScript errors first
```

**WebSocket Connection Issues**
```javascript
// Check connection status in browser console
const ws = new WebSocket('ws://localhost:8001/ws');
ws.onopen = () => console.log('Connected');
ws.onerror = (e) => console.error('WebSocket error:', e);
```

### Performance Issues

**Slow Knowledge Base Queries**
```python
# Add query logging to identify bottlenecks
import time
start_time = time.time()
results = chroma_collection.query(query_texts=[query], n_results=limit)
query_time = time.time() - start_time
logger.info(f"Query took {query_time:.2f}s for '{query}'")
```

**Memory Leaks**
```bash
# Monitor memory usage
ps aux | grep python | grep autobot
# Check for unclosed connections
lsof -p $(pgrep -f "python main.py")
```

## ⚠️ COMMON PITFALLS AND BEST PRACTICES

### Configuration Management
```python
# ❌ NEVER hardcode values
api_key = "sk-1234567890abcdef"  # pragma: allowlist secret
redis_host = "localhost"

# ✅ ALWAYS use config system
from src.config import Config
config = Config()
api_key = config.get("openai.api_key")
redis_host = config.get("redis.host", "localhost")
```

### Error Handling
```python
# ❌ NEVER catch all exceptions silently
try:
    result = risky_operation()
except:
    pass

# ✅ ALWAYS log errors and handle specifically
try:
    result = risky_operation()
except SpecificException as e:
    logger.error(f"Operation failed: {e}")
    raise HTTPException(status_code=400, detail=f"Operation failed: {e}")
except Exception as e:
    logger.critical(f"Unexpected error: {e}")
    raise HTTPException(status_code=500, detail="Internal server error")
```

### Async/Await Patterns
```python
# ❌ INCORRECT: Blocking operations in async functions
async def bad_example():
    time.sleep(5)  # Blocks event loop

# ✅ CORRECT: Non-blocking operations
async def good_example():
    await asyncio.sleep(5)  # Non-blocking
```

### Database Connections
```python
# ❌ INCORRECT: Not closing connections
def query_database():
    conn = sqlite3.connect("data/knowledge_base.db")
    return conn.execute("SELECT * FROM documents").fetchall()

# ✅ CORRECT: Always use context managers
def query_database():
    with sqlite3.connect("data/knowledge_base.db") as conn:
        return conn.execute("SELECT * FROM documents").fetchall()
```

## 🔍 TESTING STRATEGIES

### Unit Tests
```python
# Test file: tests/test_knowledge_base.py
import pytest
from src.knowledge_base import KnowledgeBase

@pytest.fixture
def kb():
    """Create test knowledge base instance."""
    return KnowledgeBase(db_path=":memory:")  # In-memory for tests

def test_search_functionality(kb):
    """Test knowledge base search returns expected results."""
    # Add test document
    kb.add_document("Test content", {"source": "test"})

    # Search and verify
    results = kb.search("Test", limit=1)
    assert len(results) == 1
    assert "Test content" in results[0]["content"]
```

### Integration Tests
```bash
# Test API endpoints
curl -X POST "http://localhost:8001/api/knowledge_base/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "limit": 1}' | \
  python3 -c "import sys,json; data=json.load(sys.stdin); exit(0 if data['success'] else 1)"
```

## 🎯 CLAUDE CODE SPECIFIC GUIDANCE

### Pre-Change Checklist
- [ ] Verify system is running: `curl -s http://localhost:8001/api/system/health`
- [ ] Check current git status: `git status --porcelain`
- [ ] Run existing tests: `python -m pytest tests/ --tb=short -q`
- [ ] Backup critical data if changing schemas

### Post-Change Validation
- [ ] Run flake8: `flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503`
- [ ] Run type checking: `mypy src/ backend/ --ignore-missing-imports`
- [ ] Test API endpoints affected by changes
- [ ] Verify frontend compilation: `cd autobot-vue && npm run build`
- [ ] Test full system restart: `./run_agent.sh --test-mode`

### Safe Change Patterns
1. **Add new functionality** without modifying existing working code
2. **Use feature flags** for experimental features
3. **Implement gradual rollouts** with configuration switches
4. **Always provide rollback paths** for database changes
5. **Log all significant operations** for debugging

### File Priority for Changes
**🔴 HIGH RISK** (require extra testing):
- `src/orchestrator.py` - Core task planning
- `src/knowledge_base.py` - Data layer
- `backend/app_factory.py` - Application bootstrap

**🟡 MEDIUM RISK** (standard testing):
- `backend/api/*.py` - API endpoints
- `src/llm_interface.py` - LLM integrations
- `src/config.py` - Configuration

**🟢 LOW RISK** (basic testing):
- `src/diagnostics.py` - Monitoring
- Documentation files
- Frontend components (isolated)

## 📚 ENVIRONMENT SETUP

### Development Environment
```bash
# Set development mode
export AUTOBOT_DEBUG=true
export AUTOBOT_LOG_LEVEL=DEBUG
export AUTOBOT_BACKEND_RELOAD=true

# Development database (separate from production)
export AUTOBOT_DATABASE_PATH=data/knowledge_base_dev.db
```

### Production Environment
```bash
# Optimize for production
export AUTOBOT_DEBUG=false
export AUTOBOT_LOG_LEVEL=INFO
export AUTOBOT_WORKERS=4
export AUTOBOT_BACKEND_RELOAD=false
```

### Testing Environment
```bash
# Isolated testing setup
export AUTOBOT_DATABASE_PATH=:memory:
export AUTOBOT_REDIS_DB=15  # Separate Redis DB for tests
export AUTOBOT_FILE_ROOT=tests/fixtures/files
```

---

**Remember**: This AutoBot platform handles sensitive operations. Always prioritize stability and data integrity over speed of implementation.
