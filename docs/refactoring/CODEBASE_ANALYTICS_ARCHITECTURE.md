# Codebase Analytics API Architecture

## Module Structure

```
backend/api/codebase_analytics/
│
├── __init__.py                      # Package initialization
├── router.py                        # Main router (combines all sub-routers)
├── routes.py                        # Backward compatibility wrapper
│
├── endpoints/                       # Modular endpoint definitions
│   ├── __init__.py                 # Endpoints package init
│   ├── shared.py                   # Shared utilities and constants
│   │   ├── INTERNAL_MODULE_PREFIXES
│   │   ├── STDLIB_MODULES
│   │   ├── _in_memory_storage
│   │   └── get_project_root()
│   │
│   ├── indexing.py                 # Indexing operations (4 endpoints)
│   │   ├── POST /index
│   │   ├── GET /index/status/{task_id}
│   │   ├── GET /index/current
│   │   └── POST /index/cancel
│   │
│   ├── stats.py                    # Statistics endpoints (3 endpoints)
│   │   ├── GET /stats
│   │   ├── GET /hardcodes
│   │   └── GET /problems
│   │
│   ├── charts.py                   # Chart data (1 endpoint)
│   │   └── GET /analytics/charts
│   │
│   ├── dependencies.py             # Dependency analysis (1 endpoint)
│   │   └── GET /analytics/dependencies
│   │
│   ├── import_tree.py              # Import relationships (1 endpoint)
│   │   └── GET /analytics/import-tree
│   │
│   ├── call_graph.py               # Function call graph (1 endpoint)
│   │   └── GET /analytics/call-graph
│   │
│   ├── declarations.py             # Code declarations (1 endpoint)
│   │   └── GET /declarations
│   │
│   ├── duplicates.py               # Duplicate detection (2 endpoints)
│   │   ├── GET /duplicates
│   │   └── GET /config-duplicates
│   │
│   └── cache.py                    # Cache management (1 endpoint)
│       └── DELETE /cache
│
├── storage.py                      # Storage layer (Redis/ChromaDB)
├── scanner.py                      # Code scanning logic
├── models.py                       # Data models
├── analyzers.py                    # Code analyzers
└── config_duplication_detector.py # Config duplicate detection
```

## Data Flow

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                   │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│        backend/api/codebase_analytics/routes.py         │
│              (Backward Compatibility Layer)              │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│        backend/api/codebase_analytics/router.py         │
│                  (Main Router - 34 lines)                │
│     Combines all sub-routers with /codebase prefix      │
└─────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ indexing.py │    │  stats.py   │    │ charts.py   │
│ 282 lines   │    │ 256 lines   │    │ 188 lines   │
│ 4 endpoints │    │ 3 endpoints │    │ 1 endpoint  │
└─────────────┘    └─────────────┘    └─────────────┘
        │                  │                   │
        └──────────────────┼───────────────────┘
                           ▼
        ┌──────────────────────────────────────┐
        │     endpoints/shared.py              │
        │  (Common utilities & constants)      │
        │  - INTERNAL_MODULE_PREFIXES          │
        │  - STDLIB_MODULES                    │
        │  - _in_memory_storage                │
        │  - get_project_root()                │
        └──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ storage.py  │    │ scanner.py  │    │ models.py   │
