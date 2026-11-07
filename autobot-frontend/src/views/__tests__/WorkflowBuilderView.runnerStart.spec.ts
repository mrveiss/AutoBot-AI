// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// A canvas save selects the saved workflow, and Start leads to step 1 waiting (#21043).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, reactive } from 'vue'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import StepApprovalCard from '@/components/workflow/StepApprovalCard.vue'
import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue'

type Wf = { workflow_id: string; started_at?: string; steps: Array<Record<string, unknown>> }
const route = reactive({ params: { section: 'canvas' }, meta: {}, matched: [], query: {} })
const currentWorkflow = ref<Wf | null>(null)
const SAVED: Wf = { workflow_id: 'wf-new', steps: [{ step_id: 's1', description: 'Restart nginx', command: 'x', status: 'pending', risk_tier: 'high' }] }
const STARTED: Wf = { ...SAVED, started_at: 'now', steps: [{ ...SAVED.steps[0], status: 'waiting_approval' }] }
const getWorkflowStatus = vi.fn()
const startWorkflow = vi.fn()
const createWorkflowFromTemplate = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ push: (p: string) => { route.params.section = p.split('/').pop()! }, replace: vi.fn() }),
}))

vi.mock('@/composables/useWorkflowBuilder', async () => {
  const { ref: r, computed: c } = await import('vue')
  return {
    useWorkflowBuilder: () => new Proxy({
      loading: r(false), executingWorkflow: r(false), loadingCapabilities: r(false), error: r(null),
      activeWorkflows: r([]), completedWorkflows: r([]), currentWorkflow,
      stepsAwaitingApproval: c(() => currentWorkflow.value?.steps.filter((s) => s.status === 'waiting_approval') ?? []),
      pendingApproval: r(null), orchestrationStatus: r(null), executionStrategies: r([]), agentCapabilities: r([]),
      agentPerformance: r([]), exampleWorkflows: r([]), workflowNodes: r([]), selectedNodeId: r(null), templates: r([]),
      hasActiveWorkflows: c(() => false), exportCanvasToSteps: () => SAVED.steps,
      approveStep: async () => true, skipStep: async () => true,
      getWorkflowStatus, startWorkflow, createWorkflowFromTemplate,
    } as Record<string, unknown>, {
      get: (t, key: string) => (key in t ? t[key] : vi.fn().mockResolvedValue(undefined)),
    }),
  }
})
vi.mock('@/composables/useWorkflowTemplates', () => ({ useWorkflowTemplates: () => ({ fetchTemplateDetail: vi.fn() }) }))
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast: vi.fn() }) }))

import WorkflowBuilderView from '../WorkflowBuilderView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const stubs = Object.fromEntries(['WorkflowTemplateGallery', 'WorkflowNotificationConfig', 'WorkflowHistory',
  'OrchestrationVisualizer', 'WorkflowLiveDashboard', 'GUIAutomationControls', 'ScreenCaptureViewer', 'VideoProcessor',
  'MediaGallery', 'PlanBeforeBuildingAction', 'RouterLink', 'WorkflowCanvas'].map((k) => [k, true]))

describe('WorkflowBuilderView runner start (#21043)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    route.params.section = 'canvas'
    currentWorkflow.value = null
    createWorkflowFromTemplate.mockResolvedValue('wf-new')
    getWorkflowStatus.mockImplementation(async () => { currentWorkflow.value = SAVED; return SAVED })
    startWorkflow.mockImplementation(async () => { currentWorkflow.value = STARTED; return true })
  })

  it('selects the saved workflow after a canvas save', async () => {
    const w = mount(WorkflowBuilderView, { global: { plugins: [i18n], stubs, mocks: { $route: route } } })
    w.findComponent(WorkflowCanvas).vm.$emit('save-workflow', 'My flow', '')
    await flushPromises()
    expect(getWorkflowStatus).toHaveBeenCalledWith('wf-new')
    expect(route.params.section).toBe('runner')
    expect(currentWorkflow.value).toEqual(SAVED)
  })

  it('Start runs the workflow and step 1 shows its approval card', async () => {
    const w = mount(WorkflowBuilderView, { global: { plugins: [i18n], stubs, mocks: { $route: route } } })
    w.findComponent(WorkflowCanvas).vm.$emit('save-workflow', 'My flow', '')
    await flushPromises()
    expect(w.findAllComponents(StepApprovalCard)).toHaveLength(0)
    await w.findAll('button').find((b) => b.text() === 'Start')!.trigger('click')
    await flushPromises()
    expect(startWorkflow).toHaveBeenCalledWith('wf-new')
    expect(w.findAllComponents(StepApprovalCard)).toHaveLength(1)
    expect(w.text()).toContain('Restart nginx')
  })

  it('a list click selects through getWorkflowStatus', async () => {
    route.params.section = 'runner'
    const w = mount(WorkflowBuilderView, { global: { plugins: [i18n], stubs, mocks: { $route: route } } })
    w.findComponent({ name: 'WorkflowRunner' }).vm.$emit('select-workflow', 'wf-9')
    await flushPromises()
    expect(getWorkflowStatus).toHaveBeenCalledWith('wf-9')
  })
})
