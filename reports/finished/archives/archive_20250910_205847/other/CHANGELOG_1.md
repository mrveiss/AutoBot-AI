# Changelog

All notable changes to this project will be documented in this file.

## [2.1.1] - 2025-01-15

### Fixed
- **SCIP Java Strategy**: Simplified Java symbol analysis implementation
  - Refactored JavaStrategy to use streamlined symbol registration methods
  - Removed complex JavaAnalyzer and JavaRelationshipExtractor classes
  - Fixed symbol creation with basic identifier extraction
  - Removed relationships summary calculation that was causing issues
  - Added back to_scip_relationships method for compatibility
  - Streamlined Java AST processing to focus on core symbol definitions

### Improved
- **Code Maintainability**: Significantly reduced complexity in Java SCIP processing
- **Performance**: Faster Java file analysis with simplified approach
- **Reliability**: More stable symbol extraction without complex relationship tracking

## [2.1.0] - 2025-01-13

### Major SCIP Architecture Enhancement

This release completes the migration to SCIP-based code indexing with significant improvements to the core infrastructure and API simplification.

#### Core SCIP Infrastructure
- **Complete SCIP core components**: Added symbol_manager, position_calculator, reference_resolver, moniker_manager
- **Two-phase SCIP analysis**: Implemented symbol collection → reference resolution workflow
- **Unified index management**: New index_provider and unified_index_manager for seamless index operations
- **SCIP-compliant symbol IDs**: Standard symbol ID generation with cross-file reference support

#### Enhanced Strategy System
- **All language strategies SCIP-compliant**: Refactored Python, Java, JavaScript, Objective-C strategies
- **External symbol extraction**: Added dependency tracking and external symbol resolution
- **Proper SCIP classifications**: Implemented symbol roles and syntax kind detection
- **Robust file handling**: Enhanced encoding detection and error recovery

#### API Improvements
- **Simplified find_files response**: Returns clean file path lists instead of complex metadata objects
- **Enhanced SCIPSymbolAnalyzer**: Replaced legacy query tools with accurate symbol analysis
- **Improved logging**: Comprehensive logging throughout SCIP indexing pipeline

#### Dependency Updates
- **pathspec integration**: Better .gitignore parsing and file filtering
- **Updated requirements**: Added comprehensive dependency list for cross-platform support

#### Technical Improvements
- **Symbol analysis tools**: New inspection scripts for debugging and development
- **Enhanced error handling**: Better fallback strategies and error recovery
- **Testing improvements**: Updated sample projects for multilingual testing

#### Breaking Changes
- **find_files API**: Now returns `List[str]` instead of complex metadata dictionary
- **Internal architecture**: Significant refactoring of internal components (no user-facing impact)

## [2.0.0] - 2025-08-11

### 🚀 MAJOR RELEASE - SCIP Architecture Migration

This release represents a **complete architectural overhaul** of the code indexing system, migrating from language-specific analyzers to a unified SCIP-based approach.

#### ✨ New Architecture
- **Three-layer service architecture**: Service → Tool → Technical Components
- **Unified SCIP indexing**: Replace 8 language-specific analyzers with single SCIP protobuf system
- **Service-oriented design**: Clear separation of business logic, technical tools, and low-level operations
- **Composable components**: Modular design enabling easier testing and maintenance

#### 🔧 Technical Improvements
- **Tree-sitter AST parsing**: Replace regex-based analysis with proper AST parsing
- **SCIP protobuf format**: Industry-standard code intelligence format
- **Reduced complexity**: Simplified from 40K+ lines to ~1K lines of core logic
- **Better error handling**: Improved exception handling and validation
- **Enhanced logging**: Better debugging and monitoring capabilities

#### 📦 Backward Compatibility
- **MCP API unchanged**: All existing MCP tools work without modification
- **Automatic migration**: Legacy indexes automatically migrated to SCIP format
- **Same functionality**: All user-facing features preserved and enhanced
- **No breaking changes**: Seamless upgrade experience

#### 🗑️ Removed Components
- Language-specific analyzers (C, C++, C#, Go, Java, JavaScript, Objective-C, Python)
- Legacy indexing models and relationship management
- Complex duplicate detection and qualified name systems
- Obsolete builder and scanner components
- Demo files and temporary utilities

#### 🆕 New Services
- **ProjectManagementService**: Project lifecycle and configuration management
- **IndexManagementService**: Index building, rebuilding, and status monitoring
- **FileDiscoveryService**: Intelligent file discovery with pattern matching
- **CodeIntelligenceService**: Code analysis and summary generation
- **SystemManagementService**: File watcher and system configuration

#### 🛠️ New Tool Layer
- **SCIPIndexTool & SCIPQueryTool**: SCIP operations and querying
- **FileMatchingTool & FileSystemTool**: File system operations
- **ProjectConfigTool & SettingsTool**: Configuration management
- **FileWatcherTool**: Enhanced file monitoring capabilities

#### 📊 Performance Benefits
- **Faster indexing**: Tree-sitter parsing significantly faster than regex
- **Lower memory usage**: Streamlined data structures and processing
- **Better accuracy**: SCIP provides more precise code intelligence
- **Improved scalability**: Cleaner architecture supports larger codebases

#### 🔄 Migration Guide
Existing users can upgrade seamlessly:
1. System automatically detects legacy index format
2. Migrates to new SCIP format on first run
3. All existing functionality preserved
4. No manual intervention required

This release establishes a solid foundation for future enhancements while dramatically simplifying the codebase and improving performance.

## [1.2.1] - 2024-08-06

### Fixed
- **File Watcher**: Enhanced move event handling for modern editors (VS Code, etc.)
  - Fixed issue where files created via temp-then-move pattern weren't being detected
  - Improved event processing logic to exclusively check destination path for move events
  - Eliminated ambiguous fallback behavior that could cause inconsistent results

### Improved
- **Code Quality**: Comprehensive Pylint compliance improvements
  - Fixed all f-string logging warnings using lazy % formatting
  - Added proper docstrings to fallback classes
  - Fixed multiple-statements warnings
  - Moved imports to top-level following PEP 8 conventions
  - Added appropriate pylint disables for stub methods

### Technical Details
- Unified path checking logic across all event types
- Reduced code complexity in `should_process_event()` method
- Better error handling with consistent exception management
- Enhanced debugging capabilities with improved logging

## [1.2.0] - Previous Release

### Added
- Enhanced find_files functionality with filename search
- Performance improvements to file discovery
- Auto-refresh troubleshooting documentation

## [1.1.1] - Previous Release

### Fixed
- Various bug fixes and stability improvements

## [1.1.0] - Previous Release

### Added
- Initial file watcher functionality
- Cross-platform file system monitoring

## [1.0.0] - Initial Release

### Added
- Core MCP server implementation
- Code indexing and analysis capabilities
- Multi-language support