// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Code Intelligence TypeScript interfaces
 * Issue #772 - Code Intelligence & Repository Analysis
 */

// Severity levels used across all analyzers
export type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical'

// Anti-pattern types
export interface AntiPatternType {
  name: string
  category: string
  description: string
  threshold: string
}

export interface AntiPatternResult {
  pattern_type: string
  severity: Severity
  file_path: string
  line_number: number
  message: string
  suggestion: string
}

export interface AnalysisReport {
  status: string
  timestamp: string
  report: {
    total_files: number
    total_issues: number
    anti_patterns: AntiPatternResult[]
    severity_distribution: Record<Severity, number>
  }
}

// Health score response
export interface HealthScoreResponse {
  status: string
  timestamp: string
  path: string
  health_score: number
  grade: string
  total_issues: number
  files_analyzed: number
  severity_breakdown: Record<Severity, number>
}

// Security types
export interface VulnerabilityType {
  type: string
  description: string
  owasp: string
  cwe?: string
}

export interface SecurityFinding {
  vulnerability_type: string
  severity: Severity
  file_path: string
  line_number: number
  code_snippet: string
  message: string
  remediation: string
  owasp_category: string
}

export interface SecurityScoreResponse {
  status: string
  timestamp: string
  path: string
  security_score: number
  grade: string
  risk_level: string
  status_message: string
  total_findings: number
  critical_issues: number
  high_issues: number
  files_analyzed: number
  severity_breakdown: Record<Severity, number>
  owasp_breakdown: Record<string, number>
}

// Performance types
export interface PerformanceIssueType {
  type: string
  category: string
  description: string
}

export interface PerformanceFinding {
  issue_type: string
  severity: Severity
  file_path: string
  line_number: number
  message: string
  recommendation: string
  estimated_impact: string
}

export interface PerformanceScoreResponse {
  status: string
  timestamp: string
  path: string
  performance_score: number
  grade: string
  status_message: string
  total_issues: number
  critical_issues: number
  high_issues: number
  files_analyzed: number
  severity_breakdown: Record<Severity, number>
  top_issues: string[]
}

// Redis optimization types
export interface RedisOptimizationType {
  name: string
  category: string
  description: string
  recommendation: string
}

export interface RedisHealthScoreResponse {
  status: string
  timestamp: string
  path: string
  health_score: number
  grade: string
  status_message: string
  total_optimizations: number
  files_with_issues: number
  severity_breakdown: Record<Severity, number>
  category_breakdown: Record<string, number>
}

// Report types
export interface ReportResponse {
  status: string
  timestamp: string
  path: string
  format: 'json' | 'markdown'
  report: string | object
}

// Redis optimization finding (from analyze endpoint)
export interface RedisOptimizationFinding {
  optimization_type: string
  severity: Severity
  file_path: string
  line_number: number
  message: string
  recommendation: string
  category: string
}

// Analysis response types
export interface SecurityAnalysisResponse {
  status: string
  timestamp: string
  path: string
  summary: Record<string, unknown>
  findings: SecurityFinding[]
  total_findings: number
}

export interface PerformanceAnalysisResponse {
  status: string
  timestamp: string
  path: string
  summary: Record<string, unknown>
  findings: PerformanceFinding[]
  total_findings: number
}

export interface RedisAnalysisResponse {
  status: string
  timestamp: string
  path: string
  optimizations: RedisOptimizationFinding[]
  summary: Record<string, unknown>
}
