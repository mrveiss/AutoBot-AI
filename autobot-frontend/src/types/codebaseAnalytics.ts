// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Shared types for Codebase Analytics components and composables.
 * Issue #2228/#2230: Extracted from CodebaseAnalytics.vue script section.
 */

export interface CodeSource {
  id: string
  name: string
  source_type: 'github' | 'local'
  repo: string | null
  branch: string
  credential_id: string | null
  clone_path: string | null
  last_synced: string | null
  status: 'configured' | 'syncing' | 'ready' | 'error'
  error_message: string | null
  owner_id: string | null
  access: 'private' | 'shared' | 'public'
  shared_with: string[]
  created_at: string
}

export interface JobPhase {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed'
}
export interface JobPhasesData { phase_list: JobPhase[] }
export interface JobBatchesData { total_batches: number; completed_batches: number }
export interface JobStatsData { files_scanned: number; problems_found: number; functions_found: number; classes_found: number; items_stored: number }

export interface Problem { severity: string; type: string; message: string; description?: string; file_path: string; line?: number; line_number?: number; category?: string; suggestion?: string }
export interface DuplicateCode { similarity: number; lines: number; file1: string; file2: string; start1?: number; start2?: number }
export interface Declaration { type: string; name: string; file_path: string; line?: number; line_number?: number; is_exported?: boolean }
export interface HardcodedValue { file: string; line: number; variable_name?: string; value: string; type: string; severity: string; suggested_env_var: string; context?: string; current_usage?: string }
export interface RefactoringSuggestion { type: string; severity: string; description: string; file_path: string; line?: number; suggestion: string }

export interface CodeSmellsReportData { smells: Array<{ type: string; severity: string; message: string; file_path: string; line?: number }>; summary?: Record<string, unknown> }
export interface CodeHealthScoreData { grade: string; health_score: number; breakdown?: Record<string, unknown>; [key: string]: unknown }

export interface SystemOverviewData { api_requests_per_minute: number; average_response_time: number; active_connections: number; system_health: string }
export interface CommunicationPatternsData { websocket_connections: number; api_call_frequency: number; data_transfer_rate: number; unique_endpoints: number }
export interface CodeQualityData { overall_score: number; test_coverage: number; code_duplicates: number; technical_debt: number }
export interface PerformanceMetricsData { efficiency_score: number; memory_usage: number; cpu_usage: number; load_time: number }

export interface ChartDataItem { name: string; value: number; type?: string; [key: string]: unknown }
export interface ChartDataSummary { total_problems?: number; unique_problem_types?: number; files_with_problems?: number; race_condition_count?: number }
export interface ChartData { summary?: ChartDataSummary; problem_types?: ChartDataItem[]; severity_counts?: ChartDataItem[]; race_conditions?: ChartDataItem[]; top_files?: ChartDataItem[]; [key: string]: unknown }

export interface DependencyNode { id: string; name: string; type?: string }
export interface DependencyEdge { source: string; target: string; type?: string }
export interface ModuleData { name: string; path?: string; import_count: number; [key: string]: unknown }
export interface ExternalDependency { name: string; usage_count?: number; [key: string]: unknown }
export type CircularDependency = string[] | { modules: string[]; cycle?: string[]; length?: number; severity?: string }
export interface DependencySummary { total_modules?: number; total_import_relationships?: number; external_dependency_count?: number; circular_dependency_count?: number }
export interface DependencyGraph { nodes: DependencyNode[]; edges: DependencyEdge[]; summary?: DependencySummary; modules?: ModuleData[]; external_dependencies?: ExternalDependency[]; circular_dependencies?: CircularDependency[]; import_relationships?: DependencyEdge[] }
export interface ImportTreeNode { name: string; path: string; children?: ImportTreeNode[]; imports?: string[] }

export interface UnifiedReportData { categories: Record<string, Problem[]>; summary: { total: number; by_severity: Record<string, number>; by_category: Record<string, number> }; timestamp: string }

export interface ApiEndpointInfo { path: string; method?: string; function_name?: string; expected_path?: string; actual_path?: string; file_path?: string; line_number?: number; [key: string]: unknown }
export interface ApiUsageInfo { endpoint?: ApiEndpointInfo; call_count?: number; [key: string]: unknown }
export interface ApiEndpointAnalysisResult { coverage_percentage: number; backend_endpoints: number; frontend_calls: number; used_endpoints: number; orphaned_endpoints: number; missing_endpoints: number; orphaned: ApiEndpointInfo[]; missing: ApiEndpointInfo[]; used?: ApiUsageInfo[]; scan_timestamp?: string | number | Date; [key: string]: unknown }

export interface ConfigDuplicatesResult { duplicates_found: number; duplicates: Array<{ value: string; locations: Array<{ file: string; line: number }> }>; report: string }

export interface BugPredictionFile { file_path: string; risk_score: number; risk_level: string; factors: Record<string, number>; prevention_tips?: string[]; suggested_tests?: string[] }
export interface BugPredictionResult { timestamp: string; total_files: number; analyzed_files: number; high_risk_count: number; files: BugPredictionFile[] }

