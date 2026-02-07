# Long-Running Operations Architecture for AutoBot

## Overview

This document describes the comprehensive timeout architecture implemented for AutoBot's long-running operations. The framework provides intelligent timeout management, checkpoint/resume capabilities, real-time progress tracking, and operation-specific handling to ensure that operations "either finish or fail" rather than timing out prematurely.

## Problem Statement

Previously, AutoBot had several issues with long-running operations:

- **Premature Timeouts**: Fixed timeouts (30s, 60s) that were inadequate for large operations
- **Lost Work**: No checkpoint/resume capabilities meant starting over on failures
- **No Progress Visibility**: Users had no insight into operation progress
- **Poor Resource Management**: No control over concurrent operations
- **Inflexible Timeout Handling**: One-size-fits-all timeout approach

## Solution Architecture

### Core Components

#### 1. Long-Running Operations Framework (`autobot-user-backend/utils/long_running_operations_framework.py`)

**Key Features:**
- **Dynamic Timeout Profiles**: Timeouts based on operation type and estimated complexity
- **Checkpoint/Resume System**: Automatic checkpointing with Redis and filesystem storage
- **Real-Time Progress Tracking**: WebSocket broadcasting for live updates
- **Background Operation Management**: Concurrent execution with resource control
- **Operation-Specific Handlers**: Tailored handling for different operation types

**Operation Types Supported:**
```python
class OperationType(Enum):
    CODEBASE_INDEXING = "codebase_indexing"
    CODE_ANALYSIS = "code_analysis"
    DEPENDENCY_ANALYSIS = "dependency_analysis"
    SECURITY_SCAN = "security_scan"
    PERFORMANCE_PROFILING = "performance_profiling"
    COMPREHENSIVE_TEST_SUITE = "comprehensive_test_suite"
    INTEGRATION_TESTING = "integration_testing"
    PERFORMANCE_TESTING = "performance_testing"
    LOAD_TESTING = "load_testing"
    KB_POPULATION = "kb_population"
    KB_OPTIMIZATION = "kb_optimization"
    VECTOR_INDEXING = "vector_indexing"
    SEMANTIC_ANALYSIS = "semantic_analysis"
    BACKUP_OPERATION = "backup_operation"
    MIGRATION_OPERATION = "migration_operation"
    CLEANUP_OPERATION = "cleanup_operation"
    MONITORING_COLLECTION = "monitoring_collection"
```

**Dynamic Timeout Configuration:**
```python
OPERATION_TIMEOUTS = {
    OperationType.CODEBASE_INDEXING: {
        "base_timeout": 3600,  # 1 hour base
        "per_file_timeout": 10,  # 10 seconds per file
        "max_timeout": 14400,  # 4 hours maximum
        "checkpoint_interval": 300,  # 5 minutes
        "progress_report_interval": 30,  # 30 seconds
        "failure_threshold": 5,  # Max failures before abort
    },
    OperationType.COMPREHENSIVE_TEST_SUITE: {
        "base_timeout": 2400,  # 40 minutes base
        "per_test_timeout": 120,  # 2 minutes per test
        "max_timeout": 10800,  # 3 hours maximum
        "checkpoint_interval": 600,  # 10 minutes
        "progress_report_interval": 60,  # 1 minute
        "failure_threshold": 10,
    },
    # ... other operation types
}
```

#### 2. Checkpoint System

**Features:**
- **Automatic Checkpointing**: Saves state at configurable intervals
- **Dual Storage**: Redis for speed, filesystem for persistence
- **Resume Capability**: Restart from exact point of interruption
- **Context Preservation**: Maintains operation state and intermediate results

**Checkpoint Data Structure:**
```python
@dataclass
class OperationCheckpoint:
    operation_id: str
    checkpoint_id: str
    timestamp: datetime
    progress_percentage: float
    processed_items: int
    total_items: int
    intermediate_results: Dict[str, Any]
    context_data: Dict[str, Any]
    next_step: str
    metadata: Dict[str, Any]
```

#### 3. Progress Tracking

**Real-Time Updates:**
- WebSocket broadcasting for live UI updates
- Detailed progress metrics with performance data
- Estimated completion times
- Step-by-step operation status

