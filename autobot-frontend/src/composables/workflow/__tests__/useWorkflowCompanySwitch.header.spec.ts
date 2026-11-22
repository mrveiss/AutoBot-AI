// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// After a company switch the builder's lists and the X-Organization-Id of its next request must name
// the same company, and nothing may be sent in the window where they do not (#21520).

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { nextTick, ref } from 'vue'

const { orgId } = vi.hoisted(() => ({ orgId: { value: 'co-1' } }))
vi.mock('@/stores/useUserStore', () => ({ useUserStore: () => ({ logout: vi.fn() }) }))
vi.mock('@/utils/orgContext', () => ({ getSelectedCompanyId: () => orgId.value }))
vi.mock('@/utils/authToken', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/authToken')>()),
  readStoredAuthToken: () => 'live-jwt',
  clearStoredAuth: vi.fn(),
}))

import { ApiClient } from '@/utils/ApiClient'
import { resetCircuitBreakers } from '@/utils/apiCircuitBreaker'
import { companyContextAgrees, useWorkflowCompanySwitch } from '../useWorkflowCompanySwitch'
import { useWorkflowListLoaders } from '../useWorkflowListLoaders'
import { useRunnerSelection } from '../useRunnerSelection'

interface W { workflow_id: string }

/** The server answers each company with its own rows, keyed by the header it received. */
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })

describe('company switch: lists and X-Organization-Id agree (#21520)', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  const sentHeaders = () => fetchMock.mock.calls.map((c) => c[1].headers['X-Organization-Id'])

  beforeEach(() => {
    resetCircuitBreakers()
    orgId.value = 'co-1'
    fetchMock = vi.fn(async (_url: string, init: { headers: Record<string, string> }) =>
      json({ workflows: [{ workflow_id: `wf-of-${init.headers['X-Organization-Id']}` }] }))
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  function setup() {
    const client = new ApiClient()
    const routeCompany = ref('co-1')
    const activeWorkflows = ref<W[]>([])
    const completedWorkflows = ref<W[]>([])
    const read = async () => {
      // ApiClient.get resolves the parsed body, not a Response.
      const data = await client.get<{ workflows: W[] }>('/workflow-automation/active_workflows')
      return { success: true, data }
    }
    const loaders = useWorkflowListLoaders<W>({
      activeWorkflows, completedWorkflows, fetchActive: read, fetchCompleted: read,
      wrap: (fn) => fn(), forgetRemoved: () => {}, restoreWaiting: async () => {},
    })
    useWorkflowCompanySwitch({
      companyId: () => routeCompany.value,
      draft: {
        naturalLanguageInput: ref(''), selectedStrategy: ref(''), workflowPlan: ref(null), pendingApproval: ref(null),
        currentWorkflow: ref(null), workflowNodes: ref([]), selectedNodeId: ref(null),
      },
      reload: async () => (await loaders.loadActive()) && (await loaders.loadCompleted()),
      onDraftDiscarded: vi.fn(),
    })
    const startWorkflow = vi.fn(async () => true)
    const runner = useRunnerSelection({
      t: (k) => k, showToast: vi.fn(), navigateToRunner: vi.fn(), activeWorkflows: ref([]), currentWorkflow: ref(null),
      executingWorkflow: ref(false), startWorkflow, getWorkflowStatus: vi.fn(),
      companyAgrees: () => companyContextAgrees(routeCompany.value),
    })
    return { routeCompany, activeWorkflows, completedWorkflows, runner, startWorkflow }
  }

  it('reloads the lists under the new company and sends that same company on the next request', async () => {
    const { routeCompany, activeWorkflows, completedWorkflows } = setup()
    orgId.value = 'co-2'
    routeCompany.value = 'co-2'
    await vi.waitFor(() => expect(completedWorkflows.value).toEqual([{ workflow_id: 'wf-of-co-2' }]))
    expect(activeWorkflows.value).toEqual([{ workflow_id: 'wf-of-co-2' }])
    expect(new Set(sentHeaders())).toEqual(new Set(['co-2']))
  })

  it('refuses Start while the sidebar has switched but the route (and its lists) have not followed', async () => {
    const { routeCompany, runner, startWorkflow } = setup()
    orgId.value = 'co-2'
    await runner.handleStartWorkflow('wf-1')
    expect(startWorkflow).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
    routeCompany.value = 'co-2'
    await nextTick()
    await runner.handleStartWorkflow('wf-1')
    expect(startWorkflow).toHaveBeenCalledWith('wf-1')
  })
})
