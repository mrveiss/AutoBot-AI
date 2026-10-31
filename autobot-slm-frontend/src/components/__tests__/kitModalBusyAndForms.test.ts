// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #14777 batch 2 (#19002 review): the SLM dialogs moved onto the kit BaseModal keep their
// behaviour. A dialog whose Cancel is disabled while it works is `locked` then, so overlay
// click and Escape close nothing and there is no X; idle, the exits are back (contrast).
// A form dialog's submit button lives in the kit footer, outside its <form>, and still
// submits that form through `form="<id>"`.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import type { Component } from 'vue'
import en from '@/locales/en.json'
import AddNodeModal from '@/components/AddNodeModal.vue'
import DeploymentWizard from '@/components/DeploymentWizard.vue'
import InfrastructureWizard from '@/components/InfrastructureWizard.vue'
import MaintenanceView from '@/views/MaintenanceView.vue'
import RolesView from '@/views/RolesView.vue'
import AlertRulesView from '@/views/performance/AlertRulesView.vue'
import SLODashboard from '@/views/performance/SLODashboard.vue'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ path: '/maintenance', params: {}, query: {} }),
}))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

// The dialogs under test need no data to open: every request answers empty, in the shape its
// endpoint really returns.
const EMPTY: [string, unknown][] = [
  ['/roles/fleet-health', { health: 'healthy', required_down: [], optional_down: [], detail: '' }],
  ['/playbooks', { playbooks: [] }],
  ['/maintenance', { windows: [], total: 0 }],
  ['/nodes', { nodes: [], total: 0 }],
]
function stubFetch() {
  const body = (url: string) => EMPTY.find(([path]) => url.includes(path))?.[1] ?? []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(body(String(url))), { status: 200, headers: { 'content-type': 'application/json' } })))
}

type Vm = Record<string, unknown>

async function mountWith(component: Component, props: Record<string, unknown>, state: Vm): Promise<VueWrapper> {
  const wrapper = mount(component, { props, global: { plugins: [i18n], stubs: { Teleport: true } }, attachTo: document.body })
  await flushPromises()
  Object.assign(wrapper.vm as unknown as Vm, state)
  await flushPromises()
  return wrapper
}

/** Overlay click and Escape, then whether the dialog is still open and shows an X. */
async function tryEveryExit(wrapper: VueWrapper) {
  const overlay = wrapper.find('.aui-dialog-overlay')
  expect(overlay.exists()).toBe(true)
  await overlay.trigger('click')
  await wrapper.find('.aui-dialog-overlay').trigger('keydown', { key: 'Escape' })
  await flushPromises()
  return { open: wrapper.find('.aui-dialog').exists(), hasX: wrapper.find('.aui-dialog-close').exists() }
}

interface LockedCase {
  name: string
  component: Component
  props: Record<string, unknown>
  open: Vm
  busy: Vm
  /** What a closed dialog looks like from outside: an emitted event or a cleared flag. */
  closed: (w: VueWrapper) => boolean
}

const emittedClose = (w: VueWrapper) => (w.emitted('close')?.length ?? 0) > 0

const LOCKED: LockedCase[] = [
  { name: 'AddNodeModal while submitting', component: AddNodeModal, props: { visible: true }, open: {}, busy: { isSubmitting: true }, closed: emittedClose },
  { name: 'DeploymentWizard while deploying', component: DeploymentWizard, props: { visible: true }, open: {}, busy: { isDeploying: true }, closed: emittedClose },
  {
    name: 'InfrastructureWizard while a playbook runs',
    component: InfrastructureWizard,
    props: { visible: true },
    open: {},
    busy: { currentExecution: { status: 'running' } },
    closed: emittedClose,
  },
  {
    name: 'MaintenanceView schedule while saving',
    component: MaintenanceView,
    props: {},
    open: { showScheduleDialog: true },
    busy: { isSubmitting: true },
    closed: (w) => (w.vm as unknown as Vm).showScheduleDialog === false,
  },
  {
    name: 'RolesView migrate while the playbook runs',
    component: RolesView,
    props: {},
    open: { showMigrateDialog: true },
    busy: { migrateLoading: true },
    closed: (w) => (w.vm as unknown as Vm).showMigrateDialog === false,
  },
]

describe('#14777 batch 2 dialogs on the kit BaseModal', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    stubFetch()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  describe.each(LOCKED)('$name', (c) => {
    it('is locked: overlay and Escape close nothing, and there is no X', async () => {
      const w = await mountWith(c.component, c.props, { ...c.open, ...c.busy })
      const { open, hasX } = await tryEveryExit(w)
      expect(open).toBe(true)
      expect(hasX).toBe(false)
      expect(c.closed(w)).toBe(false)
      w.unmount()
    })

    it('contrast: idle, it shows the X and Escape closes it', async () => {
      const w = await mountWith(c.component, c.props, c.open)
      expect(w.find('.aui-dialog-close').exists()).toBe(true)
      await w.find('.aui-dialog-overlay').trigger('keydown', { key: 'Escape' })
      await flushPromises()
      expect(c.closed(w)).toBe(true)
      w.unmount()
    })
  })

  describe.each([
    { name: 'AlertRulesView create', component: AlertRulesView, open: { showCreateModal: true }, formId: 'alert-rule-form' },
    { name: 'SLODashboard create', component: SLODashboard, open: { showCreateModal: true }, formId: 'slo-create-form' },
    { name: 'MaintenanceView schedule', component: MaintenanceView, open: { showScheduleDialog: true }, formId: 'maintenance-window-form' },
  ])('$name', ({ component, open, formId }) => {
    it('submits its form from the footer button through form="<id>"', async () => {
      const w = await mountWith(component, {}, open)
      const form = w.find<HTMLFormElement>(`form#${formId}`)
      const submit = w.find<HTMLButtonElement>(`button[type="submit"][form="${formId}"]`)
      expect(form.exists()).toBe(true)
      expect(submit.exists()).toBe(true)
      // The button sits in the kit footer, outside the form: only the attribute ties them.
      expect(form.element.contains(submit.element)).toBe(false)
      expect(submit.element.form).toBe(form.element)
      const onSubmit = vi.fn((e: Event) => e.preventDefault())
      form.element.addEventListener('submit', onSubmit)
      // Constraint validation is not under test: the empty form would block the submit event.
      form.element.noValidate = true
      submit.element.disabled = false
      submit.element.click()
      expect(onSubmit).toHaveBeenCalledTimes(1)
      w.unmount()
    })
  })
})
