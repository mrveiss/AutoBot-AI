# Test File Organization Summary

This document tracks the reorganization of test files into appropriate test subfolders.

## Files Moved (September 9, 2025)

### Unit Tests (`tests/unit/`)
- **`test_man_page_integration.py`** - Unit tests for the man page knowledge integration system
  - Tests man page extraction, parsing, and YAML conversion
  - Tests machine-aware system knowledge management
  - Originally located: `/test_man_page_integration.py`

### Integration Tests (`tests/integration/`)
- **`demo_chat_with_man_pages.py`** - Integration demo showing chat workflow with man page knowledge
  - Simulates chat queries using integrated man page knowledge
  - Demonstrates machine-specific knowledge responses
  - Originally located: `/demo_chat_with_man_pages.py`

- **`test_new_chat_workflow.py`** - Integration test for the complete chat system workflow
  - Tests user request → knowledge → response flow
  - Validates chat classification, knowledge search, and research orchestration
  - Originally located: `/scripts/analysis/test_new_chat_workflow.py`

- **`test_full_integration.py`** - Full integration test creating actual machine-specific knowledge
  - Tests complete workflow from machine detection to man page integration
  - Creates real knowledge files and validates integration
  - Originally located: `/test_full_integration.py`

- **`test_simple_man_pages.py`** - Simplified integration test for core man page functionality
  - Tests essential man page processing without full system integration
  - Lighter weight alternative for quick validation
  - Originally located: `/test_simple_man_pages.py`

### GUI Tests (`tests/gui/`)
- **`test-manpage-manager.html`** - Standalone HTML demo for the ManPageManager Vue.js component
  - Interactive demonstration of the man page management GUI
  - Includes mock data and simulated progress tracking
  - Originally located: `/autobot-vue/test-manpage-manager.html`

## Test Folder Structure

```
tests/
├── unit/              # Unit tests for individual components
├── integration/       # Integration tests for system workflows  
├── gui/              # GUI tests and demos
├── api/              # API endpoint tests
├── security/         # Security-related tests
├── performance/      # Performance benchmarks
└── fixtures/         # Test data and fixtures
```

## Benefits of Organization

1. **Clear Separation**: Unit, integration, and GUI tests are properly categorized
2. **Easy Discovery**: Developers can quickly find relevant tests
3. **Parallel Execution**: Different test types can be run independently
4. **CI/CD Integration**: Test runners can execute specific test categories
5. **Maintainability**: Related tests are grouped together

## Running Tests

### Run All Tests
```bash
pytest tests/
```

### Run Specific Test Categories
```bash
# Unit tests only
pytest tests/unit/

# Integration tests only  
pytest tests/integration/

# GUI tests (manual execution)
open tests/gui/test-manpage-manager.html
```

### Run Specific Test Files
```bash
# Man page integration tests
pytest tests/unit/test_man_page_integration.py

# Chat workflow integration
pytest tests/integration/test_new_chat_workflow.py

# Full system integration
pytest tests/integration/test_full_integration.py
```

## Notes

- All moved test files maintain their original functionality and executable permissions
- Test files are now properly organized according to AutoBot's testing standards
- Future test files should be created directly in the appropriate subfolder