**Progress Data:**
```python
@dataclass
class OperationProgress:
    operation_id: str
    current_step: str
    progress_percentage: float
    processed_items: int
    total_items: int
    estimated_completion: Optional[datetime]
    performance_metrics: Dict[str, Any]
    status_message: str
    detailed_status: Dict[str, Any]
```

#### 4. FastAPI Integration (`autobot-user-backend/api/long_running_operations.py`)

**API Endpoints:**
- `POST /api/operations/codebase/index` - Start codebase indexing
- `POST /api/operations/testing/comprehensive` - Start test suite
- `POST /api/operations/knowledge-base/populate` - Populate KB
- `POST /api/operations/security/scan` - Security scanning
- `GET /api/operations/{operation_id}` - Get operation status
- `GET /api/operations/` - List operations with filtering
- `POST /api/operations/{operation_id}/cancel` - Cancel operation
- `POST /api/operations/{operation_id}/resume` - Resume from checkpoint
- `WebSocket /api/operations/{operation_id}/progress` - Real-time updates

### Architecture Benefits

#### 1. Intelligent Timeout Management
- **Before**: Fixed 30-second timeout for all operations
- **After**: Dynamic timeouts (1-4 hours) based on operation complexity

#### 2. Resilient Operations
- **Before**: Lost all work on timeout/failure
- **After**: Resume from checkpoint, never lose progress

#### 3. User Visibility
- **Before**: No progress indication
- **After**: Real-time progress with detailed metrics

#### 4. Resource Management
- **Before**: No concurrency control
- **After**: Configurable concurrent operation limits

#### 5. Operation-Specific Handling
- **Before**: One-size-fits-all approach
- **After**: Tailored handling per operation type

## Usage Examples

### 1. Codebase Indexing with Checkpoint/Resume

```python
# Enhanced indexing operation
async def enhanced_indexing_operation(context: OperationExecutionContext):
    codebase_path = Path("/home/kali/Desktop/AutoBot")
    file_patterns = ["*.py", "*.js", "*.vue", "*.ts"]

    # Check if resuming from checkpoint
    if context.should_resume():
        checkpoint_data = context.get_resume_data()
        processed_files = checkpoint_data.intermediate_results.get("processed_files", [])
        start_index = len(processed_files)
        logger.info(f"Resuming indexing from file {start_index}")
    else:
        processed_files = []
        start_index = 0

    # Process files with progress tracking
    for i, file_path in enumerate(all_files[start_index:], start_index):
        file_info = await process_file(file_path)
        indexed_files.append(file_info)

        # Update progress
        await context.update_progress(
            f"Indexing {file_path.name}",
            i + 1,
            total_files,
            {"files_per_second": files_per_second},
            f"Processed {i + 1} of {total_files} files"
        )

        # Checkpoint every 100 files
        if (i + 1) % 100 == 0:
            await context.save_checkpoint(
                {"processed_files": processed_files + indexed_files},
                f"file_{i + 1}"
            )
```

### 2. Migration from Existing Timeout Operations

```python
# Decorator-based migration
@migrate_timeout_operation(
    OperationType.CODEBASE_INDEXING,
    estimated_items=1000
)
async def index_codebase(path: str, patterns: List[str]):
    """Automatically migrated to long-running framework"""
    # Original implementation
    return await perform_indexing(path, patterns)

# Usage (no changes needed)
result = await index_codebase("/path/to/code", ["*.py"])
```

### 3. Real-Time Progress Monitoring

