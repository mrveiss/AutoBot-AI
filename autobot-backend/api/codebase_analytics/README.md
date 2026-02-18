# Codebase Analytics Module

This directory contains the refactored `codebase_analytics` API module, split from the original monolithic file (`codebase_analytics.py`, 2996 lines) into a modular structure.

## Module Structure

```
codebase_analytics/
├── __init__.py          (48 lines)   - Module exports and interface
├── models.py           (54 lines)   - Pydantic models (CodebaseStats, ProblemItem, etc.)
├── storage.py         (109 lines)   - Redis and ChromaDB utilities
├── analyzers.py       (729 lines)   - Code analysis functions
├── scanner.py         (628 lines)   - Codebase scanning and indexing
└── routes.py         (1552 lines)   - FastAPI router endpoints (14 routes)
```

## Components

### 1. models.py
Pydantic models for API request/response:
- `CodebaseStats` - Statistics about the codebase
- `ProblemItem` - Code problems and issues
- `HardcodeItem` - Hardcoded values
- `DeclarationItem` - Code declarations (functions, classes, variables)

### 2. storage.py
Storage layer utilities:
- `get_redis_connection()` - Redis client for analytics (follows CLAUDE.md policy)
- `get_code_collection()` - ChromaDB collection for code storage
- `InMemoryStorage` - In-memory fallback storage class

### 3. analyzers.py
Code analysis functions:
- `detect_hardcodes_and_debt_with_llm()` - LLM-based semantic analysis (~85 lines)
- `detect_race_conditions()` - Race condition detection in Python code (~260 lines)
- `analyze_python_file()` - Comprehensive Python file analysis (~260 lines)
- `analyze_javascript_vue_file()` - JS/Vue file analysis (~100 lines)

### 4. scanner.py
Codebase scanning and indexing:
- `scan_codebase()` - Scan entire codebase for analysis (~200 lines)
- `do_indexing_with_progress()` - Background indexing with progress tracking (~400 lines)
- Global state management (locks, task tracking)

### 5. routes.py
FastAPI router with 14 endpoints (~1552 lines):
1. `POST /codebase/index` - Start indexing
2. `GET /codebase/index/status/{task_id}` - Get indexing status
3. `GET /codebase/index/current` - Get current indexing job
4. `POST /codebase/index/cancel` - Cancel indexing
5. `GET /codebase/stats` - Get codebase statistics
6. `GET /codebase/hardcodes` - Get hardcoded values
7. `GET /codebase/problems` - Get code problems
8. `GET /codebase/analytics/charts` - Get chart data
9. `GET /codebase/analytics/dependencies` - Get dependencies
10. `GET /codebase/analytics/import-tree` - Get import tree
11. `GET /codebase/analytics/call-graph` - Get call graph
12. `GET /codebase/declarations` - Get code declarations
13. `GET /codebase/duplicates` - Get duplicate code
14. `DELETE /codebase/cache` - Clear cache

## Backward Compatibility

All imports from the original module still work:

```python
# These imports still work exactly as before
from backend.api.codebase_analytics import router
from backend.api.codebase_analytics import get_redis_connection, get_code_collection
from backend.api.codebase_analytics import analyze_python_file, analyze_javascript_vue_file
from backend.api.codebase_analytics import CodebaseStats, ProblemItem, HardcodeItem
```

## Integration

The module is integrated into the main application via:
- `backend/initialization/routers.py` - Router registration
- `backend/api/analytics_debt.py` - Uses storage utilities

## Testing

Run module tests:
```bash
python3 -m pytest tests/unit/test_api_endpoint_migrations.py -k codebase
```

## Original File

The original monolithic file is backed up at:
- `backend/api/codebase_analytics.py.bak` (2996 lines)
