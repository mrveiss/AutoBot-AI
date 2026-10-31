// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * `slmApi` NPU calls (#19834, ported from the SLM app's `useSlmApi`, Issue #255 / #590).
 *
 * The contract types `detectionStatus`, `strategy` and `failure_action` as bare `string`; the SLM
 * types narrow them to the value sets the backend enumerates (see the notes in
 * `libs/slm-contract/src/npu.ts`). The narrowing is the one cast per call, made here at the seam.
 */
import type {
  NPUFleetMetrics,
  NPULoadBalancingConfig,
  NPUNodeStatus,
  NPUWorkerConfig,
  NPUWorkerMetrics,
} from '@autobot/slm-contract'
import { slmRequest, slmRequestAs } from './transport'

/** What the SLM backend answers when an NPU role is assigned (`NPURoleAssignResponse`). */
export interface NpuRoleResult {
  success: boolean
  message: string
  node_id: string
  detection_triggered?: boolean
}

/** The `remove npu role` 200 is a bare `{[key]: unknown}` in the contract; this is its shape. */
export interface NpuRoleRemoval {
  success: boolean
  message: string
}

export interface NpuDetectionResult {
  success: boolean
  message: string
  node_id: string
  capabilities?: NPUNodeStatus['capabilities']
}

export interface NpuConfigResult {
  success: boolean
  message: string
  config: NPUWorkerConfig
}

const nodeParams = (nodeId: string) => ({ params: { node_id: nodeId } })

export async function getNpuNodes(): Promise<NPUNodeStatus[]> {
  const body = await slmRequest('get', '/api/npu/nodes')
  return body.nodes as NPUNodeStatus[]
}

export async function getNpuStatus(nodeId: string): Promise<NPUNodeStatus> {
  return (await slmRequest('get', '/api/npu/nodes/{node_id}/status', nodeParams(nodeId))) as NPUNodeStatus
}

export async function triggerNpuDetection(nodeId: string, force: boolean = false): Promise<NpuDetectionResult> {
  return slmRequest('post', '/api/npu/nodes/{node_id}/detect', { ...nodeParams(nodeId), body: { force } })
}

export async function assignNpuRole(nodeId: string): Promise<NpuRoleResult> {
  return slmRequest('post', '/api/npu/nodes/{node_id}/assign-role', nodeParams(nodeId))
}

export async function removeNpuRole(nodeId: string): Promise<NpuRoleRemoval> {
  return slmRequestAs<NpuRoleRemoval, '/api/npu/nodes/{node_id}/role', 'delete'>(
    'delete',
    '/api/npu/nodes/{node_id}/role',
    nodeParams(nodeId),
  )
}

export async function getNpuLoadBalancing(): Promise<NPULoadBalancingConfig> {
  return (await slmRequest('get', '/api/npu/load-balancing')) as NPULoadBalancingConfig
}

export async function updateNpuLoadBalancing(config: NPULoadBalancingConfig): Promise<void> {
  await slmRequest('post', '/api/npu/load-balancing', { body: config })
}

export async function getNpuFleetMetrics(): Promise<NPUFleetMetrics> {
  return (await slmRequest('get', '/api/npu/metrics')) as NPUFleetMetrics
}

export async function getNpuNodeMetrics(nodeId: string): Promise<NPUWorkerMetrics> {
  return slmRequest('get', '/api/npu/nodes/{node_id}/metrics', nodeParams(nodeId))
}

export async function getNpuWorkerConfig(nodeId: string): Promise<NPUWorkerConfig> {
  return (await slmRequest('get', '/api/npu/nodes/{node_id}/config', nodeParams(nodeId))) as NPUWorkerConfig
}

export async function updateNpuWorkerConfig(nodeId: string, config: NPUWorkerConfig): Promise<NpuConfigResult> {
  const body = await slmRequest('put', '/api/npu/nodes/{node_id}/config', { ...nodeParams(nodeId), body: config })
  return { success: body.success, message: body.message, config: body.config as NPUWorkerConfig }
}
