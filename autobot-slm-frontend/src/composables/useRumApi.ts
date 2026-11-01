// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Real-user-monitoring (RUM) API (#18277): the main backend's `/rum` routes
 * (autobot-backend/api/rum.py), read through the shared main-backend client.
 *
 * `GET /status` answers any signed-in user; `GET /export`, `POST /config`, `POST /disable` and
 * `POST /clear` are admin-only on the backend. The envelope types are the generated contract's.
 * The contract types the inner payloads as open objects (the route returns the module's in-memory
 * dicts), so `RumStatus` and `RumExport` below declare the fields the screen reads, taken from
 * `get_rum_status` and `export_rum_data` in rum.py and `track_session` in rum_ingest_bounds.py.
 */

import type { components as backend } from '@autobot/backend-contract'
import { createAutobotBackendClient } from '@/composables/useAutobotApi'

type BackendSchemas = backend['schemas']

/** The collection settings; `POST /config` replaces all of them, so a toggle sends the whole object. */
export type RumConfig = BackendSchemas['RumConfig']
export type RumClearResponse = BackendSchemas['RUMClearResponse']
export type RumDisableResponse = BackendSchemas['RUMDisableResponse']
export type RumConfigResponse = BackendSchemas['RUMConfigResponse']

export interface RumStatistics {
  total_events: number
  total_sessions: number
  /** Sessions with activity in the last 30 minutes. */
  active_sessions: number
  events_today: number
}

/** `rum_status` of GET /status. */
export interface RumStatus {
  enabled: boolean
  config: RumConfig
  statistics: RumStatistics
}

export interface RumSession {
  start_time: string
  last_activity: string
  event_count: number
  user_agent: string
  initial_url: string
}

export interface RumEvent {
  type: string
  timestamp: string
  sessionId: string
  url: string
  userAgent: string
  server_timestamp: string
  data: Record<string, unknown>
}

/** `data` of GET /export: all sessions, the latest 1000 events, and the totals over every event held. */
export interface RumExport {
  export_timestamp: string
  config: RumConfig
  sessions: Record<string, RumSession>
  events: RumEvent[]
  summary: { total_events: number; total_sessions: number; event_types: Record<string, number> }
}

export function useRumApi() {
  const client = createAutobotBackendClient()

  async function getStatus(): Promise<RumStatus> {
    const response = await client.get<{ status: string; rum_status: unknown }>('/rum/status', { maxRetries: 1 })
    return response.rum_status as RumStatus
  }

  /** Admin only. */
  async function exportData(): Promise<RumExport> {
    const response = await client.get<{ status: string; data: unknown }>('/rum/export', { maxRetries: 1 })
    return response.data as RumExport
  }

  /** Admin only. Turns collection on: `/config` has no partial update, so the current settings go back with `enabled: true`. */
  function enable(current: RumConfig): Promise<RumConfigResponse> {
    return client.post<RumConfigResponse>('/rum/config', { ...current, enabled: true })
  }

  /** Admin only. Turns collection off; the events already held stay until they are cleared. */
  function disable(): Promise<RumDisableResponse> {
    return client.post<RumDisableResponse>('/rum/disable')
  }

  /** Admin only. Drops every held event and session; answers how many of each. */
  function clear(): Promise<RumClearResponse> {
    return client.post<RumClearResponse>('/rum/clear')
  }

  return { getStatus, exportData, enable, disable, clear }
}
