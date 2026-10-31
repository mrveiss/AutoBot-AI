// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * SLM contract types: NPU workers
 */

import type { components } from './generated/api'

// =============================================================================
// NPU Worker Types (Issue #255 - NPU Fleet Integration)
// =============================================================================

// #15226: generated from the SLM schema (models/npu_schemas.py) -- the one
// vocabulary the schema, the API and this UI share, not a hand-kept copy.
export type NPUDeviceType = components['schemas']['NPUDeviceType']

export type NPULoadBalancingStrategy = 'round-robin' | 'least-loaded' | 'model-affinity'

/**
 * NPU device capabilities reported by detection (#13138).
 *
 * `deviceType` is deliberately NOT narrowed back to `NPUDeviceType`: it is
 * copied verbatim out of an external NPU worker's `/health` payload
 * (`data.get("deviceType", "unknown")`, api/npu.py:83), so nothing constrains
 * it to the four known values. All three renderers already fall through to the
 * raw string for an unknown device (NPUNodeCard.vue:50,
 * NPUWorkerMonitor.vue:97, NPUDetailsPanel.vue:54), so the union was an
 * unverifiable claim the UI never relied on. `NPUDeviceType` stays exported as
 * the set of values that get a friendly label.
 */
export type NPUCapabilities = components['schemas']['NPUCapabilities']

// Each node's GPUs, from its agent's heartbeat (#16280, #16281, #15226).
export type GPUReportState = components['schemas']['GPUReportState']
export type GPUDevice = components['schemas']['GPUDevice']
export type GPUNodeStatus = components['schemas']['GPUNodeStatus']
export type GPUNodeListResponse = components['schemas']['GPUNodeListResponse']

export interface NPUNodeStatus {
  node_id: string
  capabilities: NPUCapabilities | null
  loadedModels: string[]
  queueDepth: number
  lastHealthCheck: string | null
  detectionStatus: 'pending' | 'detected' | 'failed' | 'unavailable'
  detectionError?: string
}

/**
 * NPU load-balancing configuration (#13138).
 *
 * `strategy` is a bare `str` on the model (models/schemas.py:2115), but the
 * value set is enumerated by `NPULoadBalancingStrategy`
 * (models/schemas.py:2078-2085) and matches this union exactly, so the
 * narrowing is kept by intersection. `modelAffinity` is `default_factory=dict`,
 * hence optional in the contract.
 */
export type NPULoadBalancingConfig =
  components['schemas']['NPULoadBalancingConfig'] & {
    strategy: NPULoadBalancingStrategy
  }

export interface NPUModelInfo {
  name: string
  size_mb: number
  loaded: boolean
  inference_time_ms: number | null
  total_requests: number
}

// NPU Metrics & Config Types (Issue #590 - NPU Dashboard Improvements)

/**
 * Per-worker NPU metrics (#13138). `temperature_celsius` and `timestamp` are
 * optional AND nullable in the contract; the hand-written declaration required
 * both to be present.
 */
export type NPUWorkerMetrics = components['schemas']['NPUWorkerMetrics']

export interface NPUFleetMetrics {
  total_nodes: number
  online_nodes: number
  total_inference_count: number
  avg_utilization: number
  avg_latency_ms: number
  total_throughput_rps: number
  total_queue_depth: number
  node_metrics: NPUWorkerMetrics[]
}

/**
 * Configuration for an individual NPU worker (models/schemas.py:2196), derived
 * from the generated contract (#13138).
 *
 * `failure_action` is a bare `str` with only a `retry` default server-side
 * (schemas.py:2202); its sole construction site is the four-option `<select>`
 * at `components/fleet/NPUDetailsPanel.vue:383-386`, so the union is a real
 * frontend-side guarantee and is kept by intersection.
 */
export type NPUWorkerConfig = components['schemas']['NPUWorkerConfig'] & {
  failure_action: 'retry' | 'failover' | 'skip' | 'alert'
}
