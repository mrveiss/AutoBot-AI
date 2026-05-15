# CodebaseAnalytics Composable Extraction Plan (#1321)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract 30+ nearly identical loader functions from CodebaseAnalytics.vue into two reusable composables, removing ~500-800 lines of boilerplate.

**Architecture:** Two new composables — `useAnalyticsFetch<T>` for direct-fetch loaders and `useTaskLoader<T>` for background-task loaders — each wrapping the existing `fetchWithAuth` and `useBackgroundTask` respectively.

**Tech Stack:** Vue 3 Composition API, TypeScript, fetchWithAuth, useBackgroundTask

---

### Task 1: Create `useAnalyticsFetch` Composable

**Files:**
- Create: `autobot-frontend/src/composables/useAnalyticsFetch.ts`

### Task 2: Create `useTaskLoader` Composable

**Files:**
- Create: `autobot-frontend/src/composables/useTaskLoader.ts`

### Task 3: Replace 5 Background-Task Loaders with useTaskLoader

**Files:**
- Modify: `autobot-frontend/src/components/analytics/CodebaseAnalytics.vue`

### Task 4: Replace 15+ Direct-Fetch Loaders with useAnalyticsFetch

**Files:**
- Modify: `autobot-frontend/src/components/analytics/CodebaseAnalytics.vue`

### Task 5: Merge Duplicate Function Pairs

**Files:**
- Modify: `autobot-frontend/src/components/analytics/CodebaseAnalytics.vue`

### Task 6: Final Cleanup & Verification

**Files:**
- Modify: `autobot-frontend/src/components/analytics/CodebaseAnalytics.vue`
