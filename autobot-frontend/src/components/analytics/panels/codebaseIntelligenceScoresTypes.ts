// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** Prop and score shapes for CodebaseIntelligenceScoresPanel.vue (split out of the component for the size ceiling, #18730).
 * CodeHealthScore, QualityScore, CodeSuggestion and CodeAnalysisResult come from
 * composables/useCodeIntelligence.ts, the single definition. */
export type {
  CodeHealthScore,
  QualityScore,
  CodeSuggestion,
  CodeAnalysisResult,
} from '@/composables/useCodeIntelligence'

export interface SecurityScoreResult {
  security_score: number
  grade: string
  risk_level: string
  status_message: string
  total_findings: number
  critical_issues: number
  high_issues: number
  files_analyzed: number
  severity_breakdown: Record<string, number>
  owasp_breakdown: Record<string, number>
}

export interface PerformanceScoreResult {
  performance_score: number
  grade: string
  status_message: string
  total_issues: number
  files_analyzed: number
}

export interface RedisHealthResult {
  redis_health_score: number
  grade: string
  status_message: string
  total_files: number
  total_issues: number
  files_with_issues: number
}

export interface SecurityFindingDetail {
  severity: string
  vulnerability_type: string
  description: string
  file_path: string
  line?: number
  recommendation?: string
  owasp_category?: string
}

export interface PerformanceFindingDetail {
  severity: string
  issue_type: string
  description: string
  file_path: string
  line?: number
  function_name?: string
  recommendation?: string
}

export interface RedisOptimization {
  severity: string
  optimization_type: string
  description: string
  file_path: string
  line?: number
  category?: string
  recommendation?: string
}
