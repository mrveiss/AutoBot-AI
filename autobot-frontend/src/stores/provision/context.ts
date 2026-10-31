// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Provision store state, runtime and constants (#19834, #7096).
 *
 * `state` is what the store exposes; `runtime` is what it keeps to itself (the socket, the
 * line cursor, the timers), one set per store instance exactly as the SLM store's closure
 * variables were.
 */
import { ref, type Ref } from 'vue'
import type { ProvisionLogEntry, ProvisionStatus } from '@autobot/slm-contract'
import type { UsePollingJobReturn } from '@/composables/usePollingJob'
import { slmApi, type SlmApi } from '@/utils/slmApi'

export type { ProvisionLogEntry, ProvisionStatus }

export const POLL_INTERVAL_MS = 3000
/** Clear a stuck "Still running..." after this long without a WebSocket message. */
export const HEARTBEAT_STALE_MS = 30000
export const STALE_CHECK_INTERVAL_MS = 5000

function positiveInt(raw: unknown, fallback: number): number {
  const parsed = Number(raw)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback
}

/** The dashboard policy (#19482): a poller stops after this many consecutive failed reads. */
export const POLL_CONSECUTIVE_ERROR_LIMIT = positiveInt(import.meta.env.VITE_SLM_POLL_ERROR_LIMIT, 5)

export interface ProvisionState {
  status: Ref<ProvisionStatus>
  stage: Ref<string>
  elapsedSeconds: Ref<number>
  currentTask: Ref<string>
  currentPhase: Ref<string>
  completedPhases: Ref<Set<string>>
  logs: Ref<ProvisionLogEntry[]>
  error: Ref<string | null>
  startedAt: Ref<number | null>
  finishedAt: Ref<number | null>
  wsConnected: Ref<boolean>
}

export interface ProvisionRuntime {
  ws: WebSocket | null
  linesSeen: number
  lastWsMessageAt: number
  staleTaskTimer: number | null
  /** Set by the store's setup, which owns the poller's effect scope. */
  poller: UsePollingJobReturn<void> | null
}

export interface ProvisionCtx {
  api: SlmApi
  state: ProvisionState
  runtime: ProvisionRuntime
}

export function createProvisionState(): ProvisionState {
  return {
    status: ref('idle'),
    stage: ref(''),
    elapsedSeconds: ref(0),
    currentTask: ref(''),
    currentPhase: ref(''),
    completedPhases: ref(new Set<string>()),
    logs: ref([]),
    error: ref(null),
    startedAt: ref(null),
    finishedAt: ref(null),
    wsConnected: ref(false),
  }
}

export function createProvisionContext(api: SlmApi = slmApi): ProvisionCtx {
  const runtime: ProvisionRuntime = { ws: null, linesSeen: 0, lastWsMessageAt: 0, staleTaskTimer: null, poller: null }
  return { api, state: createProvisionState(), runtime }
}

export function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}m ${secs}s`
}
