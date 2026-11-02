// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// The workflow plan approval inside WorkflowBuilderView renders in the shared
// ApprovalEnvelope (#13421) and keeps its approve / reject wiring and per-step risk.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const approvePlan = vi.fn().mockResolvedValue(true)
const rejectPlan = vi.fn().mockResolvedValue(true)
const pendingApproval = ref<unknown>(null)

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { section: 'natural-language' }, meta: {}, matched: [], query: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

vi.mock('@/composables/useWorkflowBuilder', async () => {
  const { ref: r, computed } = await import('vue')
  return {
    useWorkflowBuilder: () => new Proxy({
      loading: r(false),
      executingWorkflow: r(false),
      loadingCapabilities: r(false),
      error: r(null),
      activeWorkflows: r([]),
      completedWorkflows: r([]),
      currentWorkflow: r(null),
      pendingApproval,
      orchestrationStatus: r(null),
      executionStrategies: r([]),
      agentCapabilities: r([]),
      agentPerformance: r([]),
      exampleWorkflows: r([]),
      workflowNodes: r([]),
      selectedNodeId: r(null),
      templates: r([]),
      hasActiveWorkflows: computed(() => false),
      approvePlan,
      rejectPlan,
    } as Record<string, unknown>, {
      // Every loader / action this test does not care about is an inert async no-op.
      get: (target, key: string) => (key in target ? target[key] : vi.fn().mockResolvedValue(undefined)),
    }),
  }
})

vi.mock('@/composables/useWorkflowTemplates', () => ({
  useWorkflowTemplates: () => ({ fetchTemplateDetail: vi.fn() }),
}))

vi.mock('@/composables/useNotificationBus', () => ({
  useNotificationBus: () => ({ showToast: vi.fn() }),
}))

import WorkflowBuilderView from '../WorkflowBuilderView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const PLAN = {
  workflow_id: 'wf-1',
  plan_summary: 'Rotate the logs',
  total_steps: 2,
  estimated_total_duration: 120,
  steps: [
    { step_id: 's1', description: 'List logs', command: 'ls /var/log', risk_tier: 'low' },
    { step_id: 's2', description: 'Delete logs', command: 'rm -rf /var/log/old', risk_tier: 'critical' },
  ],
}

function mountView() {
  return mount(WorkflowBuilderView, {
    global: {
      plugins: [i18n],
      mocks: { $route: { name: 'workflow-builder', params: { section: 'natural-language' }, meta: {} } },
      stubs: {
        WorkflowCanvas: true,
        WorkflowTemplateGallery: true,
        WorkflowRunner: true,
        WorkflowHistory: true,
        WorkflowNotificationConfig: true,
        OrchestrationVisualizer: true,
        WorkflowLiveDashboard: true,
        GUIAutomationControls: true,
        ScreenCaptureViewer: true,
        VideoProcessor: true,
        MediaGallery: true,
        PlanBeforeBuildingAction: true,
        RouterLink: true,
      },
    },
  })
}

describe('WorkflowBuilderView plan approval', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    pendingApproval.value = PLAN
  })

  it('renders the pending plan in the shared envelope with per-step risk', () => {
    const wrapper = mountView()
    const text = wrapper.text()
    expect(text).toContain('Rotate the logs')
    expect(text).toContain('ls /var/log')
    expect(text).toContain('Critical')
    expect(text).toContain('Low')
  })

  it('approves and rejects the plan by workflow id', async () => {
    const wrapper = mountView()
    const buttons = wrapper.findAll('button').filter((b) => /Approve & Run|Approve and Run|Reject/i.test(b.text()))
    expect(buttons.length).toBeGreaterThanOrEqual(2)
    await buttons[0].trigger('click')
    expect(approvePlan).toHaveBeenCalledWith('wf-1')
    await buttons[1].trigger('click')
    expect(rejectPlan).toHaveBeenCalledWith('wf-1', 'User rejected')
  })

  it('renders no approval when nothing is pending', () => {
    pendingApproval.value = null
    const wrapper = mountView()
    expect(wrapper.text()).not.toContain('Rotate the logs')
  })
})
