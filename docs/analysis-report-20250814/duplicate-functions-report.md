# Duplicate Functions Report
**Generated**: 2025-08-14 22:51:08.635305
**Branch**: analysis-report-20250814
**Analysis Scope**: `backend/api/` directory
**Priority Level**: High

## Executive Summary
This report details a significant instance of code duplication found in the terminal websocket implementations. Three separate files provide similar functionality, with two of them being nearly identical. This duplication increases maintenance costs and the risk of bugs.

## Duplicate Code Findings

### Duplicated Files
The following files in `backend/api/` provide terminal websocket functionality and contain a large amount of duplicated or overlapping logic:

1.  **`simple_terminal_websocket.py`**: A low-level implementation using Python's `pty` module. It includes features for workflow automation.
2.  **`secure_terminal_websocket.py`**: Another low-level `pty`-based implementation that is almost a direct copy of the `simple` version, but with added security and auditing features.
3.  **`terminal_websocket.py`**: A high-level implementation that uses the `SystemCommandAgent` and does not use `pty` directly.

### Analysis of Duplication
The most significant duplication is between `simple_terminal_websocket.py` and `secure_terminal_websocket.py`. These two files share nearly identical logic for:
- **PTY and Process Management**: The `start_pty_shell` and `disconnect` methods, which handle the creation and cleanup of the `pty` and `subprocess`, are almost word-for-word the same.
- **WebSocket Connection Handling**: The `connect` method and the main message handling loop are structured identically.
- **PTY Output Reading**: The `_read_pty_output` method, which runs in a separate thread to read from the PTY, is duplicated.

While `terminal_websocket.py` uses a different approach (agent-based), it still represents a duplication of the *feature* of providing a terminal over a websocket.

### Estimated Lines of Code Reduction
A proper refactoring could consolidate the ~300 lines of code in `simple_terminal_websocket.py` and the ~300 lines in `secure_terminal_websocket.py` into a single, well-structured module of around 200-250 lines, with extensions for security and workflow features. This would result in a net reduction of **350-400 lines of code** and significantly improve maintainability.

## Consolidation Opportunities

The duplicated logic can be consolidated by creating a single, unified PTY terminal implementation.

### Proposed Refactoring Roadmap
1.  **Create a `UnifiedTerminalSession` class**: This class would contain all the common PTY management logic (creation, reading, writing, disconnection).
2.  **Use Composition or Mixins for Features**:
    - The security/auditing features from `secure_terminal_websocket.py` could be implemented in a `SecurityMixin` or a separate `AuditingService` that the unified terminal can use.
    - The workflow automation features from `simple_terminal_websocket.py` could be implemented in a `WorkflowMixin` or a `WorkflowService`.
3.  **Refactor Endpoints**: The FastAPI endpoints should be updated to use the new unified terminal class. Configuration flags could be used to enable/disable features like security and workflow on a per-session basis.
4.  **Deprecate and Remove Old Files**: Once the refactoring is complete and tested, the old `simple_terminal_websocket.py` and `secure_terminal_websocket.py` files should be deleted.
5.  **Decide on `terminal_websocket.py`**: The team needs to decide if the high-level, agent-based terminal is still needed. If not, it should also be removed to avoid confusion.

This refactoring is detailed as a critical task in the [Task Breakdown - Critical](task-breakdown-critical.md) report.
