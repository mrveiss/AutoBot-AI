// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Reasoning Trace Composable (#3232)
 *
 * Subscribes to agent chain-of-thought WebSocket events and exposes a
 * reactive list of trace entries for the ReasoningTrace component.
 *
 * Event types handled:
 *   agent.step.start    – a graph node is beginning
 *   agent.step.complete – a graph node has finished
 *   agent.tool.call     – a tool call is about to dispatch
 *   agent.tool.result   – a tool call result has arrived
 *   agent.llm.chunk     – a streaming LLM token chunk
 *   agent.plan          – plan decomposition from the overseer
 *
 * Usage:
 *   const { entries, isActive, clear } = useReasoningTrace(sessionId)
 *   // entries is a reactive array of TraceEntry[]
 */

import { ref, computed, isRef, onUnmounted, getCurrentInstance, type Ref, type ComputedRef, type MaybeRef } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import globalWebSocketService from '@/services/GlobalWebSocketService'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TraceEntryKind =
  | 'step_start'
  | 'step_complete'
  | 'tool_call'
  | 'tool_result'
  | 'llm_chunk'
  | 'plan'

export interface TraceEntry {
  id: string
  kind: TraceEntryKind
  label: string
  detail?: string
  durationMs?: number
  success?: boolean
  ts: number
}

