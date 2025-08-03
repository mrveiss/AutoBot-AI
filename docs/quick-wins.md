# Quick Wins & 30-Day Action Plan
**Generated**: 2025-08-03 06:15:37
**Branch**: analysis-report-20250803
**Analysis Scope**: Full codebase
**Priority Level**: High

## Executive Summary
This document identifies a list of "quick wins" - tasks that are low-effort but have a high impact on the project's security, stability, and maintainability. These are the ideal starting points for paying down technical debt and improving the codebase. This list can form the basis of an action plan for the next 30 days.

## Impact Assessment
- **Timeline Impact**: All tasks listed here can be completed in a short amount of time, providing immediate value.
- **Resource Requirements**: A single developer can complete most of these tasks.
- **Business Value**: **High**. Quickly patching security holes, fixing bugs, and improving maintainability provides a significant return on a small time investment.
- **Risk Level**: **Low**. These tasks are generally isolated and have a low risk of causing regressions.

---

## 30-Day Action Plan

### Week 1: Triage & Security Hardening (Effort: ~2-3 days)

The absolute first priority is to fix the critical security holes.

| Task | Priority | Effort | Impact |
|---|---|---|---|
| **Secure File Management API** | Critical | 1-2 days | Plugs a major security vulnerability. |
| **Mitigate Shell Injection Risk** | Critical | 1 day | Prevents arbitrary code execution. |
| **Refactor Duplicate Redis Clients**| High | 0.5 days | Improves maintainability and prevents config drift. |

**Details**:
1.  **Secure File Management API**: Focus on implementing the permission checks in `backend/api/files.py`. Even a simple, temporary role check is better than nothing while a full authentication system is being planned.
2.  **Mitigate Shell Injection Risk**: Implement the command whitelist in `src/worker_node.py`. This is a non-negotiable security fix.
3.  **Refactor Redis Clients**: This is the lowest-hanging fruit for refactoring. Create the `get_redis_client()` utility and update all modules to use it. It's a quick and easy way to improve code quality.

### Week 2: Restore Core Functionality & Fix Dependencies (Effort: ~2-3 days)

Focus on making the application fully functional as designed and fixing broken dependencies.

| Task | Priority | Effort | Impact |
|---|---|---|---|
| **Enable & Fix Orchestrator** | Critical | 1 day | Makes the agent's core asynchronous features work. |
| **Fix Frontend Dependencies** | High | 2 hours | Fixes the invalid version numbers in `package.json` to make the frontend build reliable. |
| **Add Pre-commit Hooks** | Medium | 3 hours | Automates linting and formatting, immediately improving code quality for all future commits. |

**Details**:
1.  **Enable Orchestrator**: Uncomment the listeners in `app_factory.py` and implement the `_listen_for_worker_capabilities` function. This is essential to un-break the agent's core logic.
2.  **Fix `package.json`**: Correct the `vue` and `typescript` versions and pin `rolldown-vite` to a specific version instead of `@latest`. This makes the frontend build process stable.
3.  **Add Pre-commit Hooks**: Use the `pre-commit` framework to set up hooks for `black` and `flake8`. This is a one-time setup that pays dividends on every future commit.

### Weeks 3-4: Build a Foundation for Quality (Effort: ~3-4 days)

With the most critical fires put out, focus on building the foundation for long-term quality and stability.

| Task | Priority | Effort | Impact |
|---|---|---|---|
| **Establish Testing Framework** | High | 1 day | Sets up `pytest` and CI integration. |
| **Write Initial Test Suite** | High | 2-3 days | Provides a safety net for all future changes. |
| **Update Documentation** | Medium | 1 day | Fixes the most critical documentation gaps (especially the security warnings). |

**Details**:
1.  **Establish Testing Framework**: Set up `pytest` with `pytest-cov` and create the initial CI workflow in GitHub Actions.
2.  **Write Initial Tests**: Focus on writing tests for the most critical and recently changed areas: the `SecurityLayer`, the `files` API, and the `Orchestrator`.
3.  **Update Documentation**: Add the warning about the lack of security to the API docs and add comments to the code explaining the disabled orchestrator features. This prevents other developers from being misled.