```javascript
// Frontend WebSocket integration
const ws = new WebSocket(`ws://localhost:8001/api/operations/${operationId}/progress`);

ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    if (update.type === 'progress_update') {
        updateProgressBar(update.data.progress_percentage);
        updateStatusMessage(update.data.status_message);
    }
};
```

## Operation Examples

### 1. Codebase Indexing
- **Dynamic Timeout**: 1-4 hours based on file count
- **Checkpoints**: Every 100 files processed
- **Progress**: Files per second, current file, completion estimate
- **Resume**: From last processed file

### 2. Comprehensive Test Suite
- **Dynamic Timeout**: 40 minutes to 3 hours based on test count
- **Checkpoints**: Every 10 tests completed
- **Progress**: Test results, pass/fail rate, current test
- **Resume**: From last completed test

### 3. Security Scanning
- **Dynamic Timeout**: 45 minutes to 3 hours based on files to scan
- **Checkpoints**: Every 50 files scanned
- **Progress**: Vulnerabilities found, scan type, current file
- **Resume**: From last scanned file

## Migration Guide

### Step 1: Identify Timeout-Sensitive Operations

Look for patterns like:
```python
# Problematic pattern
try:
    result = await asyncio.wait_for(long_operation(), timeout=30.0)
except asyncio.TimeoutError:
    return {"error": "Operation timed out"}
```

### Step 2: Migrate to Long-Running Framework

```python
# Enhanced pattern
@migrate_timeout_operation(OperationType.CODE_ANALYSIS)
async def long_operation(progress_callback=None):
    # Add progress tracking
    if progress_callback:
        await progress_callback("Starting", 0, 100)

    # Original logic with progress updates
    for i in range(100):
        # Do work
        if progress_callback:
            await progress_callback(f"Step {i}", i, 100)

    return result
```

### Step 3: Update API Endpoints

```python
# Before
@router.post("/analyze")
async def analyze_code():
    try:
        result = await asyncio.wait_for(analyze(), timeout=30)
        return result
    except asyncio.TimeoutError:
        raise HTTPException(500, "Analysis timed out")

# After
@router.post("/analyze")
async def analyze_code():
    operation_id = await create_analysis_operation()
    return {"operation_id": operation_id}
```

## Performance Characteristics

### Timeout Improvements
- **Knowledge Base Indexing**: 30s → 1-4 hours (dynamic)
- **Test Suite Execution**: 10 minutes → 40 minutes-3 hours (dynamic)
- **Security Scanning**: 5 minutes → 45 minutes-3 hours (dynamic)

### Checkpoint Overhead
- **Storage**: ~1-5KB per checkpoint
- **Performance**: <100ms checkpoint save time
- **Frequency**: Configurable (every 100 files, 10 tests, etc.)

### Concurrency Control
- **Max Concurrent Operations**: 3 (configurable)
- **Resource Management**: Memory and CPU usage monitoring
- **Priority Scheduling**: High/Normal/Low priority queues

## Testing

Run the comprehensive test suite:

```bash
# Test all functionality
python scripts/test_long_running_operations.py --demo-type all

# Test specific components
python scripts/test_long_running_operations.py --demo-type indexing
python scripts/test_long_running_operations.py --demo-type testing
python scripts/test_long_running_operations.py --demo-type checkpoint
```

## Integration with AutoBot

The long-running operations framework is integrated into AutoBot's backend:

1. **Backend Integration**: Added to `backend/fast_app_factory_fix.py`
2. **API Endpoints**: Available at `/api/operations/*`
3. **WebSocket Support**: Real-time progress updates
4. **Migration Examples**: Ready-to-use migration patterns

## Future Enhancements

1. **Advanced Monitoring**: Prometheus metrics integration
2. **Load Balancing**: Multiple operation worker instances
3. **Persistence**: Database storage for operation history
4. **UI Integration**: Rich progress displays in frontend
5. **Auto-scaling**: Dynamic resource allocation based on load

## Conclusion

The long-running operations architecture transforms AutoBot's timeout-prone operations into robust, user-friendly experiences. Operations now "either finish or fail" gracefully, with full checkpoint/resume capabilities and real-time progress tracking.

Key benefits:
- ✅ **No More Premature Timeouts**: Dynamic timeouts based on operation complexity
- ✅ **Zero Work Loss**: Checkpoint/resume ensures no lost progress
- ✅ **Full Visibility**: Real-time progress with detailed metrics
- ✅ **Resource Control**: Proper concurrent operation management
- ✅ **Easy Migration**: Simple patterns to upgrade existing operations

This architecture ensures that large operations (codebase indexing, comprehensive testing, security scans) can run for hours when necessary while providing users with confidence that progress is being made and work won't be lost.
