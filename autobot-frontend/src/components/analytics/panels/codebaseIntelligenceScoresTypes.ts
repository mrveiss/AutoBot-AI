// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** Prop and score shapes for CodebaseIntelligenceScoresPanel.vue (split out of the component for the size ceiling, #18730). */

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

export interface CodeHealthScore {
  health_score: number
  total_files: number
  issues_count: {
    critical: number
    high: number
    medium: number
    low: number
  }
  coverage_percent: number
  technical_debt_hours: number
  timestamp: string
}

export interface QualityScore {
  overall_score: number
  metrics: {
    complexity: number
    maintainability: number
    documentation: number
    testing: number
    security: number
  }
  grade: string
  trend?: 'improving' | 'stable' | 'declining'
}

export interface CodeSuggestion {
  id: string
  type: string
  priority: 'high' | 'medium' | 'low'
  title: string
  description: string
  impact: string
}

export interface CodeAnalysisResult {
  id: string
  language: string
  filename?: string
  quality_score: number
  timestamp: string
}
