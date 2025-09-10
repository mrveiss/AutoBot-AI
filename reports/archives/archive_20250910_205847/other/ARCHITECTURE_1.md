# Code Index MCP System Architecture

## Overview

Code Index MCP is a Model Context Protocol (MCP) server that provides intelligent code indexing and analysis capabilities. The system follows SCIP (Source Code Intelligence Protocol) standards and uses a service-oriented architecture with clear separation of concerns.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        MCP Interface Layer                      │
├─────────────────────────────────────────────────────────────────┤
│                        Service Layer                           │
├─────────────────────────────────────────────────────────────────┤
│                        SCIP Core Layer                         │
├─────────────────────────────────────────────────────────────────┤
│                     Language Strategies                        │
├─────────────────────────────────────────────────────────────────┤
│                    Technical Tools Layer                       │
└─────────────────────────────────────────────────────────────────┘
```

## Layer Responsibilities

### 1. MCP Interface Layer (`server.py`)
**Purpose**: Exposes MCP tools and handles protocol communication

**Key Components**:
- MCP tool definitions (`@mcp.tool()`)
- Error handling and response formatting
- User interaction and guidance

**MCP Tools**:
- `set_project_path` - Initialize project indexing
- `find_files` - File discovery with patterns
- `get_file_summary` - File analysis and metadata
- `search_code_advanced` - Content search across files
- `refresh_index` - Manual index rebuilding
- `get_file_watcher_status` - File monitoring status
- `configure_file_watcher` - File watcher settings

### 2. Service Layer (`services/`)
**Purpose**: Business logic orchestration and workflow management

**Key Services**:
- `ProjectManagementService` - Project lifecycle and initialization
- `FileWatcherService` - Real-time file monitoring and auto-refresh
- `IndexManagementService` - Index rebuild operations
- `CodeIntelligenceService` - File analysis and symbol intelligence
- `FileDiscoveryService` - File pattern matching and discovery
- `SearchService` - Advanced code search capabilities

**Architecture Pattern**: Service delegation with clear business boundaries

### 3. SCIP Core Layer (`scip/core/`)
**Purpose**: Language-agnostic SCIP protocol implementation

**Core Components**:
- `SCIPSymbolManager` - Standard SCIP symbol ID generation
- `LocalReferenceResolver` - Cross-file reference resolution
- `PositionCalculator` - AST/Tree-sitter position conversion
- `MonikerManager` - External package dependency handling

**Standards Compliance**: Full SCIP protocol buffer implementation

### 4. Language Strategies (`scip/strategies/`)
**Purpose**: Language-specific code analysis using two-phase processing

**Strategy Pattern Implementation**:
- `BaseStrategy` - Abstract interface and common functionality
- `PythonStrategy` - Python AST analysis
- `JavaScriptStrategy` - JavaScript/TypeScript Tree-sitter analysis
- `JavaStrategy` - Java Tree-sitter analysis
- `ObjectiveCStrategy` - Objective-C Tree-sitter analysis
- `FallbackStrategy` - Generic text-based analysis

**Two-Phase Analysis**:
1. **Phase 1**: Symbol definition collection
2. **Phase 2**: Reference resolution and SCIP document generation

### 5. Technical Tools Layer (`tools/`)
**Purpose**: Low-level technical capabilities

**Tool Categories**:
- `filesystem/` - File system operations and pattern matching
- `scip/` - SCIP index operations and symbol analysis
- `config/` - Configuration and settings management
- `monitoring/` - File watching and system monitoring

## Data Flow Architecture

### File Analysis Workflow
```
User Request → Service Layer → SCIP Strategy → Core Components → SCIP Documents
```

### Index Management Workflow
```
File Changes → File Watcher → Index Management Service → Strategy Factory → Updated Index
```

### Search Workflow
```
Search Query → Search Service → Advanced Search Tools → Filtered Results
```

## SCIP Implementation Details

### Symbol ID Format
```
scip-{language} {manager} {package} [version] {descriptors}
```

**Examples**:
- Local: `scip-python local myproject src/main.py/MyClass#method().`
- External: `scip-python pip requests 2.31.0 sessions/Session#get().`

