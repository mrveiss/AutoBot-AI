// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Log Forwarding works against the served shapes, keyed by name (#18734):
 * bare-list destinations, masked credentials never sent back, auto-start read
 * from GET /auto-start.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'
import LogForwardingSettings from '../LogForwardingSettings.vue'

const api = {
  getLogForwardingStatus: vi.fn(),
  getLogForwardingAutoStart: vi.fn(),
  getLogForwardingDestinations: vi.fn(),
  createLogForwardingDestination: vi.fn(),
  updateLogForwardingDestination: vi.fn(),
  deleteLogForwardingDestination: vi.fn(),
  testLogForwardingDestination: vi.fn(),
  testAllLogForwardingDestinations: vi.fn(),
  setLogForwardingAutoStart: vi.fn(),
  startLogForwarding: vi.fn(),
  stopLogForwarding: vi.fn(),
}
vi.mock('@/composables/useAutobotApi', () => ({ useAutobotApi: () => api }))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })
const t = (en as { settings: { admin: Record<string, Record<string, string>> } }).settings.admin.logForwardingSettings

function served(name: string, over: Record<string, unknown> = {}) {
  return {
    name, type: 'webhook', enabled: true, url: `https://${name}.example/logs`,
    api_key_masked: '****abcd', username: null, password_masked: null, index: null, file_path: null,
    min_level: 'Information', batch_size: 10, batch_timeout: 5, retry_count: 3, retry_delay: 1,
    scope: 'global', target_hosts: [], syslog_protocol: 'udp', ssl_verify: true,
    ssl_ca_cert: null, ssl_client_cert: null, ssl_client_key: null,
    healthy: true, last_error: null, sent_count: 0, failed_count: 0, ...over,
  }
}

async function mountPage() {
  // The dialogs are the kit BaseModal, which teleports to body: render it in place (#14777).
  const wrapper = mount(LogForwardingSettings, { global: { plugins: [i18n], stubs: { Teleport: true } } })
  await flushPromises()
  return wrapper
}

function buttonByTitle(wrapper: ReturnType<typeof mount>, title: string, index = 0) {
  return wrapper.findAll(`button[title="${title}"]`)[index]
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset()
  api.getLogForwardingStatus.mockResolvedValue({ running: true, total_destinations: 2 })
  api.getLogForwardingAutoStart.mockResolvedValue({ auto_start: true, message: 'on' })
  api.getLogForwardingDestinations.mockResolvedValue([served('alpha'), served('beta', { type: 'file', url: null, file_path: '/var/log/b.log' })])
})

