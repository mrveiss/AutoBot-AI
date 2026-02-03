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