export interface SecurityScoreResult { security_score: number; grade: string; risk_level: string; status_message: string; total_findings: number; critical_issues: number; high_issues: number; files_analyzed: number; severity_breakdown: Record<string, number>; owasp_breakdown: Record<string, number> }
export interface PerformanceScoreResult { performance_score: number; grade: string; status_message: string; total_issues: number; files_analyzed: number; severity_breakdown: Record<string, number>; issue_type_breakdown: Record<string, number> }
export interface RedisHealthResult { redis_health_score: number; grade: string; status_message: string; total_files: number; total_issues: number; files_with_issues: number }

export interface SecurityFindingDetail { severity: string; vulnerability_type: string; description: string; file_path: string; line?: number; code_snippet?: string; recommendation?: string; owasp_category?: string }
export interface PerformanceFindingDetail { severity: string; issue_type: string; description: string; file_path: string; line?: number; function_name?: string; recommendation?: string }
export interface RedisOptimization { severity: string; optimization_type: string; category?: string; description: string; file_path: string; line?: number; code_snippet?: string; recommendation?: string }

export interface EnvRecommendation { env_var_name: string; default_value: string; description: string; category: string; priority: string }
export interface EnvironmentAnalysisResult { total_hardcoded_values: number; high_priority_count: number; recommendations_count: number; categories: Record<string, number>; analysis_time_seconds: number; hardcoded_values: HardcodedValue[]; recommendations: EnvRecommendation[]; is_truncated?: boolean }
export interface LlmFilteringResult { enabled: boolean; model: string; original_count: number; filtered_count: number; reduction_percent: number; filter_priority: string | null }

export interface OwnershipContributor { name: string; email?: string; lines: number; percentage: number }
export interface FileOwnership { file_path: string; total_lines: number; primary_owner: string | null; ownership_percentage: number; bus_factor: number; knowledge_risk: string; last_modified: string | null; contributors: OwnershipContributor[] }
export interface DirectoryOwnership { directory_path: string; total_files: number; total_lines: number; primary_owner: string | null; ownership_percentage: number; bus_factor: number; knowledge_risk: string; contributors: OwnershipContributor[] }
export interface ExpertiseScore { author_name: string; author_email: string; total_lines: number; total_commits: number; files_owned: number; directories_owned: number; expertise_areas: string[]; recency_score: number; impact_score: number; overall_score: number }
export interface KnowledgeGap { area: string; gap_type: string; risk_level: string; description: string; recommendation: string; affected_lines: number }
export interface OwnershipMetrics { total_lines_analyzed: number; total_files_analyzed: number; overall_bus_factor: number; bus_factor_distribution: Record<string, number>; knowledge_risk_distribution: Record<string, number>; top_contributors: Array<{ name: string; lines: number; score: number }>; ownership_concentration: number; team_coverage: number }
export interface OwnershipSummary { total_files: number; total_directories: number; total_contributors: number; knowledge_gaps_count: number; critical_gaps: number; high_risk_gaps: number }
export interface OwnershipAnalysisResult { status: string; analysis_time_seconds: number; summary: OwnershipSummary; file_ownership: FileOwnership[]; directory_ownership: DirectoryOwnership[]; expertise_scores: ExpertiseScore[]; knowledge_gaps: KnowledgeGap[]; metrics: OwnershipMetrics }

export interface PatternLocation { file_path: string; line_start: number; line_end: number; language: string }
export interface DTOMismatch { mismatch_id: string; backend_type: string; frontend_type: string; field_name: string; mismatch_type: string; severity: string; recommendation: string; backend_location?: PatternLocation; frontend_location?: PatternLocation }
export interface ValidationDuplication { duplication_id: string; validation_type: string; similarity_score: number; severity: string; recommendation: string; python_location?: PatternLocation; typescript_location?: PatternLocation }
export interface APIContractMismatch { mismatch_id: string; endpoint_path: string; http_method: string; mismatch_type: string; severity: string; details: string; recommendation: string; backend_location?: PatternLocation; frontend_location?: PatternLocation }
export interface PatternMatch { pattern_id: string; similarity_score: number; match_type: string; confidence: number; source_location?: PatternLocation; target_location?: PatternLocation; metadata?: Record<string, string> }
export interface CrossLanguageAnalysisResult { analysis_id: string; scan_timestamp: string; python_files_analyzed: number; typescript_files_analyzed: number; vue_files_analyzed: number; total_patterns: number; critical_issues: number; high_issues: number; medium_issues: number; low_issues: number; dto_mismatches: DTOMismatch[]; validation_duplications: ValidationDuplication[]; api_contract_mismatches: APIContractMismatch[]; pattern_matches: PatternMatch[]; analysis_time_ms: number }

export interface OrphanedFunction { id: string; name: string; full_name: string; module: string; class: string | null; file: string; line: number; is_async: boolean }
export interface PatternAnalysisComponent { runAnalysis: () => Promise<void>; error?: string }