describe('Log Forwarding served shapes', () => {
  it('renders the bare list keyed by name', async () => {
    const wrapper = await mountPage()
    expect(wrapper.text()).toContain('alpha')
    expect(wrapper.text()).toContain('https://alpha.example/logs')
    expect(wrapper.text()).toContain('/var/log/b.log')
  })

  it('edit PUT omits untouched credentials and never prefills the masked value', async () => {
    api.updateLogForwardingDestination.mockResolvedValue({ message: 'ok', destination: {} })
    const wrapper = await mountPage()
    await buttonByTitle(wrapper, t.edit).trigger('click')
    const key = wrapper.get('[data-test="field-api-key"]')
    expect((key.element as HTMLInputElement).value).toBe('')
    expect(wrapper.text()).toContain(t.leaveBlankToKeep)

    await wrapper.get('[data-test="field-url"]').setValue('https://changed.example/x')
    await wrapper.findAll('button').find((b) => b.text() === t.update)!.trigger('click')
    await flushPromises()
    const [name, body] = api.updateLogForwardingDestination.mock.calls[0]
    expect(name).toBe('alpha')
    expect(body.url).toBe('https://changed.example/x')
    expect('api_key' in body).toBe(false)
    expect('password' in body).toBe(false)
    expect(JSON.stringify(body)).not.toContain('****')
  })

  it('edit PUT includes a newly typed credential', async () => {
    api.updateLogForwardingDestination.mockResolvedValue({ message: 'ok', destination: {} })
    const wrapper = await mountPage()
    await buttonByTitle(wrapper, t.edit).trigger('click')
    await wrapper.get('[data-test="field-api-key"]').setValue('new-secret')
    await wrapper.findAll('button').find((b) => b.text() === t.update)!.trigger('click')
    await flushPromises()
    expect(api.updateLogForwardingDestination.mock.calls[0][1].api_key).toBe('new-secret')
  })

  it('auto-start toggle sends the inverse of the value read from GET /auto-start', async () => {
    api.setLogForwardingAutoStart.mockResolvedValue({ auto_start: false, message: 'off' })
    const wrapper = await mountPage()
    const box = wrapper.get('input[type="checkbox"]')
    expect((box.element as HTMLInputElement).checked).toBe(true)
    await box.trigger('change')
    await flushPromises()
    expect(api.setLogForwardingAutoStart).toHaveBeenCalledWith(false)
    expect((wrapper.get('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(false)
  })

  it('test and delete address the destination by name', async () => {
    api.testLogForwardingDestination.mockResolvedValue({ name: 'beta', healthy: true, last_error: null, message: 'ok' })
    api.deleteLogForwardingDestination.mockResolvedValue({ message: 'deleted' })
    const wrapper = await mountPage()
    await buttonByTitle(wrapper, t.testConnection, 1).trigger('click')
    await flushPromises()
    expect(api.testLogForwardingDestination).toHaveBeenCalledWith('beta')

    await buttonByTitle(wrapper, t.delete, 0).trigger('click')
    await wrapper.findAll('button').find((b) => b.text() === t.delete)!.trigger('click')
    await flushPromises()
    expect(api.deleteLogForwardingDestination).toHaveBeenCalledWith('alpha')
  })

  it('test-all reports the served healthy/total counts', async () => {
    api.testAllLogForwardingDestinations.mockResolvedValue({ results: { alpha: true, beta: false }, total: 2, healthy: 1, unhealthy: 1 })
    const wrapper = await mountPage()
    await wrapper.findAll('button').find((b) => b.text() === t.testAll)!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('1/2 destinations healthy')
  })
})

describe('Log Forwarding edit mode details', () => {
  async function openEdit() {
    api.updateLogForwardingDestination.mockResolvedValue({ message: 'ok', destination: {} })
    const wrapper = await mountPage()
    await buttonByTitle(wrapper, t.edit).trigger('click')
    return wrapper
  }
  async function save(wrapper: ReturnType<typeof mount>) {
    await wrapper.findAll('button').find((b) => b.text() === t.update)!.trigger('click')
    await flushPromises()
    return api.updateLogForwardingDestination.mock.calls[0][1]
  }

  it('type is not editable in edit mode', async () => {
    const wrapper = await openEdit()
    expect(wrapper.findAll('select')[0].attributes('disabled')).toBeDefined()
  })

  it('remove sends an explicit null for that credential', async () => {
    const wrapper = await openEdit()
    await wrapper.get('[data-test="remove-api-key"]').setValue(true)
    const body = await save(wrapper)
    expect(body.api_key).toBeNull()
    expect('password' in body).toBe(false)
  })

  it('remove wins over a value typed before it was ticked: the body carries null (#18797)', async () => {
    const wrapper = await openEdit()
    await wrapper.get('[data-test="field-api-key"]').setValue('typed-then-removed')
    await wrapper.get('[data-test="remove-api-key"]').setValue(true)
    const body = await save(wrapper)
    expect(body.api_key).toBeNull()
  })

  it('untouched omits the credential; a typed value sends the value', async () => {
    const wrapper = await openEdit()
    expect('api_key' in (await save(wrapper))).toBe(false)
    api.updateLogForwardingDestination.mockClear()
    await buttonByTitle(wrapper, t.edit).trigger('click')
    await wrapper.get('[data-test="field-api-key"]').setValue('typed')
    expect((await save(wrapper)).api_key).toBe('typed')
  })
})

describe('Log Forwarding auto-start toggle (#18797 review)', () => {
  const box = (w: Awaited<ReturnType<typeof mountPage>>) => w.find<HTMLInputElement>('input[data-test="auto-start"]')

  it('stays disabled when the auto-start read failed, instead of showing "off"', async () => {
    api.getLogForwardingAutoStart.mockRejectedValue(new Error('503'))
    const w = await mountPage()
    expect(box(w).element.disabled).toBe(true)
    await box(w).trigger('change')
    expect(api.setLogForwardingAutoStart).not.toHaveBeenCalled()
  })

  it('contrast: after a successful read it is enabled and sends the opposite value', async () => {
    api.setLogForwardingAutoStart.mockResolvedValue({ auto_start: false })
    const w = await mountPage()
    expect(box(w).element.disabled).toBe(false)
    await box(w).trigger('change')
    await flushPromises()
    expect(api.setLogForwardingAutoStart).toHaveBeenCalledWith(false)
    expect(box(w).element.checked).toBe(false)
  })

  it('ignores a second change while the first is pending, and shows the confirmed value', async () => {
    let finish: (v: { auto_start: boolean }) => void = () => {}
    api.setLogForwardingAutoStart.mockReturnValue(new Promise((r) => { finish = r }))
    const w = await mountPage()
    await box(w).trigger('change')
    await box(w).trigger('change')
    expect(api.setLogForwardingAutoStart).toHaveBeenCalledTimes(1)
    expect(box(w).element.checked).toBe(true) // unconfirmed: still the stored value
    finish({ auto_start: false })
    await flushPromises()
    expect(box(w).element.checked).toBe(false)
  })

  it('Refresh retries a failed auto-start read and enables the toggle (#18797)', async () => {
    api.getLogForwardingAutoStart.mockRejectedValueOnce(new Error('503'))
    const w = await mountPage()
    expect(box(w).element.disabled).toBe(true)
    await w.get('[data-test="refresh"]').trigger('click')
    await flushPromises()
    expect(api.getLogForwardingAutoStart).toHaveBeenCalledTimes(2)
    expect(box(w).element.disabled).toBe(false)
  })

  it('a failed save leaves the checkbox at the stored value', async () => {
    api.setLogForwardingAutoStart.mockRejectedValue(new Error('500'))
    const w = await mountPage()
    box(w).element.checked = false
    await box(w).trigger('change')
    await flushPromises()
    expect(box(w).element.checked).toBe(true)
  })
})

describe('Log Forwarding test results are shown truthfully (#18797 review)', () => {
  const errorAlert = (w: Awaited<ReturnType<typeof mountPage>>) => w.find('.aui-alert--error')

  it("an unhealthy single test keeps its message: the list refresh after it does not clear it", async () => {
    api.testLogForwardingDestination.mockResolvedValue({ name: 'alpha', healthy: false, last_error: 'refused', message: 'connection refused' })
    const w = await mountPage()
    await buttonByTitle(w, t.testConnection, 0).trigger('click')
    await flushPromises()
    expect(errorAlert(w).exists()).toBe(true)
    expect(errorAlert(w).text()).toContain('connection refused')
  })

  it('test all with a failure is an error, not the success banner', async () => {
    api.testAllLogForwardingDestinations.mockResolvedValue({ results: { alpha: true, beta: false }, total: 2, healthy: 1, unhealthy: 1 })
    const w = await mountPage()
    await w.findAll('button').find((b) => b.text().includes(t.testAll))!.trigger('click')
    await flushPromises()
    expect(errorAlert(w).text()).toContain('1/2')
    expect(w.text()).toContain('1/2 destinations healthy')
  })

  it('contrast: test all with every destination healthy shows no error', async () => {
    api.testAllLogForwardingDestinations.mockResolvedValue({ results: { alpha: true, beta: true }, total: 2, healthy: 2, unhealthy: 0 })
    const w = await mountPage()
    await w.findAll('button').find((b) => b.text().includes(t.testAll))!.trigger('click')
    await flushPromises()
    expect(errorAlert(w).exists()).toBe(false)
    expect(w.text()).toContain('2/2 destinations healthy')
  })
})
