// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Analytics type definitions — shared between useAnalyticsDataFetchers
 * and its consumers (CodebaseAnalytics.vue). Extracted from the fetchers
 * composable in #5112 to keep the fetchers file under 700 lines.
 */

export interface Problem {
  severity: string
  type: string
  message: string
  description?: string
  file_path: string
  line?: number
  line_number?: number
  category?: string
  suggestion?: string
}

export interface DuplicateCode {
  similarity: number
  lines: number
  file1: string
  file2: string
  start1?: number
  start2?: number
}

export interface Declaration {
  type: string
  name: string
  file_path: string
  line?: number
  line_number?: number
  is_exported?: boolean
}

/**
 * Hardcoded value record (Issue #5290: contract aligned with backend).
 *
 * Canonical shape emitted by `/api/analytics/codebase/hardcodes`:
 * - `file`, `line`, `value`, `type`, `severity` are always present
 *   (backend response-boundary normalizer fills `file` + default
 *   `severity` for legacy records without them).
 * - `variable_name` / `suggested_env_var` are populated by the LLM path
 *   only; AST/regex detections omit them.
 */
export interface HardcodedValue {
  file: string
  line: number
  value: string
  type: string
  severity: string
  variable_name?: string
  suggested_env_var?: string
  context?: string
  current_usage?: string
}

export interface RefactoringSuggestion {
  type: string
  severity: string
  description: string
  file_path: string
  line?: number
  suggestion: string
}

export interface ChartDataItem {
  name: string
  value: number
  type?: string
  [key: string]: unknown
}

export interface ChartDataSummary {
  total_problems?: number
  unique_problem_types?: number
  files_with_problems?: number
  race_condition_count?: number
}

export interface ChartData {
  summary?: ChartDataSummary
  problem_types?: ChartDataItem[]
  severity_counts?: ChartDataItem[]
  race_conditions?: ChartDataItem[]
  top_files?: ChartDataItem[]
  [key: string]: unknown
}

export interface DependencyNode {
  id: string
  name: string
  type?: string
}

export interface DependencyEdge {
  source: string
  target: string
  type?: string
}

export interface ModuleData {
  name: string
  path?: string
  import_count: number
  [key: string]: unknown
}

export interface ExternalDependency {
  name: string
  usage_count?: number
  [key: string]: unknown
}

export type CircularDependency =
  | string[]
  | {
      modules: string[]
      cycle?: string[]
      length?: number
      severity?: string
    }

export interface DependencySummary {
  total_modules?: number
  total_import_relationships?: number
  external_dependency_count?: number
  circular_dependency_count?: number
}

export interface DependencyGraph {
  nodes: DependencyNode[]
  edges: DependencyEdge[]
  summary?: DependencySummary
  modules?: ModuleData[]
  external_dependencies?: ExternalDependency[]
  circular_dependencies?: CircularDependency[]
  import_relationships?: DependencyEdge[]
}

export interface ImportTreeNode {
  name: string
  path: string
  children?: ImportTreeNode[]
  imports?: string[]
}

export interface UnifiedReportData {
  categories: Record<string, Problem[]>
  summary: {
    total: number
    by_severity: Record<string, number>
    by_category: Record<string, number>
  }
  timestamp: string
}

export interface OrphanedFunction {
  id: string
  name: string
  full_name: string
  module: string
  class: string | null
  file: string
  line: number
  is_async: boolean
}

// Issue #609: Code smell types for filtering
export const CODE_SMELL_TYPES = new Set([
  'long_function',
  'debug_code',
  'race_condition',
  'technical_debt_bug',
  'technical_debt_todo',
  'technical_debt_fixme',
  'technical_debt_deprecated',
  'performance_nested_loop_complexity',
  'performance_quadratic_complexity',
  'performance_n_plus_one_query',
  'performance_blocking_io_in_async',
  'performance_excessive_string_concat',
  'performance_list_for_lookup',
  'performance_repeated_computation',
  'performance_repeated_file_open',
  'performance_sequential_awaits',
  'performance_unbatched_api_calls',
])
