// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * useWorkflowPlans (#19938): the Workflow Planner's API surface and list state.
 *
 * The routes are a 404 while the planner switch is off, so a 404 on the list is reported as
 * `unavailable`, which is a different answer from `error` and from an empty list. Plan-level
 * calls return the whole plan: the server recomputes the status on every write.
 */
import { ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { describeApiError } from '@/composables/llc/apiErrorMessage'
import {
  isNotFoundError,
  type BreakdownBody,
  type GateResponse,
  type MapBody,
  type MapResponse,
  type OneNumberBody,
  type Plan,
  type PlanCreate,
  type PlanSummary,
  type Label,
} from '@/composables/llc/workflowPlanTypes'

const BASE = '/api/llc/company-os/workflow-plans'

export type PlanListState = 'loading' | 'ready' | 'unavailable' | 'error'

const planUrl = (key: string, tail = '') => `${BASE}/${encodeURIComponent(key)}${tail}`

export function useWorkflowPlans() {
  const api = useApiClient()
  const plans = ref<PlanSummary[]>([])
  const state = ref<PlanListState>('loading')
  const errorMessage = ref('')

  async function load(fallback: string): Promise<void> {
    state.value = 'loading'
    try {
      plans.value = (await api.get<PlanSummary[]>(BASE)) ?? []
      state.value = 'ready'
    } catch (err: unknown) {
      state.value = isNotFoundError(err) ? 'unavailable' : 'error'
      errorMessage.value = describeApiError(err, fallback)
    }
  }

  const create = (body: PlanCreate) => api.post<Plan>(BASE, body)
  const get = (key: string) => api.get<Plan>(planUrl(key))
  const gate = (key: string) => api.get<GateResponse>(planUrl(key, '/gate'))
  const putMap = (key: string, body: MapBody) => api.put<MapResponse>(planUrl(key, '/map'), body)
  const setWaitNote = (key: string, handoff: string, note: string | null) =>
    api.patch<Plan>(planUrl(key, `/handoffs/${encodeURIComponent(handoff)}`), { wait_note: note })
  const putMetric = (key: string, step: string, body: unknown) =>
    api.put<Plan>(planUrl(key, `/steps/${encodeURIComponent(step)}/metric`), body)
  const deleteMetric = (key: string, step: string) =>
    api.delete<Plan>(planUrl(key, `/steps/${encodeURIComponent(step)}/metric`))
  const putOneNumber = (key: string, body: OneNumberBody) => api.put<Plan>(planUrl(key, '/one-number'), body)
  const putBreakdown = (key: string, step: string, body: BreakdownBody) =>
    api.put<Plan>(planUrl(key, `/steps/${encodeURIComponent(step)}/breakdown`), body)
  const classifySubStep = (key: string, sub: string, classification: Label | null) =>
    api.patch<Plan>(planUrl(key, `/sub-steps/${encodeURIComponent(sub)}`), { classification })
  const acknowledgeByHand = (key: string) => api.post<Plan>(planUrl(key, '/by-hand-acknowledgement'))

  return {
    plans,
    state,
    errorMessage,
    load,
    create,
    get,
    gate,
    putMap,
    setWaitNote,
    putMetric,
    deleteMetric,
    putOneNumber,
    putBreakdown,
    classifySubStep,
    acknowledgeByHand,
  }
}

export type WorkflowPlansApi = ReturnType<typeof useWorkflowPlans>
