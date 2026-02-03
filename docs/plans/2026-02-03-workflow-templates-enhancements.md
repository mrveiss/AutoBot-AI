# Workflow Templates Enhancement Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect the existing WorkflowTemplateGallery to backend API endpoints instead of hardcoded data.

**Architecture:** Add API methods to useWorkflowBuilder composable, create TypeScript interfaces for templates, and enhance the gallery component with API-driven features.

**Tech Stack:** Vue 3, TypeScript, Pinia

**Related Issue:** #778 - Workflow Templates (User-Facing)

---

## Current State Analysis

**Existing UI (working):**
- `WorkflowBuilderView.vue` - Has templates section with sidebar nav
- `WorkflowTemplateGallery.vue` - Has search, category filters, preview panel
- `useWorkflowBuilder.ts` - Has hardcoded `builtInTemplates` array

**Backend API (ready):**
- `GET /api/templates/templates` - List templates with filters
- `GET /api/templates/templates/{id}` - Get template details
- `GET /api/templates/templates/search?q=` - Search templates
- `GET /api/templates/templates/categories` - List categories
- `GET /api/templates/templates/stats` - Get statistics
- `GET /api/templates/templates/{id}/preview` - Preview workflow
- `POST /api/templates/templates/{id}/create-workflow` - Create workflow
- `POST /api/templates/templates/{id}/execute` - Execute directly

---

## Task 1: Add Template TypeScript Interfaces

**Files:**
- Create: `autobot-vue/src/types/workflowTemplates.ts`

**Step 1: Create type definitions**

```typescript
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Workflow Templates TypeScript interfaces
 * Issue #778 - Workflow Templates Enhancement
 */

export type TemplateCategory = 'security' | 'research' | 'development' | 'system_admin' | 'analysis'
export type TaskComplexity = 'simple' | 'moderate' | 'complex' | 'research' | 'security_scan' | 'install'
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export interface TemplateStep {
  step_id: string
  description: string
  command: string
  requires_confirmation: boolean
  risk_level: RiskLevel
  estimated_duration_seconds: number
  agent_type?: string
}

export interface WorkflowTemplateSummary {
  id: string
  name: string
  description: string
  category: TemplateCategory
  complexity: TaskComplexity
  estimated_duration_minutes: number
  agents_involved: string[]
  tags: string[]
  icon?: string
}

export interface WorkflowTemplateDetail extends WorkflowTemplateSummary {
  steps: TemplateStep[]
  required_variables: string[]
  optional_variables: string[]
  created_at?: string
  updated_at?: string
}

export interface TemplateListResponse {
  success: boolean
  templates: WorkflowTemplateSummary[]
  total: number
}

export interface TemplateDetailResponse {
  success: boolean
  template: WorkflowTemplateDetail
}

export interface TemplateCategoryInfo {
  name: string
  display_name: string
  template_count: number
}

export interface TemplateCategoriesResponse {
  success: boolean
  categories: TemplateCategoryInfo[]
}

export interface TemplateSearchResponse {
  success: boolean
  query: string
  results: WorkflowTemplateSummary[]
  total: number
}

export interface TemplateStatsResponse {
  success: boolean
  statistics: {
    total_templates: number
    category_breakdown: Record<string, number>
    complexity_breakdown: Record<string, number>
    agent_usage: Record<string, number>
    average_duration_minutes: number
    duration_range: {
      min: number
      max: number
    }
  }
}

export interface TemplatePreviewResponse {
  success: boolean
  template_id: string
  template_name: string
  description: string
  estimated_duration_minutes: number
  agents_involved: string[]
  workflow_preview: string[]
  variables_used: Record<string, string>
  total_steps: number
  approval_required_steps: number
}

export interface CreateWorkflowResponse {
  success: boolean
  workflow?: {
    template_name: string
    description: string
    category: string
    steps: TemplateStep[]
    estimated_duration_minutes: number
    agents_involved: string[]
    variables_used?: Record<string, string>
  }
  ready_for_execution?: boolean
  execution_endpoint?: string
  error?: string
  validation?: {
    valid: boolean
    missing_required: string[]
    invalid_values: Record<string, string>
  }
}
```

