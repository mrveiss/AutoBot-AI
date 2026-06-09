// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Workflow Templates TypeScript interfaces
 * Issue #778 - Workflow Templates Enhancement
 * Issue #6951 Phase 2F + #7044: TemplateStep regenerated from canonical
 *   autobot_shared.workflow.WorkflowTask shape. Old fields step_id /
 *   requires_confirmation / risk_level removed — those belonged to the
 *   runtime workflow_automation path, NOT the static template path.
 *   See AutomationWorkflowStep below for the runtime shape.
 */

export type TemplateCategory = 'security' | 'research' | 'development' | 'system_admin' | 'analysis' | 'community'
export type TaskComplexity = 'simple' | 'moderate' | 'complex' | 'research' | 'security_scan' | 'install'

/**
 * Generated unions/types — single source of truth is the canonical Python
 * (#7122 / #7226). Re-exported here so consumers keep a stable import path
 * (`@/types/workflowTemplates`) regardless of how the backing classes are
 * sourced (shared dataclasses, backend enums, etc.).
 *
 * The `frontend-codegen-drift` CI check fails if the generated file goes stale.
 */
import type {
  PromptSpec,
  WorkflowTask,
  WorkflowPlan,
  WorkflowStepStatus,
  RiskLevel,
} from './_generated/workflow'
export type { PromptSpec, WorkflowTask, WorkflowPlan, RiskLevel }

/**
 * Static template step — matches backend `_template_step_dict()` from
 * `workflow_templates/types.py`. Field names align with canonical
 * `autobot_shared.workflow.WorkflowTask`. Runtime-state fields
 * (status / start_time / end_time / error / outputs) are intentionally
 * absent — a template step has no execution state.
 */
export interface TemplateStep {
  task_id: string
  agent_type: string
  action: string
  command: string | null
  description: string
  requires_approval: boolean
  dependencies: string[]
  inputs: Record<string, unknown>
  estimated_duration_seconds: number
  prompt: PromptSpec | null
  tools_allowed: string[] | null
  tools_denied: string[]
}

/**
 * Runtime workflow step status — string union mirroring
 * `services/workflow_automation/models.py:WorkflowStepStatus`.
 *
 * #7123: declared here as the canonical types module. The previous local
 * declaration in `composables/useWorkflowBuilder.ts` is now a re-export
 * pointing at this definition (single source of truth).
 */
export type WorkflowStepStatus =
  | 'pending'
  | 'waiting_approval'
  | 'approved'
  | 'executing'
  | 'completed'
  | 'skipped'
  | 'failed'
  | 'paused'

/**
 * Runtime workflow step — matches backend
 * `services/workflow_automation/WorkflowStep.to_status_dict()`. Used by the
 * shell+vision execution path with risk levels and confirmation gating.
 * Distinct from `TemplateStep` per #7044 split.
 *
 * #7123: extended to be the canonical runtime shape consumed across the
 * frontend. The previous local `WorkflowStep` interface in
 * `composables/useWorkflowBuilder.ts` is now `type WorkflowStep = AutomationWorkflowStep`.
 *
 * Field nullability matches backend payload exactly:
 * - `started_at` / `completed_at` are `string | null` (backend always sends
 *   the key, with ISO-8601 string when set, null otherwise).
 * - `risk_level` is required (backend always emits it; the previous
 *   optional ? was a guess that masked the bug #7044 documented).
 */
export interface AutomationWorkflowStep {
  step_id: string
  command: string
  description: string
  explanation?: string
  status: WorkflowStepStatus
  requires_confirmation: boolean
  risk_level: RiskLevel
  estimated_duration: number
  dependencies?: string[]
  execution_result?: Record<string, unknown>
  started_at: string | null
  completed_at: string | null
}

export interface SecretRequirement {
  description: string
  required: boolean
  scope: string
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
  step_count?: number
  approval_steps?: number
  required_secrets?: Record<string, SecretRequirement>
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
