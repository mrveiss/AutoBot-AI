// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21241: the create-workflow modal. Create then attach in one flow; a failed attach keeps the new
// workflow and retries only the attach; a company switched mid-flight receives nothing.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({}) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import CompanyWorkflowCreateModal from '../CompanyWorkflowCreateModal.vue'
import { WorkflowWriteError } from '@/composables/llc/useCompanyWorkflows'

const create = vi.fn()
const attach = vi.fn()
const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

function mountModal(roleId: string | undefined = 'r1') {
  return mount(CompanyWorkflowCreateModal, {
    props: { modelValue: true, companyId: 'c1', roleId, service: { create, attach } as never },
    global: { plugins: [i18n], stubs: { teleport: true } },
  })
}

type Wrapper = ReturnType<typeof mountModal>

async function fill(wrapper: Wrapper, id: string, name = '') {
  await wrapper.get('[data-testid="workflow-create-id"] input').setValue(id)
  if (name) await wrapper.get('[data-testid="workflow-create-name"] input').setValue(name)
}

// The footer button submits the form by its `form` attribute, and Enter in a field submits the same form.
async function submit(wrapper: Wrapper) {
  await wrapper.get('[data-testid="workflow-create-form"]').trigger('submit')
  await flushPromises()
}

beforeEach(() => {
  create.mockReset()
  attach.mockReset()
  create.mockImplementation((body: { workflow_id: string }) => Promise.resolve({ workflow_id: body.workflow_id }))
  attach.mockResolvedValue(undefined)
})

describe('CompanyWorkflowCreateModal (#21241)', () => {
  it('creates the workflow and attaches it to the role in one flow', async () => {
    const wrapper = mountModal()
    await fill(wrapper, '  wf-new  ', 'Quarterly review')
    await submit(wrapper)

    expect(create).toHaveBeenCalledWith({
      workflow_id: 'wf-new',
      name: 'Quarterly review',
      status: 'planned',
      kind: 'workflow',
    })
    expect(attach).toHaveBeenCalledWith('r1', 'wf-new')
    expect(wrapper.emitted('created')).toEqual([['wf-new', true]])
  })

  it('renders only strings that exist in the English locale', () => {
    const text = mountModal().text()

    for (const key of ['createTitle', 'fieldId', 'idHint', 'fieldName', 'createAndAttach'] as const) {
      expect(en.llc.workflows[key]).toBeTruthy()
      expect(text).toContain(en.llc.workflows[key])
    }
    expect(text).not.toContain('llc.workflows.')
  })

  it('only creates when no role is given, and says so', async () => {
    const wrapper = mountModal(undefined)
    await fill(wrapper, 'wf-new')
    await submit(wrapper)

    expect(create.mock.calls[0][0].name).toBeNull()
    expect(attach).not.toHaveBeenCalled()
    expect(wrapper.emitted('created')).toEqual([['wf-new', false]])
  })

  it('keeps the new workflow when the attach fails, and retries only the attach', async () => {
    attach.mockRejectedValueOnce(new WorkflowWriteError('HTTP 409: already attached', 409))
    const wrapper = mountModal()
    await fill(wrapper, 'wf-new')
    await submit(wrapper)

    const shown = wrapper.get('[data-testid="workflow-create-error"]').text()
    expect(shown).toContain('wf-new')
    expect(shown).toContain('already attached')
    expect(wrapper.emitted('created')).toBeUndefined()
    // The id is locked: the workflow exists and must not be created a second time.
    expect(wrapper.get('[data-testid="workflow-create-id"] input').attributes('disabled')).toBeDefined()

    await submit(wrapper)

    expect(create).toHaveBeenCalledTimes(1)
    expect(attach).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('created')).toEqual([['wf-new', true]])
  })

  it('does not attach when the create is refused, and names the admin gate for a 403', async () => {
    create.mockRejectedValueOnce(new WorkflowWriteError('HTTP 403: nope', 403))
    const wrapper = mountModal()
    await fill(wrapper, 'wf-new')
    await submit(wrapper)

    expect(attach).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="workflow-create-error"]').text()).toBe(en.llc.workflows.createForbidden)
  })

  it('shows the server reason for another refusal', async () => {
    create.mockRejectedValueOnce(new WorkflowWriteError('HTTP 409: workflow exists', 409))
    const wrapper = mountModal()
    await fill(wrapper, 'wf-new')
    await submit(wrapper)

    expect(wrapper.get('[data-testid="workflow-create-error"]').text()).toContain('workflow exists')
  })

  it('submits once through the form its footer submit button is bound to (so Enter in a field submits too)', async () => {
    const wrapper = mountModal()
    await fill(wrapper, 'wf-new')
    const button = wrapper.get('[data-testid="workflow-create-submit"]')
    const form = wrapper.get('[data-testid="workflow-create-form"]')

    expect(button.attributes('type')).toBe('submit')
    expect(button.attributes('form')).toBe(form.attributes('id'))
    // One path only: the form's submit. A click handler besides it would create twice per press.
    await form.trigger('submit')
    await flushPromises()
    expect(create).toHaveBeenCalledTimes(1)
    expect(attach).toHaveBeenCalledTimes(1)
  })

  it('cannot be submitted without an id', async () => {
    const wrapper = mountModal()
    await fill(wrapper, '   ')

    expect(wrapper.get('[data-testid="workflow-create-submit"]').attributes('disabled')).toBeDefined()
    await submit(wrapper)
    expect(create).not.toHaveBeenCalled()
  })

  it('attaches nothing and reports nothing when the company changes while the create is in flight', async () => {
    const gate = deferred<{ workflow_id: string }>()
    create.mockReturnValueOnce(gate.promise)
    const wrapper = mountModal()
    await fill(wrapper, 'wf-new')
    await submit(wrapper)

    await wrapper.setProps({ companyId: 'c2' })
    gate.resolve({ workflow_id: 'wf-new' })
    await flushPromises()

    // The attach would have gone to the company now shown, which never had this workflow.
    expect(attach).not.toHaveBeenCalled()
    expect(wrapper.emitted('created')).toBeUndefined()
    expect(wrapper.find('[data-testid="workflow-create-error"]').exists()).toBe(false)
    expect((wrapper.get('[data-testid="workflow-create-id"] input').element as HTMLInputElement).value).toBe('')
  })

  it('emits nothing when the role changes while the attach is in flight', async () => {
    const gate = deferred<void>()
    attach.mockReturnValueOnce(gate.promise)
    const wrapper = mountModal()
    await fill(wrapper, 'wf-new')
    await submit(wrapper)

    await wrapper.setProps({ roleId: 'r2' })
    gate.resolve()
    await flushPromises()

    expect(wrapper.emitted('created')).toBeUndefined()
  })
})