### Language Support Strategy

**Parsing Approaches**:
- **Python**: Native AST module
- **JavaScript/TypeScript**: Tree-sitter
- **Java**: Tree-sitter  
- **Objective-C**: Tree-sitter
- **Others**: Fallback text analysis

**Supported Code Intelligence**:
- Symbol definitions (functions, classes, variables)
- Import/export tracking
- Cross-file reference resolution
- External dependency management
- Position-accurate symbol ranges

## Configuration and Extensibility

### Package Manager Integration
- **Python**: pip, conda, poetry detection
- **JavaScript**: npm, yarn package.json parsing
- **Java**: Maven pom.xml, Gradle build files
- **Configuration-driven**: Easy addition of new package managers

### File Watcher System
- **Real-time monitoring**: Watchdog-based file system events
- **Debounced rebuilds**: 4-6 second batching of rapid changes
- **Configurable patterns**: Customizable include/exclude rules
- **Thread-safe**: ThreadPoolExecutor for concurrent rebuilds

## Performance Characteristics

### Indexing Performance
- **Incremental updates**: File-level granular rebuilds
- **Parallel processing**: Concurrent file analysis
- **Memory efficient**: Streaming SCIP document generation
- **Cache optimization**: Symbol table reuse across phases

### Search Performance
- **Advanced tools**: ripgrep, ugrep, ag integration
- **Pattern optimization**: Glob-based file filtering
- **Result streaming**: Large result set handling

## Error Handling and Reliability

### Fault Tolerance
- **Graceful degradation**: Continue indexing on individual file failures
- **Error isolation**: Per-file error boundaries
- **Recovery mechanisms**: Automatic retry on transient failures
- **Comprehensive logging**: Debug and audit trail support

### Validation
- **Input sanitization**: Path traversal protection
- **Range validation**: SCIP position boundary checking
- **Schema validation**: Protocol buffer structure verification

## Future Architecture Considerations

### Planned Enhancements
1. **Function Call Relationships**: Complete call graph analysis
2. **Type Information**: Enhanced semantic analysis
3. **Cross-repository Navigation**: Multi-project symbol resolution
4. **Language Server Protocol**: LSP compatibility layer
5. **Distributed Indexing**: Horizontal scaling support

### Extension Points
- **Custom strategies**: Plugin architecture for new languages
- **Analysis plugins**: Custom symbol analyzers
- **Export formats**: Multiple output format support
- **Integration APIs**: External tool connectivity

## Directory Structure

```
src/code_index_mcp/
├── server.py                   # MCP interface layer
├── services/                   # Business logic services
│   ├── project_management_service.py
│   ├── file_watcher_service.py
│   ├── index_management_service.py
│   ├── code_intelligence_service.py
│   └── ...
├── scip/                       # SCIP implementation
│   ├── core/                   # Language-agnostic core
│   │   ├── symbol_manager.py
│   │   ├── local_reference_resolver.py
│   │   ├── position_calculator.py
│   │   └── moniker_manager.py
│   ├── strategies/             # Language-specific strategies
│   │   ├── base_strategy.py
│   │   ├── python_strategy.py
│   │   ├── javascript_strategy.py
│   │   └── ...
│   └── factory.py              # Strategy selection
├── tools/                      # Technical capabilities
│   ├── filesystem/
│   ├── scip/
│   ├── config/
│   └── monitoring/
├── indexing/                   # Index management
└── utils/                      # Shared utilities
```

## Key Design Principles

1. **Standards Compliance**: Full SCIP protocol adherence
2. **Language Agnostic**: Core components independent of specific languages
3. **Extensible**: Easy addition of new languages and features
4. **Performance**: Efficient indexing and search operations
5. **Reliability**: Fault-tolerant with comprehensive error handling
6. **Maintainability**: Clear separation of concerns and modular design

---

*Last updated: 2025-01-14*
*Architecture version: 2.1.0*