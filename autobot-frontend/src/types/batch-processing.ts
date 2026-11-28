// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * TypeScript types for Batch Processing
 * Issue #584 - Batch Processing Manager
 */

import type { components } from '@/types/generated/api'
import type { BaseModuleHealthResponse } from './health'

// #21649: every record and request shape below is the backend's own contract
// (autobot-backend/api/batch_jobs.py, schemas in api/schemas_workflows.py), read
// from the generated OpenAPI types. The hand-written copies they replace had
// drifted: the list carried four per-status counts the backend never sends, and
// logs, templates and schedules were wrapped in objects the backend never builds.
type Schemas = components['schemas']

export type BatchJobStatus = Schemas['BatchJobStatus']
export type BatchJobType = Schemas['BatchJobType']
export type BatchJob = Schemas['BatchJob']
export type BatchTemplate = Schemas['BatchTemplate']
export type BatchSchedule = Schemas['BatchSchedule']
export type BatchLogEntry = Schemas['BatchLogEntry']

/** GET /api/batch-jobs: `status_counts` counts every job by status, before the filter. */
export type BatchJobsListResponse = Schemas['BatchJobList']

/** POST /api/batch-jobs body. */
export type CreateBatchJobRequest = Schemas['BatchJobCreate']

/** POST /api/batch-jobs/templates/: `name` and `job_type` travel as query, `parameters` as the body. */
export interface CreateBatchTemplateRequest {
  name: string
  job_type: BatchJobType
  parameters?: Record<string, unknown>
}

/** POST /api/batch-jobs/schedules/: every field travels as query. */
export interface CreateBatchScheduleRequest {
  job_id: string
  cron_expression: string
  enabled?: boolean
}

/** The list filter; each field is a query parameter of GET /api/batch-jobs. */
export interface BatchJobsFilter {
  status?: BatchJobStatus
  job_type?: BatchJobType
  limit?: number
}

/** Batch service health, read from the canonical /api/system/health aggregator (#6902). */
export interface BatchHealthResponse extends BaseModuleHealthResponse {
  active_jobs: number
  total_jobs: number
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
