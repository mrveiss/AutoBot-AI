// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * SLM Type Definitions
 */

export type NodeStatus = 'registered' | 'healthy' | 'degraded' | 'unhealthy' | 'offline'

export type NodeRole = 'redis' | 'llm' | 'npu' | 'browser' | 'orchestrator'

export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown'

export interface NodeHealth {
  status: HealthStatus
  cpu_percent: number
  memory_percent: number
  disk_percent: number
  last_heartbeat: string | null
  services: ServiceHealth[]
}

export interface ServiceHealth {
  name: string
  status: HealthStatus
  details: Record<string, unknown>
}

export interface SLMNode {
  node_id: string
  hostname: string
  ip_address: string
  status: NodeStatus
  roles: NodeRole[]
  health: NodeHealth | null
  created_at: string
  updated_at: string
}

export interface Deployment {
  deployment_id: string
  node_id: string
  roles: NodeRole[]
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'rolled_back'
  started_at: string
  completed_at: string | null
  error: string | null
  playbook_output: string | null
}

export interface DeploymentRequest {
  node_id: string
  roles: NodeRole[]
  force?: boolean
}

export interface Backup {
  backup_id: string
  node_id: string
  service_type: string
  backup_path: string
  state: 'pending' | 'in_progress' | 'completed' | 'failed'
  size_bytes: number
  started_at: string | null
  completed_at: string | null
  error: string | null
  checksum: string | null
}

export interface BackupRequest {
  node_id: string
  service_type?: string
  backup_name?: string
}

export interface Replication {
  replication_id: string
  primary_node_id: string
  replica_node_id: string
  service_type: string
  state: 'pending' | 'syncing' | 'synced' | 'failed' | 'stopped'
  sync_progress: number
  started_at: string | null
  completed_at: string | null
  error: string | null
  details: Record<string, unknown>
}

export interface ReplicationRequest {
  primary_node_id: string
  replica_node_id: string
  service_type?: string
}

export interface MaintenanceWindow {
  id: string
  node_id: string
  start_time: string
  end_time: string
  reason: string
  auto_drain: boolean
  created_at: string
}

export interface SLMWebSocketMessage {
  type: 'health_update' | 'deployment_status' | 'backup_status' | 'node_status'
  node_id: string
  data: Record<string, unknown>
  timestamp: string
}

export interface FleetSummary {
  total_nodes: number
  healthy_nodes: number
  degraded_nodes: number
  unhealthy_nodes: number
  offline_nodes: number
}