export interface UseReasoningTraceReturn {
  /** Reactive list of trace entries for the current response turn. */
  entries: Ref<TraceEntry[]>
  /** True while at least one step is still in progress. */
  isActive: ComputedRef<boolean>
  /** Clear all entries (called when a new user message is sent). */
  clear: () => void
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Maximum number of entries kept in memory before trimming the head. */
const MAX_ENTRIES = 200

// ---------------------------------------------------------------------------
// Logger
// ---------------------------------------------------------------------------

const logger = createLogger('useReasoningTrace')

// ---------------------------------------------------------------------------
// ID generation
// ---------------------------------------------------------------------------

let _seq = 0
function nextId(): string {
  return `cot-${++_seq}`
}

// ---------------------------------------------------------------------------
// Event type → handler mapping
// ---------------------------------------------------------------------------

type RawPayload = Record<string, unknown>

const COT_EVENT_TYPES = [
  'agent.step.start',
  'agent.step.complete',
  'agent.tool.call',
  'agent.tool.result',
  'agent.llm.chunk',
  'agent.plan',
] as const

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useReasoningTrace(
  sessionId?: MaybeRef<string | null | undefined>,
): UseReasoningTraceReturn {
  // Normalise to a computed ref so that reactive values (e.g. computed(() =>
  // store.currentSessionId)) are read at handler call-time, not frozen at
  // setup time. Plain string / null / undefined values still work unchanged.
  const _sessionId = isRef(sessionId)
    ? sessionId
    : computed(() => sessionId as string | null | undefined)

  const entries = ref<TraceEntry[]>([])
  const activeSteps = ref(0)
  const unsubscribers: Array<() => void> = []

  const isActive = computed(() => activeSteps.value > 0)

  function clear(): void {
    entries.value = []
    activeSteps.value = 0
  }

  function push(entry: TraceEntry): void {
    entries.value.push(entry)
    if (entries.value.length > MAX_ENTRIES) {
      entries.value = entries.value.slice(-MAX_ENTRIES)
    }
  }

  // -------------------------------------------------------------------------
  // Handler per event type
  // -------------------------------------------------------------------------

  function handleStepStart(payload: RawPayload): void {
    // Filter to the relevant session when one is specified.
    if (_sessionId.value && payload['session_id'] && payload['session_id'] !== _sessionId.value) {
      return
    }
    activeSteps.value++
    push({
      id: nextId(),
      kind: 'step_start',
      label: String(payload['step_name'] ?? 'step'),
      detail: payload['agent_type'] ? String(payload['agent_type']) : undefined,
      ts: Number(payload['ts'] ?? Date.now() / 1000),
    })
  }

  function handleStepComplete(payload: RawPayload): void {
    if (_sessionId.value && payload['session_id'] && payload['session_id'] !== _sessionId.value) {
      return
    }
    activeSteps.value = Math.max(0, activeSteps.value - 1)
    push({
      id: nextId(),
      kind: 'step_complete',
      label: String(payload['step_name'] ?? 'step'),
      detail: payload['output_summary'] ? String(payload['output_summary']) : undefined,
      durationMs: payload['duration_ms'] != null ? Number(payload['duration_ms']) : undefined,
      ts: Number(payload['ts'] ?? Date.now() / 1000),
    })
  }

  function handleToolCall(payload: RawPayload): void {
    if (_sessionId.value && payload['session_id'] && payload['session_id'] !== _sessionId.value) {
      return
    }
    push({
      id: nextId(),
      kind: 'tool_call',
      label: String(payload['tool_name'] ?? 'tool'),
      ts: Number(payload['ts'] ?? Date.now() / 1000),
    })
  }

  function handleToolResult(payload: RawPayload): void {
    if (_sessionId.value && payload['session_id'] && payload['session_id'] !== _sessionId.value) {
      return
    }
    push({
      id: nextId(),
      kind: 'tool_result',
      label: String(payload['tool_name'] ?? 'tool'),
      detail: payload['result_summary'] ? String(payload['result_summary']) : undefined,
      durationMs: payload['duration_ms'] != null ? Number(payload['duration_ms']) : undefined,
      success: payload['success'] !== false,
      ts: Number(payload['ts'] ?? Date.now() / 1000),
    })
  }

  function handleLlmChunk(payload: RawPayload): void {
    if (_sessionId.value && payload['session_id'] && payload['session_id'] !== _sessionId.value) {
      return
    }
    // For chunk events we update the last llm_chunk entry in-place to avoid
    // creating one entry per token (which would be thousands per response).
    const last = entries.value[entries.value.length - 1]
    if (last && last.kind === 'llm_chunk') {
      last.label += String(payload['chunk'] ?? '')
      last.ts = Number(payload['ts'] ?? Date.now() / 1000)
    } else {
      push({
        id: nextId(),
        kind: 'llm_chunk',
        label: String(payload['chunk'] ?? ''),
        ts: Number(payload['ts'] ?? Date.now() / 1000),
      })
    }
  }

  function handlePlan(payload: RawPayload): void {
    if (_sessionId.value && payload['session_id'] && payload['session_id'] !== _sessionId.value) {
      return
    }
    const steps = Array.isArray(payload['steps'])
      ? (payload['steps'] as string[])
      : []
    push({
      id: nextId(),
      kind: 'plan',
      label: `Plan (${steps.length} steps)`,
      detail: steps.slice(0, 5).join(' → '),
      ts: Number(payload['ts'] ?? Date.now() / 1000),
    })
  }

  // -------------------------------------------------------------------------
  // Map event type string → handler
  // -------------------------------------------------------------------------

  const handlerMap: Record<string, (payload: RawPayload) => void> = {
    'agent.step.start': handleStepStart,
    'agent.step.complete': handleStepComplete,
    'agent.tool.call': handleToolCall,
    'agent.tool.result': handleToolResult,
    'agent.llm.chunk': handleLlmChunk,
    'agent.plan': handlePlan,
  }

  // -------------------------------------------------------------------------
  // Subscribe via GlobalWebSocketService
  // -------------------------------------------------------------------------

  for (const eventType of COT_EVENT_TYPES) {
    const unsubscribe = globalWebSocketService.on(eventType, (raw: unknown) => {
      try {
        // GlobalWebSocketService delivers the whole WebSocket message object.
        // EventManager publishes: { type: eventType, payload: {...} }
        const msg = raw as Record<string, unknown>
        const payload =
          (msg['payload'] as RawPayload | undefined) ??
          (msg as RawPayload)
        handlerMap[eventType]?.(payload)
      } catch (err) {
        logger.error(`Error handling ${eventType}:`, err)
      }
    })
    unsubscribers.push(unsubscribe)
  }

  // -------------------------------------------------------------------------
  // Auto-cleanup on component unmount
  // -------------------------------------------------------------------------

  const instance = getCurrentInstance()
  if (instance) {
    onUnmounted(() => {
      unsubscribers.forEach((u) => u())
    })
  } else {
    logger.warn('useReasoningTrace: not inside a Vue component, cleanup must be manual')
  }

  return { entries, isActive, clear }
}

export default useReasoningTrace
