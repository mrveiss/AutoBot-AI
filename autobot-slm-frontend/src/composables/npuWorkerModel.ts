// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The main backend's NPU worker shapes, as /api/npu/workers serves them, and the
 * flattening the SLM's NPU Workers table uses (#15536). useAutobotApi re-exports these.
 */

/** The main backend's worker definition (autobot-backend/models/npu_models.py NPUWorkerDefinition). */
export interface NPUWorkerDefinition {
  id: string
  name: string
  url: string
  platform: string
  enabled: boolean
  priority: number
  weight: number
  max_concurrent_tasks: number
}

/** GET /api/npu/workers item (npu_models.py NPUWorkerDetails); only the fields read here. */
export interface NPUWorkerDetails {
  config: NPUWorkerDefinition
  status: {
    status: NPUWorker['status']
    current_load: number
    last_heartbeat: string | null
  }
}

/** POST /api/npu/workers/{id}/test (npu_models.py WorkerTestResult); a failed test is 200 with success false. */
export interface NPUWorkerTestResult {
  worker_id: string
  success: boolean
  response_time_ms: number | null
  error_message: string | null
}

/** One row of the NPU workers table, flattened from NPUWorkerDetails. */
export interface NPUWorker {
  id: string
  hostname: string
  ip_address: string
  status: 'online' | 'offline' | 'busy' | 'error' | 'unknown' | 'degraded'
  capabilities: string[]
  /** Active tasks as a percentage of the worker's max_concurrent_tasks. */
  current_load: number
  last_heartbeat: string
  definition: NPUWorkerDefinition
}

export function toNPUWorker(details: NPUWorkerDetails): NPUWorker {
  const { config, status } = details
  const capacity = Math.max(config.max_concurrent_tasks, 1)
  return {
    id: config.id,
    hostname: config.name,
    ip_address: urlHost(config.url),
    status: status.status,
    capabilities: [],
    current_load: Math.min(100, Math.round((status.current_load / capacity) * 100)),
    last_heartbeat: status.last_heartbeat ?? '',
    definition: config,
  }
}

function urlHost(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return url
  }
}
