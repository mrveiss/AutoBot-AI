// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21241: the workflows panel of the Roles tab. Controls only for a viewer who may manage the company;
// loading, unavailable and nothing-attachable are different states; create-then-attach in one flow.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
const del = vi.fn()

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post, delete: del }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('reka-ui', async () => (await import('@/test/rekaSelectStub')).rekaSelectStub())

import RoleWorkflowsPanel from '../RoleWorkflowsPanel.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

const row = (id: string, name: string | null = null) => ({ workflow_id: id, name, kind: 'workflow' })
const STANDING = (canManage: boolean) => ({ members: [], viewer_grantable_roles: [], viewer_can_manage: canManage })

interface Server {
  workflows: unknown[]
  canManage: boolean
  listFails: boolean
  membersFail: boolean
}
let server: Server

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

beforeEach(() => {
  get.mockReset()
  post.mockReset()
  del.mockReset()
  server = { workflows: [row('wf-a', 'Alpha'), row('wf-b', 'Beta')], canManage: true, listFails: false, membersFail: false }
  get.mockImplementation((url: string) => {
    if (url === '/api/llc/workflows/c1' || url === '/api/llc/workflows/c2') {
      return server.listFails ? Promise.reject(new Error('HTTP 500: boom')) : Promise.resolve(server.workflows)
    }
    if (url.endsWith('/members')) {
      return server.membersFail ? Promise.reject(new Error('HTTP 500: boom')) : Promise.resolve(STANDING(server.canManage))
    }
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
  post.mockImplementation((url: string, body: { workflow_id: string }) => {
    if (url === '/api/llc/workflows/c1') {
      server.workflows = [...server.workflows, row(body.workflow_id)]
      return Promise.resolve(row(body.workflow_id))
    }
    return Promise.resolve(undefined)
  })
  del.mockResolvedValue(undefined)
})

async function mountPanel(attached: string[] = ['wf-a']) {
  const wrapper = mount(RoleWorkflowsPanel, {
    props: { companyId: 'c1', roleId: 'r1', attached, busy: false },
    global: { plugins: [i18n], stubs: { teleport: true } },
  })
  await flushPromises()
  return wrapper
}

type Wrapper = Awaited<ReturnType<typeof mountPanel>>
const optionButtons = (w: Wrapper) => w.findAll('[data-testid="role-workflows-picker"] [data-option]')

async function createFromModal(wrapper: Wrapper, id: string) {
  await wrapper.get('[data-testid="role-workflows-new"]').trigger('click')
  await wrapper.get('[data-testid="workflow-create-id"] input').setValue(id)
  await wrapper.get('[data-testid="workflow-create-form"]').trigger('submit')
  await flushPromises()
}

describe('RoleWorkflowsPanel (#21241)', () => {
  it('offers a picker over the company workflows, with the attached ones disabled', async () => {
    const wrapper = await mountPanel(['wf-a'])

    const options = optionButtons(wrapper)
    expect(options.map((o) => o.attributes('data-option'))).toEqual(['wf-a', 'wf-b'])
    expect(options.map((o) => o.text())).toEqual(['Alpha', 'Beta'])
    expect(options[0].attributes('disabled')).toBeDefined()
    expect(options[1].attributes('disabled')).toBeUndefined()
  })

  it('attaches the picked workflow to the role and announces the change', async () => {
    const wrapper = await mountPanel(['wf-a'])
    await optionButtons(wrapper)[1].trigger('click')
    await wrapper.get('[data-testid="role-workflows-attach"]').trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/api/llc/roles/c1/r1/workflows', { workflow_id: 'wf-b' })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('reports a write in flight to the page as busy, and clears it when the write ends', async () => {
    const gate = deferred<void>()
    post.mockReturnValueOnce(gate.promise)
    const wrapper = await mountPanel(['wf-a'])
    await optionButtons(wrapper)[1].trigger('click')
    await wrapper.get('[data-testid="role-workflows-attach"]').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('busy')).toEqual([[true]])

    gate.resolve()
    await flushPromises()
    expect(wrapper.emitted('busy')).toEqual([[true], [false]])
  })

  it('cannot attach until a workflow is picked', async () => {
    const wrapper = await mountPanel()

    expect(wrapper.get('[data-testid="role-workflows-attach"]').attributes('disabled')).toBeDefined()
  })

  it('shows the refusal of an attach and announces no change', async () => {
    post.mockRejectedValueOnce(new Error("HTTP 403: membership role 'member' may not perform this change"))
    const wrapper = await mountPanel(['wf-a'])
    await optionButtons(wrapper)[1].trigger('click')
    await wrapper.get('[data-testid="role-workflows-attach"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="role-workflows-error"]').text()).toContain('may not perform this change')
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('detaches an attached workflow', async () => {
    const wrapper = await mountPanel(['wf-a'])
    await wrapper.get('[data-testid="role-workflow-detach-wf-a"]').trigger('click')
    await flushPromises()

    expect(del).toHaveBeenCalledWith('/api/llc/roles/c1/r1/workflows/wf-a')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('hides every mutation control from a viewer who may not manage the company', async () => {
    server.canManage = false
    const wrapper = await mountPanel(['wf-a'])

    expect(wrapper.text()).toContain('wf-a')
    expect(wrapper.find('[data-testid="role-workflows-controls"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="role-workflows-new"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="role-workflow-detach-wf-a"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="workflow-create-form"]').exists()).toBe(false)
  })

  it('keeps the controls hidden, and says why, when the viewer standing could not be loaded', async () => {
    server.membersFail = true
    const wrapper = await mountPanel(['wf-a'])

    expect(wrapper.find('[data-testid="role-workflows-controls"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="role-workflows-standing-unavailable"]').text()).toBe(en.llc.workflows.standingUnavailable)
  })

  it('says the workflows are unavailable when the list fails, not that there are none', async () => {
    server.listFails = true
    const wrapper = await mountPanel()

    expect(wrapper.get('[data-testid="role-workflows-unavailable"]').text()).toContain(en.llc.workflows.unavailable)
    expect(wrapper.find('[data-testid="role-workflows-nothing-attachable"]').exists()).toBe(false)

    server.listFails = false
    await wrapper.get('[data-testid="role-workflows-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="role-workflows-unavailable"]').exists()).toBe(false)
    expect(optionButtons(wrapper)).toHaveLength(2)
  })

  it('says there is nothing to attach when the company has no workflows', async () => {
    server.workflows = []
    const wrapper = await mountPanel([])

    expect(wrapper.get('[data-testid="role-workflows-nothing-attachable"]').text()).toBe(en.llc.workflows.nothingAttachable)
    expect(wrapper.find('[data-testid="role-workflows-unavailable"]').exists()).toBe(false)
  })

  it('says every workflow is attached when none is left to pick', async () => {
    const wrapper = await mountPanel(['wf-a', 'wf-b'])

    expect(wrapper.get('[data-testid="role-workflows-nothing-attachable"]').text()).toBe(en.llc.workflows.allAttached)
  })

  it('shows loading while the list is on its way', async () => {
    const gate = deferred<unknown[]>()
    get.mockImplementation((url: string) =>
      url.endsWith('/members') ? Promise.resolve(STANDING(true)) : gate.promise,
    )
    const wrapper = await mountPanel()

    expect(wrapper.find('[data-testid="role-workflows-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="role-workflows-unavailable"]').exists()).toBe(false)
    gate.resolve([])
    await flushPromises()
  })

  it('creates a workflow and attaches it to the role in one flow, without a reload', async () => {
    const wrapper = await mountPanel(['wf-a'])
    await createFromModal(wrapper, 'wf-new')

    expect(post).toHaveBeenCalledWith('/api/llc/workflows/c1', expect.objectContaining({ workflow_id: 'wf-new', kind: 'workflow' }))
    expect(post).toHaveBeenCalledWith('/api/llc/roles/c1/r1/workflows', { workflow_id: 'wf-new' })
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.find('[data-testid="workflow-create-form"]').exists()).toBe(false)
    // The list was reloaded by the create: the new workflow is a picker option.
    expect(optionButtons(wrapper).map((o) => o.attributes('data-option'))).toContain('wf-new')
  })

  it('keeps the created workflow attachable when the attach fails', async () => {
    post.mockImplementation((url: string, body: { workflow_id: string }) => {
      if (url === '/api/llc/workflows/c1') {
        server.workflows = [...server.workflows, row(body.workflow_id)]
        return Promise.resolve(row(body.workflow_id))
      }
      return Promise.reject(new Error('HTTP 500: attach broke'))
    })
    const wrapper = await mountPanel(['wf-a'])
    await createFromModal(wrapper, 'wf-new')

    expect(wrapper.get('[data-testid="workflow-create-error"]').text()).toContain('attach broke')
    expect(wrapper.emitted('changed')).toBeUndefined()
    const option = optionButtons(wrapper).find((o) => o.attributes('data-option') === 'wf-new')
    expect(option).toBeDefined()
    expect(option?.attributes('disabled')).toBeUndefined()
  })

  it('drops the attach of a create-then-attach whose company was switched mid-flight', async () => {
    const gate = deferred<unknown>()
    post.mockImplementation((url: string) => (url === '/api/llc/workflows/c1' ? gate.promise : Promise.resolve(undefined)))
    const wrapper = await mountPanel(['wf-a'])
    await wrapper.get('[data-testid="role-workflows-new"]').trigger('click')
    await wrapper.get('[data-testid="workflow-create-id"] input').setValue('wf-new')
    await wrapper.get('[data-testid="workflow-create-form"]').trigger('submit')
    await flushPromises()

    await wrapper.setProps({ companyId: 'c2', roleId: 'r9' })
    gate.resolve(row('wf-new'))
    await flushPromises()

    expect(post).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(wrapper.find('[data-testid="role-workflows-error"]').exists()).toBe(false)
  })
})
