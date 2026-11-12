// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The workflows of one company (#21240, child of #14409): list, create, and attach to / detach from a role.
 *
 * Reads and creates through the path-scoped `/api/llc/workflows/{company_id}` routes (the company is the
 * path, not a header). The list holds every kind, so only `kind=workflow` rows are kept. Create is
 * admin-gated server-side: a 403 surfaces as a `WorkflowWriteError` with `forbidden` set, never as a
 * silent no-op. A failed load is `state='failed'`, never an empty list.
 *
 * The view is not remounted when the route moves to another company, so the company id is captured
 * at send time and a response for a company no longer shown is discarded.
 */
import { computed, ref, watch } from 'vue'
import { useApiClient } from '@/plugins/api'
import type { components } from '@/types/generated/api'
import { planRequest } from '@/composables/llc/workflowPlanRequest'
import { describeApiError } from '@/composables/llc/apiErrorMessage'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCompanyWorkflows')

export type CompanyWorkflow = components['schemas']['WorkflowResponse']
export type CompanyWorkflowCreate = components['schemas']['WorkflowCreate']
export type WorkflowsState = 'loading' | 'ready' | 'failed'

const WORKFLOW_KIND = 'workflow'
const LIST = '/api/llc/workflows/{company_id}'
const ROLE_WORKFLOWS = '/api/llc/roles/{company_id}/{role_id}/workflows'
const ROLE_WORKFLOW = '/api/llc/roles/{company_id}/{role_id}/workflows/{workflow_id}'

export interface WorkflowOption {
  id: string
  label: string
  disabled: boolean
}

/** A refused company-workflow write; `forbidden` is the admin-gate 403. */
export class WorkflowWriteError extends Error {
  readonly status?: number
  readonly forbidden: boolean
  constructor(message: string, status?: number) {
    super(message)
    this.name = 'WorkflowWriteError'
    this.status = status
    this.forbidden = status === 403
  }
}

/** ApiClient errors read `HTTP <status>: <detail>`; some callers attach `status`. */
function statusOf(err: unknown): number | undefined {
  const direct = (err as { status?: number })?.status
  if (typeof direct === 'number') return direct
  const hit = err instanceof Error ? /^HTTP (\d{3})/.exec(err.message) : null
  return hit ? Number(hit[1]) : undefined
}

export function useCompanyWorkflows(companyId: () => string) {
  const api = useApiClient()
  const workflows = ref<CompanyWorkflow[]>([])
  const state = ref<WorkflowsState>('loading')
  const errorMessage = ref('')
  const pending = ref(false)
  // Bumped on a company change and on every load: only the newest request of the shown company lands.
  let generation = 0
  let loadSeq = 0

  async function load(): Promise<void> {
    const id = companyId()
    if (!id) return
    const mine = generation
    const req = ++loadSeq
    if (workflows.value.length === 0) state.value = 'loading'
    try {
      const rows = await planRequest(api, 'get', LIST, { company_id: id })
      if (mine !== generation || req !== loadSeq) return
      workflows.value = (Array.isArray(rows) ? rows : []).filter((w) => w.kind === WORKFLOW_KIND)
      state.value = 'ready'
    } catch (err: unknown) {
      if (mine !== generation || req !== loadSeq) return
      logger.error('Failed to load workflows', err)
      workflows.value = []
      errorMessage.value = describeApiError(err, '')
      state.value = 'failed'
    }
  }

  /** Run one write for the company shown; a refusal is recorded and rethrown typed. */
  async function write<T>(action: (id: string) => Promise<T>): Promise<T> {
    const id = companyId()
    const mine = generation
    pending.value = true
    errorMessage.value = ''
    try {
      return await action(id)
    } catch (err: unknown) {
      logger.error('Workflow write failed', err)
      const message = describeApiError(err, '')
      if (mine === generation) errorMessage.value = message
      throw new WorkflowWriteError(message, statusOf(err))
    } finally {
      if (mine === generation) pending.value = false
    }
  }

  const create = (body: CompanyWorkflowCreate) =>
    write(async (id) => {
      const made = await planRequest(api, 'post', LIST, { company_id: id }, body)
      if (id === companyId()) await load()
      return made
    })

  const attach = (roleId: string, workflowId: string) =>
    write((id) =>
      planRequest(api, 'post', ROLE_WORKFLOWS, { company_id: id, role_id: roleId }, { workflow_id: workflowId }),
    )

  const detach = (roleId: string, workflowId: string) =>
    write((id) =>
      planRequest(api, 'delete', ROLE_WORKFLOW, { company_id: id, role_id: roleId, workflow_id: workflowId }),
    )

  /** Every kind=workflow row as a picker option; ids already on the role are disabled. */
  const attachable = (attached: readonly string[]): WorkflowOption[] => {
    const on = new Set(attached)
    return workflows.value.map((w) => ({
      id: w.workflow_id,
      label: w.name ?? w.workflow_id,
      disabled: on.has(w.workflow_id),
    }))
  }

  watch(companyId, () => {
    generation++
    workflows.value = []
    errorMessage.value = ''
    pending.value = false
    state.value = 'loading'
    void load()
  })

  const isEmpty = computed(() => state.value === 'ready' && workflows.value.length === 0)

  return { workflows, state, errorMessage, pending, isEmpty, load, create, attach, detach, attachable }
}