│  (Redis/    │    │  (Indexing  │    │  (Data      │
│  ChromaDB)  │    │   Logic)    │    │  Models)    │
└─────────────┘    └─────────────┘    └─────────────┘
```

## Endpoint Categories

### 🔄 Indexing Operations
- **Purpose**: Background indexing of codebase
- **Module**: `endpoints/indexing.py`
- **Endpoints**: 4
- **Key Features**:
  - Async task management
  - Progress tracking
  - Cancellation support
  - Single-task enforcement

### 📊 Statistics & Analysis
- **Purpose**: Codebase metrics and statistics
- **Module**: `endpoints/stats.py`
- **Endpoints**: 3
- **Storage**: ChromaDB (primary), Redis (fallback)
- **Data Types**:
  - File counts and types
  - Lines of code
  - Functions and classes
  - Hardcoded values
  - Code problems

### 📈 Visualization Data
- **Purpose**: Chart-ready aggregated data
- **Module**: `endpoints/charts.py`
- **Endpoints**: 1
- **Visualization Types**:
  - Problem type distribution (pie chart)
  - Severity counts (bar chart)
  - Race conditions (donut chart)
  - Top problematic files (horizontal bar)

### 🔗 Dependency Analysis
- **Purpose**: Module and import relationships
- **Modules**:
  - `endpoints/dependencies.py` (full dependency graph)
  - `endpoints/import_tree.py` (bidirectional tree)
  - `endpoints/call_graph.py` (function calls)
- **Endpoints**: 3
- **Analysis Types**:
  - Import relationships
  - Circular dependencies
  - External dependencies
  - Function call graphs

### 📝 Code Declarations
- **Purpose**: Function/class declarations
- **Module**: `endpoints/declarations.py`
- **Endpoints**: 1
- **Data**: Functions, classes, variables

### 🔍 Duplicate Detection
- **Purpose**: Code and config duplication
- **Module**: `endpoints/duplicates.py`
- **Endpoints**: 2
- **Detection Types**:
  - Semantic code similarity
  - Configuration value duplicates

### 🗑️ Cache Management
- **Purpose**: Clear cached analysis data
- **Module**: `endpoints/cache.py`
- **Endpoints**: 1
- **Storage**: Redis/In-memory

## Error Handling

All endpoints use the `@with_error_handling` decorator:

```python
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="endpoint_name",
    error_code_prefix="CODEBASE",
)
```

This provides:
- Consistent error responses
- Automatic logging
- Error categorization
- Client-friendly error messages

## Storage Strategy

### Primary: ChromaDB
- Vector storage for semantic search
- Metadata for structured queries
- Used by: stats, problems, declarations, duplicates

### Fallback: Redis
- Key-value storage
- Used when ChromaDB unavailable
- Cache for quick lookups

### In-Memory
- Last resort fallback
- Temporary storage
- Lost on restart

## Performance Optimizations

### Issue #326: O(1) Module Lookup
```python
INTERNAL_MODULE_PREFIXES = {"src", "backend", "autobot"}  # Set for O(1) lookup
is_internal = module in INTERNAL_MODULE_PREFIXES
```

### File Limiting
- Dependencies: 500 files max
- Call graph: 300 files max
- Import tree: 500 files max

### Result Limiting
- Nodes: 500 max
- Edges: 2000 max
- Import relationships: 1000 max

## Import Patterns

### For API Consumers (Backward Compatible)
```python
from backend.api.codebase_analytics.routes import router
```

### For New Development
```python
from backend.api.codebase_analytics.router import router
from backend.api.codebase_analytics.endpoints import indexing
from backend.api.codebase_analytics.endpoints.shared import get_project_root
```

## Testing Strategy

### Unit Tests
- Test each endpoint module independently
- Mock storage layer
- Verify error handling

### Integration Tests
- Test router composition
- Verify all endpoints registered
- Test backward compatibility

### Example
```python
from backend.api.codebase_analytics.router import router

# Verify endpoint count
assert len(router.routes) == 15

# Verify all paths exist
paths = [route.path for route in router.routes]
assert "/codebase/index" in paths
assert "/codebase/stats" in paths
```

## Future Enhancements

### Potential Additions
- `/codebase/analytics/complexity` - Code complexity metrics
- `/codebase/analytics/test-coverage` - Test coverage analysis
- `/codebase/analytics/performance` - Performance hotspots
- `/codebase/analytics/security` - Security vulnerability scan

### Architecture Support
Each new endpoint can be added as a new file in `endpoints/`:
1. Create `endpoints/new_feature.py`
2. Define router and endpoints
3. Include in `router.py`
4. Update this documentation

## Maintenance

### Adding New Endpoint
1. Create new file in `endpoints/` directory
2. Import shared utilities from `endpoints/shared.py`
3. Define router: `router = APIRouter()`
4. Add endpoints with `@with_error_handling` decorator
5. Include router in `router.py`

### Modifying Existing Endpoint
1. Locate endpoint in appropriate module
2. Make changes preserving error handling
3. Test backward compatibility
4. Update documentation

### Removing Endpoint
1. Remove from endpoint module
2. Mark as deprecated for one release cycle
3. Remove after deprecation period
4. Update documentation

## Author

- mrveiss (Copyright 2025)

## Related Documentation

- `REFACTORING_SUMMARY.md` - Refactoring details
- `../../../docs/api/COMPREHENSIVE_API_DOCUMENTATION.md` - Full API docs
- `../../README.md` - Backend API overview
