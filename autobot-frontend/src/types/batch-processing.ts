// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * TypeScript types for Batch Processing
 * Issue #584 - Batch Processing Manager
 */

import type { BaseModuleHealthResponse } from './health'

/**
 * Batch job status enum
 */
export type BatchJobStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'

/**
 * Batch job type enum
 */
export type BatchJobType =
  | 'data_processing'
  | 'file_conversion'
  | 'report_generation'
  | 'backup'
  | 'custom'

/**
 * Single batch job data structure
 */
export interface BatchJob {
  job_id: string
  name: string
  job_type: BatchJobType
  status: BatchJobStatus
  progress: number
  parameters: Record<string, unknown>
  created_at: string
  started_at?: string
  completed_at?: string
  error_message?: string
  result?: Record<string, unknown>
}

/**
 * Batch template for reusable job configurations
 */
export interface BatchTemplate {
  template_id: string
  name: string
  description: string
  job_type: BatchJobType
  default_parameters: Record<string, unknown>
  created_at: string
  updated_at?: string
}

/**
 * Batch schedule for recurring jobs
 */
export interface BatchSchedule {
  schedule_id: string
  name: string
  template_id: string
  cron_expression: string
  enabled: boolean
  last_run?: string
  next_run?: string
  created_at: string
  updated_at?: string
}

/**
 * Filter options for batch jobs list
 */
export interface BatchJobsFilter {
  status?: BatchJobStatus
  job_type?: BatchJobType
  limit?: number
}

/**
 * Batch jobs list response from backend
 */
export interface BatchJobsListResponse {
  jobs: BatchJob[]
  total_count: number
  pending_count: number
  running_count: number
  completed_count: number
  failed_count: number
}

/**
 * Batch templates list response
 */
export interface BatchTemplatesListResponse {
  templates: BatchTemplate[]
  total_count: number
}

/**
 * Batch schedules list response
 */
export interface BatchSchedulesListResponse {
  schedules: BatchSchedule[]
  total_count: number
}

/**
 * Batch service health check response
 */
export interface BatchHealthResponse extends BaseModuleHealthResponse {
  active_jobs: number
  total_jobs: number
}

/**
 * Create batch job request
 */
export interface CreateBatchJobRequest {
  name: string
  job_type: BatchJobType
  parameters?: Record<string, unknown>
  template_id?: string
}

/**
 * Create batch job response
 */
export interface CreateBatchJobResponse {
  job_id: string
  status: string
}

/**
 * Create batch template request
 */
export interface CreateBatchTemplateRequest {
  name: string
  description?: string
  job_type: BatchJobType
  default_parameters?: Record<string, unknown>
}

/**
 * Create batch schedule request
 */
export interface CreateBatchScheduleRequest {
  name: string
  template_id: string
  cron_expression: string
  enabled?: boolean
}

/**
 * Batch job logs response
 */
export interface BatchJobLogsResponse {
  job_id: string
  logs: BatchLogEntry[]
}

/**
 * Single log entry for a batch job
 */
export interface BatchLogEntry {
  timestamp: string
  level: 'debug' | 'info' | 'warning' | 'error'
  message: string
}

/**
 * Status display configuration
 */
export interface StatusConfig {
  label: string
  color: string
  icon: string
  bgClass: string
  textClass: string
}

/**
 * Map of batch job statuses to display configuration
 */
export const BATCH_STATUS_CONFIG: Record<BatchJobStatus, StatusConfig> = {
  pending: {
    label: 'Pending',
    color: 'gray',
    icon: 'fas fa-clock',
    bgClass: 'bg-gray-100',
    textClass: 'text-gray-700'
  },
  running: {
    label: 'Running',
    color: 'blue',
    icon: 'fas fa-spinner fa-spin',
    bgClass: 'bg-blue-100',
    textClass: 'text-blue-700'
  },
  completed: {
    label: 'Completed',
    color: 'green',
    icon: 'fas fa-check-circle',
    bgClass: 'bg-green-100',
    textClass: 'text-green-700'
  },
  failed: {
    label: 'Failed',
    color: 'red',
    icon: 'fas fa-times-circle',
    bgClass: 'bg-red-100',
    textClass: 'text-red-700'
  },
  cancelled: {
    label: 'Cancelled',
    color: 'yellow',
    icon: 'fas fa-ban',
    bgClass: 'bg-yellow-100',
    textClass: 'text-yellow-700'
  }
}

/**
 * Map of batch job types to display labels
 */
export const BATCH_TYPE_LABELS: Record<BatchJobType, string> = {
  data_processing: 'Data Processing',
  file_conversion: 'File Conversion',
  report_generation: 'Report Generation',
  backup: 'Backup',
  custom: 'Custom'
}

/**
 * Map of batch job types to icons
 */
export const BATCH_TYPE_ICONS: Record<BatchJobType, string> = {
  data_processing: 'fas fa-database',
  file_conversion: 'fas fa-file-export',
  report_generation: 'fas fa-file-alt',
  backup: 'fas fa-cloud-upload-alt',
  custom: 'fas fa-cog'
}

/**
 * Helper to check if job is in a terminal state
 */
export function isTerminalStatus(status: BatchJobStatus): boolean {
  return ['completed', 'failed', 'cancelled'].includes(status)
}

/**
 * Helper to check if job can be cancelled
 */
export function canCancelJob(job: BatchJob): boolean {
  return ['pending', 'running'].includes(job.status)
}

