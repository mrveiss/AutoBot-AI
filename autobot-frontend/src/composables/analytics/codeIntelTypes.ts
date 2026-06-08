// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Shared type definitions for Code Intelligence analysis composables.
 *
 * Issue #2260: Extracted from useCodeIntelAnalysis.ts during decomposition.
 */

import type { Ref, ComputedRef } from 'vue'
import type { ToastType } from '@/composables/useToast'
import type { HardcodedValue } from '@/composables/analytics/analyticsTypes'

// --- Dependencies interface ---

export interface UseCodeIntelAnalysisDeps {
  rootPath: Ref<string>
  sourceIdParam: ComputedRef<string>
  sourceIdQuery: ComputedRef<Record<string, string>>
  withSourceId: (url: string) => string
  analyzing: Ref<boolean>
  t: (key: string, params?: Record<string, unknown>) => string
  showToast: (msg: string, type?: ToastType, duration?: number) => number | void
  notify: (msg: string, type?: ToastType) => void
}

// --- Score result types ---

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
  severity_breakdown: Record<string, number>
  issue_type_breakdown: Record<string, number>
}

export interface RedisHealthResult {
  redis_health_score: number
  grade: string
  status_message: string
  total_files: number
  total_issues: number
  files_with_issues: number
}

// --- Finding detail types ---

export interface SecurityFindingDetail {
  severity: string
  vulnerability_type: string
  description: string
  file_path: string
  line?: number
  code_snippet?: string
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
  category?: string
  description: string
  file_path: string
  line?: number
  code_snippet?: string
  recommendation?: string
}

// --- API endpoint types ---

export interface ApiEndpointInfo {
  path: string
  method?: string
  function_name?: string
  expected_path?: string
  actual_path?: string
  file_path?: string
  line_number?: number
  [key: string]: unknown
}

export interface ApiUsageInfo {
  endpoint?: ApiEndpointInfo
  call_count?: number
  [key: string]: unknown
}

export interface ApiEndpointAnalysisResult {
  coverage_percentage: number
  backend_endpoints: number
  frontend_calls: number
  used_endpoints: number
  orphaned_endpoints: number
  missing_endpoints: number
  orphaned: ApiEndpointInfo[]
  missing: ApiEndpointInfo[]
  used?: ApiUsageInfo[]
  scan_timestamp?: string | number | Date
  [key: string]: unknown
}

// --- Config duplicates ---

export interface ConfigDuplicatesResult {
  duplicates_found: number
  duplicates: Array<{
    value: string
    locations: Array<{ file: string; line: number }>
  }>
  report: string
}

// --- Bug prediction types ---

export interface BugPredictionFile {
  file_path: string
  risk_score: number
  risk_level: string
  factors: Record<string, number>
  prevention_tips?: string[]
  suggested_tests?: string[]
}

export interface BugPredictionResult {
  timestamp: string
  total_files: number
  analyzed_files: number
  high_risk_count: number
  files: BugPredictionFile[]
}

export interface TopRiskFactor {
  name: string
  count: number
  severity: 'critical' | 'high' | 'medium' | 'low'
}

// --- Environment analysis types ---

export interface EnvRecommendation {
  env_var_name: string
  default_value: string
  description: string
  category: string
  priority: string
}

export interface EnvironmentAnalysisResult {
  total_hardcoded_values: number
  high_priority_count: number
  recommendations_count: number
  categories: Record<string, number>
  analysis_time_seconds: number
  // #5311: use canonical HardcodedValue from analyticsTypes.
  hardcoded_values: HardcodedValue[]
  recommendations: EnvRecommendation[]
  is_truncated?: boolean
}

// --- Ownership types ---

export interface OwnershipContributor {
  name: string
  email?: string
  lines: number
  percentage: number
}

export interface FileOwnership {
  file_path: string
  total_lines: number
  primary_owner: string | null
  ownership_percentage: number
  bus_factor: number
  knowledge_risk: string
  last_modified: string | null
  contributors: OwnershipContributor[]
}

export interface DirectoryOwnership {
  directory_path: string
  total_files: number
  total_lines: number
  primary_owner: string | null
  ownership_percentage: number
  bus_factor: number
  knowledge_risk: string
  contributors: OwnershipContributor[]
}

export interface ExpertiseScore {
  author_name: string
  author_email: string
  total_lines: number
  total_commits: number
  files_owned: number
  directories_owned: number
  expertise_areas: string[]
  recency_score: number
  impact_score: number
  overall_score: number
}

export interface KnowledgeGap {
  area: string
  gap_type: string
  risk_level: string
  description: string
  recommendation: string
  affected_lines: number
}

export interface OwnershipMetrics {
  total_lines_analyzed: number
  total_files_analyzed: number
  overall_bus_factor: number
  bus_factor_distribution: Record<string, number>
  knowledge_risk_distribution: Record<string, number>
  top_contributors: Array<{
    name: string
    lines: number
    score: number
  }>
  ownership_concentration: number
  team_coverage: number
}

export interface OwnershipSummary {
  total_files: number
  total_directories: number
  total_contributors: number
  knowledge_gaps_count: number
  critical_gaps: number
  high_risk_gaps: number
}

export interface OwnershipAnalysisResult {
  status: string
  analysis_time_seconds: number
  summary: OwnershipSummary
  file_ownership: FileOwnership[]
  directory_ownership: DirectoryOwnership[]
  expertise_scores: ExpertiseScore[]
  knowledge_gaps: KnowledgeGap[]
  metrics: OwnershipMetrics
}

// --- Cross-language analysis types ---

export interface PatternLocation {
  file_path: string
  line_start: number
  line_end: number
  language: string
}

export interface DTOMismatch {
  mismatch_id: string
  backend_type: string
  frontend_type: string
  field_name: string
  mismatch_type: string
  severity: string
  recommendation: string
  backend_location?: PatternLocation
  frontend_location?: PatternLocation
}

export interface ValidationDuplication {
  duplication_id: string
  validation_type: string
  similarity_score: number
  severity: string
  recommendation: string
  python_location?: PatternLocation
  typescript_location?: PatternLocation
}

export interface APIContractMismatch {
  mismatch_id: string
  endpoint_path: string
  http_method: string
  mismatch_type: string
  severity: string
  details: string
  recommendation: string
  backend_location?: PatternLocation
  frontend_location?: PatternLocation
}

export interface PatternMatch {
  pattern_id: string
  similarity_score: number
  match_type: string
  confidence: number
  source_location?: PatternLocation
  target_location?: PatternLocation
  metadata?: Record<string, string>
}

export interface CrossLanguageAnalysisResult {
  analysis_id: string
  scan_timestamp: string
  python_files_analyzed: number
  typescript_files_analyzed: number
  vue_files_analyzed: number
  total_patterns: number
  critical_issues: number
  high_issues: number
  medium_issues: number
  low_issues: number
  dto_mismatches: DTOMismatch[]
  validation_duplications: ValidationDuplication[]
  api_contract_mismatches: APIContractMismatch[]
  pattern_matches: PatternMatch[]
  analysis_time_ms: number
}

// --- Code smells types ---

export interface CodeSmellsReportData {
  smells: Array<{
    type: string
    severity: string
    message: string
    file_path: string
    line?: number
  }>
  summary?: Record<string, unknown>
  [key: string]: unknown
}

export interface CodeHealthScoreData {
  grade: string
  health_score: number
  breakdown?: Record<string, unknown>
  [key: string]: unknown
}