**Step 2: Verify file created**

Run: `ls -la autobot-vue/src/types/workflowTemplates.ts`

**Step 3: Commit**

```bash
git add autobot-vue/src/types/workflowTemplates.ts
git commit -m "feat(#778): add TypeScript interfaces for workflow templates"
```

---

## Task 2: Create useWorkflowTemplates Composable

**Files:**
- Create: `autobot-vue/src/composables/useWorkflowTemplates.ts`

**Step 1: Create the API composable**

```typescript
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Workflow Templates API composable
 * Issue #778 - Workflow Templates Enhancement
 */

import { ref, computed } from 'vue'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'
import type {
  WorkflowTemplateSummary,
  WorkflowTemplateDetail,
  TemplateCategoryInfo,
  TemplateStatsResponse,
  TemplatePreviewResponse,
  CreateWorkflowResponse,
  TemplateCategory
} from '@/types/workflowTemplates'

const logger = createLogger('useWorkflowTemplates')

export function useWorkflowTemplates() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // State
  const templates = ref<WorkflowTemplateSummary[]>([])
  const categories = ref<TemplateCategoryInfo[]>([])
  const stats = ref<TemplateStatsResponse['statistics'] | null>(null)
  const selectedTemplate = ref<WorkflowTemplateDetail | null>(null)
  const preview = ref<TemplatePreviewResponse | null>(null)

  async function getBackendUrl(): Promise<string> {
    return await appConfig.getServiceUrl('backend')
  }

  async function fetchTemplates(
    category?: TemplateCategory,
    tags?: string[],
    complexity?: string
  ): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const params = new URLSearchParams()
      if (category) params.append('category', category)
      if (tags?.length) params.append('tags', tags.join(','))
      if (complexity) params.append('complexity', complexity)

      const url = `${backendUrl}/api/templates/templates${params.toString() ? '?' + params.toString() : ''}`
      const response = await fetch(url)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      templates.value = data.templates || []
    } catch (e) {
      error.value = `Failed to fetch templates: ${e}`
      logger.error('fetchTemplates failed:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchTemplateDetail(templateId: string): Promise<WorkflowTemplateDetail | null> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(`${backendUrl}/api/templates/templates/${templateId}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      selectedTemplate.value = data.template
      return data.template
    } catch (e) {
      error.value = `Failed to fetch template: ${e}`
      logger.error('fetchTemplateDetail failed:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function searchTemplates(query: string): Promise<WorkflowTemplateSummary[]> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/templates/templates/search?q=${encodeURIComponent(query)}`
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      return data.results || []
    } catch (e) {
      error.value = `Failed to search templates: ${e}`
      logger.error('searchTemplates failed:', e)
      return []
    } finally {
      loading.value = false
    }
  }

  async function fetchCategories(): Promise<void> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(`${backendUrl}/api/templates/templates/categories`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      categories.value = data.categories || []
    } catch (e) {
      logger.error('fetchCategories failed:', e)
    }
  }

  async function fetchStats(): Promise<void> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(`${backendUrl}/api/templates/templates/stats`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      stats.value = data.statistics
    } catch (e) {
      logger.error('fetchStats failed:', e)
    }
  }

  async function previewTemplate(
    templateId: string,
    variables?: Record<string, string>
  ): Promise<TemplatePreviewResponse | null> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      let url = `${backendUrl}/api/templates/templates/${templateId}/preview`
      if (variables && Object.keys(variables).length > 0) {
        url += `?variables=${encodeURIComponent(JSON.stringify(variables))}`
      }
      const response = await fetch(url)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      preview.value = data
      return data
    } catch (e) {
      error.value = `Failed to preview template: ${e}`
      logger.error('previewTemplate failed:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function createWorkflowFromTemplate(
    templateId: string,
    variables?: Record<string, string>
  ): Promise<CreateWorkflowResponse | null> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/templates/templates/${templateId}/create-workflow`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            template_id: templateId,
            variables: variables || {},
            auto_approve: false
          })
        }
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return await response.json()
    } catch (e) {
      error.value = `Failed to create workflow: ${e}`
      logger.error('createWorkflowFromTemplate failed:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function executeTemplate(
    templateId: string,
    variables?: Record<string, string>,
    autoApprove = false
  ): Promise<CreateWorkflowResponse | null> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/templates/templates/${templateId}/execute`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            template_id: templateId,
            variables: variables || {},
            auto_approve: autoApprove
          })
        }
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return await response.json()
    } catch (e) {
      error.value = `Failed to execute template: ${e}`
      logger.error('executeTemplate failed:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function initializeTemplates(): Promise<void> {
    await Promise.all([fetchTemplates(), fetchCategories(), fetchStats()])
  }

  // Computed
  const totalTemplates = computed(() => stats.value?.total_templates || templates.value.length)
  const categoryNames = computed(() => categories.value.map(c => c.display_name))

  return {
    // State
    loading,
    error,
    templates,
    categories,
    stats,
    selectedTemplate,
    preview,
    // Computed
    totalTemplates,
    categoryNames,
    // Actions
    fetchTemplates,
    fetchTemplateDetail,
    searchTemplates,
    fetchCategories,
    fetchStats,
    previewTemplate,
    createWorkflowFromTemplate,
    executeTemplate,
    initializeTemplates
  }
}
```

**Step 2: Verify file created**

Run: `ls -la autobot-vue/src/composables/useWorkflowTemplates.ts`

**Step 3: Commit**

```bash
git add autobot-vue/src/composables/useWorkflowTemplates.ts
git commit -m "feat(#778): add useWorkflowTemplates API composable"
```

---

## Task 3: Update WorkflowTemplateGallery to Use API

**Files:**
- Modify: `autobot-vue/src/components/workflow/WorkflowTemplateGallery.vue`

**Step 1: Update the component to use the new composable**

Replace the script section to use the API composable and add statistics display. Key changes:
- Import and use `useWorkflowTemplates` composable
- Fetch templates on mount
- Use API categories instead of computed from local data
- Add template count per category
- Add stats section with template breakdown

**Step 2: Build and test**

Run: `cd autobot-vue && npm run build`

**Step 3: Commit**

```bash
git add autobot-vue/src/components/workflow/WorkflowTemplateGallery.vue
git commit -m "feat(#778): connect WorkflowTemplateGallery to backend API"
```

---

## Task 4: Update useWorkflowBuilder to Use API Templates

**Files:**
- Modify: `autobot-vue/src/composables/useWorkflowBuilder.ts`

**Step 1: Replace hardcoded templates with API call**

In `useWorkflowBuilder.ts`:
- Import `useWorkflowTemplates`
- Replace `builtInTemplates` array with API fetch
- Update `createWorkflowFromTemplate` to use API endpoint
- Keep fallback to hardcoded templates if API fails

**Step 2: Build and test**

Run: `cd autobot-vue && npm run build`

**Step 3: Commit**

```bash
git add autobot-vue/src/composables/useWorkflowBuilder.ts
git commit -m "feat(#778): integrate API templates into useWorkflowBuilder"
```

---

## Task 5: Build Verification and Final Commit

**Step 1: Run full build**

Run: `cd autobot-vue && npm run build`
Expected: Build succeeds without errors

**Step 2: Final commit**

```bash
git add -A
git commit -m "feat(#778): complete workflow templates API integration"
```

---

## Summary

This plan implements:
1. TypeScript interfaces for all template API responses
2. `useWorkflowTemplates` composable for dedicated template API calls
3. Updated `WorkflowTemplateGallery` to fetch from API
4. Updated `useWorkflowBuilder` to use API templates with hardcoded fallback
5. Build verification

Total tasks: 5
Estimated commits: 5
