# Codebase Analytics Multi-Project Fixes — #1710

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> **Primary Issue:** #1710 (cross-project data leakage)
> **Related Issues:** #1711, #1712, #1713, #1714, #1715, #1716, #1717

**Goal:** Fix cross-project data leakage, broken sync/local sources, and add missing UI elements so codebase analytics works correctly with multiple projects.

**Architecture:** Single ChromaDB collection with source_id metadata on every document. Redis keys namespaced by source_id. All query endpoints accept source_id filter. Frontend passes sourceId from route params to every API call.

**Tech Stack:** Python/FastAPI (backend), Vue 3/TypeScript (frontend), ChromaDB, Redis DB 11

---

## Phase 1: Sync Fixes (#1711, #1714, #1715)

### Task 1: Fix git clone/pull detection (#1711)
**Files:** Modify sources.py:104-138
Check .git subdirectory instead of just directory existence. Clean up failed clones before retry.

### Task 2: Fix local sources (#1714)
**Files:** Modify sources.py:222-236, 300-326
Set clone_path for local sources. Allow sync to skip git and trigger indexing directly.

### Task 3: Auto-sync on GitHub source creation (#1715)
**Files:** Modify sources.py:222-236
Fire _do_sync as background task after creating GitHub source.

## Phase 2: Cross-Project Isolation (#1710, #1716)

### Task 4: Add source_id to scanner metadata (#1710)
**Files:** Modify scanner.py, sources.py, indexing.py
Thread source_id through indexing pipeline. Namespace Redis keys. Targeted collection delete instead of drop.

### Task 5: Add source_id filtering to all query endpoints (#1710, #1716)
**Files:** Modify all endpoints/ files
Add source_id query param. Filter ChromaDB and Redis queries. Fix _get_last_indexed.

### Task 6: Frontend — pass sourceId to all API calls (#1710)
**Files:** Modify CodebaseAnalytics.vue
Create sourceQuery() helper. Namespace localStorage.

## Phase 3: Investigate Empty Reports (#1712)

### Task 7: Diagnostic investigation
Trigger indexing, check logs, verify analyzer output. Fix based on findings.

## Phase 4: UI Enhancements (#1713)

### Task 8: Show commit message on project cards (#1713)
**Files:** Modify CodebaseAnalyticsLanding.vue:118-136

### Task 9: Add project header in detail view (#1713)
**Files:** Modify CodebaseAnalytics.vue

## Phase 5: Deferred

### Task 10: Queue persistence (#1717) — DEFERRED

## Execution Order
1. Task 1-3 (Phase 1, commit after each)
2. Task 4-6 (Phase 2, commit after each)
3. Task 7 (Phase 3, diagnostic)
4. Task 8-9 (Phase 4, commit after each)
