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
import { planRequest } from '@/composables/llc/workflowPlanRequest'
import { describeApiError } from '@/composables/llc/apiErrorMessage'
import {
  isNotFoundError,
  type BreakdownBody,
  type Edge,
  type EdgeCaseBody,
  type EdgeCasePatch,
  type EdgePatch,
  type Lane,
  type LanePatch,
  type ReturnKind,
  type Step,
  type StepPatch,
  type MapBody,
  type OneNumberBody,
  type PlanCreate,
  type PlanSummary,
  type Label,
} from '@/composables/llc/workflowPlanTypes'

const ROOT = '/api/llc/company-os/workflow-plans'

export type PlanListState = 'loading' | 'ready' | 'unavailable' | 'error'

export function useWorkflowPlans() {
  const api = useApiClient()
  const plans = ref<PlanSummary[]>([])
  const state = ref<PlanListState>('loading')
  const errorMessage = ref('')

  async function load(fallback: string): Promise<void> {
    state.value = 'loading'
    try {
      plans.value = (await planRequest(api, 'get', ROOT)) ?? []
      state.value = 'ready'
    } catch (err: unknown) {
      state.value = isNotFoundError(err) ? 'unavailable' : 'error'
      errorMessage.value = describeApiError(err, fallback)
    }
  }

  const create = (body: PlanCreate) => planRequest(api, 'post', ROOT, {}, body)
  const get = (key: string) => planRequest(api, 'get', '/api/llc/company-os/workflow-plans/{plan_key}', { plan_key: key })
  const gate = (key: string) => planRequest(api, 'get', '/api/llc/company-os/workflow-plans/{plan_key}/gate', { plan_key: key })
  const putMap = (key: string, body: MapBody) => planRequest(api, 'put', '/api/llc/company-os/workflow-plans/{plan_key}/map', { plan_key: key }, body)
  const setWaitNote = (key: string, handoff: string, note: string | null) =>
    planRequest(api, 'patch', '/api/llc/company-os/workflow-plans/{plan_key}/handoffs/{handoff_key}', { plan_key: key, handoff_key: handoff }, { wait_note: note })
  const putMetric = (key: string, step: string, body: unknown) =>
    planRequest(api, 'put', '/api/llc/company-os/workflow-plans/{plan_key}/steps/{step_key}/metric', { plan_key: key, step_key: step }, body)
  const deleteMetric = (key: string, step: string) =>
    planRequest(api, 'delete', '/api/llc/company-os/workflow-plans/{plan_key}/steps/{step_key}/metric', { plan_key: key, step_key: step })
  const putOneNumber = (key: string, body: OneNumberBody) =>
    planRequest(api, 'put', '/api/llc/company-os/workflow-plans/{plan_key}/one-number', { plan_key: key }, body)
  const putBreakdown = (key: string, step: string, body: BreakdownBody) =>
    planRequest(api, 'put', '/api/llc/company-os/workflow-plans/{plan_key}/steps/{step_key}/breakdown', { plan_key: key, step_key: step }, body)
  const addEdgeCase = (key: string, step: string, body: EdgeCaseBody) =>
    planRequest(api, 'post', '/api/llc/company-os/workflow-plans/{plan_key}/steps/{step_key}/edge-cases', { plan_key: key, step_key: step }, body)
  const addLane = (key: string, body: Lane) =>
    planRequest(api, 'post', '/api/llc/company-os/workflow-plans/{plan_key}/lanes', { plan_key: key }, body)
  const patchLane = (key: string, lane: string, body: LanePatch) =>
    planRequest(api, 'patch', '/api/llc/company-os/workflow-plans/{plan_key}/lanes/{lane_key}', { plan_key: key, lane_key: lane }, body)
  const deleteLane = (key: string, lane: string) =>
    planRequest(api, 'delete', '/api/llc/company-os/workflow-plans/{plan_key}/lanes/{lane_key}', { plan_key: key, lane_key: lane })
  const addStep = (key: string, body: Step) =>
    planRequest(api, 'post', '/api/llc/company-os/workflow-plans/{plan_key}/steps', { plan_key: key }, body)
  const patchStep = (key: string, step: string, body: StepPatch) =>
    planRequest(api, 'patch', '/api/llc/company-os/workflow-plans/{plan_key}/steps/{step_key}', { plan_key: key, step_key: step }, body)
  const deleteStep = (key: string, step: string) =>
    planRequest(api, 'delete', '/api/llc/company-os/workflow-plans/{plan_key}/steps/{step_key}', { plan_key: key, step_key: step })
  const addEdge = (key: string, body: Edge) =>
    planRequest(api, 'post', '/api/llc/company-os/workflow-plans/{plan_key}/edges', { plan_key: key }, body)
  const patchEdge = (key: string, from: string, to: string, body: EdgePatch) =>
    planRequest(api, 'patch', '/api/llc/company-os/workflow-plans/{plan_key}/edges/{from_step}/{to_step}', { plan_key: key, from_step: from, to_step: to }, body)
  const deleteEdge = (key: string, from: string, to: string) =>
    planRequest(api, 'delete', '/api/llc/company-os/workflow-plans/{plan_key}/edges/{from_step}/{to_step}', { plan_key: key, from_step: from, to_step: to })
  const patchEdgeCase = (key: string, edgeCase: string, body: EdgeCasePatch) =>
    planRequest(api, 'patch', '/api/llc/company-os/workflow-plans/{plan_key}/edge-cases/{edge_case_key}', { plan_key: key, edge_case_key: edgeCase }, body)
  const deleteEdgeCase = (key: string, edgeCase: string) =>
    planRequest(api, 'delete', '/api/llc/company-os/workflow-plans/{plan_key}/edge-cases/{edge_case_key}', { plan_key: key, edge_case_key: edgeCase })
  const oneNumberCandidates = (key: string, returnKind: ReturnKind) =>
    planRequest(api, 'get', '/api/llc/company-os/workflow-plans/{plan_key}/one-number/candidates', { plan_key: key }, undefined, { return_kind: returnKind })
  const classifySubStep = (key: string, sub: string, classification: Label | null) =>
    planRequest(api, 'patch', '/api/llc/company-os/workflow-plans/{plan_key}/sub-steps/{sub_step_key}', { plan_key: key, sub_step_key: sub }, { classification })
  const acknowledgeByHand = (key: string) =>
    planRequest(api, 'post', '/api/llc/company-os/workflow-plans/{plan_key}/by-hand-acknowledgement', { plan_key: key })
  const previewConversion = (key: string) =>
    planRequest(api, 'post', '/api/llc/company-os/workflow-plans/{plan_key}/convert/preview', { plan_key: key })
  const approve = (key: string) =>
    planRequest(api, 'post', '/api/llc/company-os/workflow-plans/{plan_key}/approve', { plan_key: key })
  const convert = (key: string) =>
    planRequest(api, 'post', '/api/llc/company-os/workflow-plans/{plan_key}/convert', { plan_key: key })
  const retryAiLineProposals = (key: string) =>
    planRequest(api, 'post', '/api/llc/company-os/workflow-plans/{plan_key}/convert/retry-ai-line-proposals', { plan_key: key })

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
    addEdgeCase,
    addLane,
    patchLane,
    deleteLane,
    addStep,
    patchStep,
    deleteStep,
    addEdge,
    patchEdge,
    deleteEdge,
    patchEdgeCase,
    deleteEdgeCase,
    oneNumberCandidates,
    classifySubStep,
    acknowledgeByHand,
    previewConversion,
    approve,
    convert,
    retryAiLineProposals,
  }
}

export type WorkflowPlansApi = ReturnType<typeof useWorkflowPlans>
