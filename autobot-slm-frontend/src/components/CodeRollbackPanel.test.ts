// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #20214: the operator picks an earlier version from a list of dates and subjects, sees what the
 * rollback will do (or why it is refused), and confirms. The panel hands the job it gets back to
 * the page; it never asks for or shows a commit id.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'
import CodeRollbackPanel from './CodeRollbackPanel.vue'
import en from '@/locales/en.json'

const rawRequest = vi.fn()
vi.mock('@/utils/ApiClient', () => ({ default: { rawRequest: (...args: unknown[]) => rawRequest(...args) } }))

vi.mock('@/composables/useTimezone', () => ({ formatFleetDateTime: (d: string) => `on ${d.slice(0, 10)}` }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))

// @autobot/ui drags in reka-ui, which does not load under vitest here: stand in for the kit components.
vi.mock('@autobot/ui', () => {
  const BaseCard = defineComponent({ props: ['title', 'subtitle'], setup: (_p, { slots }) => () => h('section', slots.default?.()) })
  const BaseAlert = defineComponent({ props: ['message'], setup: (p) => () => h('div', { 'data-test': 'alert' }, p.message) })
  const BaseButton = defineComponent({
    props: ['disabled', 'loading', 'variant'],
    emits: ['click'],
    setup: (p, { slots, emit }) => () => h('button', { disabled: p.disabled, onClick: () => emit('click') }, slots.default?.()),
  })
  const BaseModal = defineComponent({
    props: ['modelValue', 'title'],
    setup: (p, { slots }) => () => (p.modelValue ? h('div', { 'data-test': 'modal' }, [h('h3', p.title), slots.default?.(), slots.actions?.()]) : null),
  })
  const BaseSelectMenu = defineComponent({
    props: ['options', 'modelValue', 'disabled'],
    emits: ['update:modelValue'],
    setup: (p, { emit }) => () =>
      h('select', { disabled: p.disabled, onChange: (e: Event) => emit('update:modelValue', (e.target as HTMLSelectElement).value) },
        (p.options as { value: string; label: string; disabled?: boolean }[]).map((o) => h('option', { value: o.value, disabled: o.disabled }, o.label))),
  })
  return { BaseCard, BaseAlert, BaseButton, BaseModal, BaseSelectMenu }
})

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

const COMMIT_A = '1'.repeat(40)
const COMMIT_B = '2'.repeat(40)
const COMMITS = [
  { commit: COMMIT_A, short: COMMIT_A.slice(0, 12), date: '2026-10-30T10:00:00+00:00', subject: 'Fix the updater', is_deployed: true },
  { commit: COMMIT_B, short: COMMIT_B.slice(0, 12), date: '2026-10-29T10:00:00+00:00', subject: 'Add the maintenance page', is_deployed: false },
]
const CHECK_CLEAR = [{ database: 'SLM', status: 'clear', in_the_way: [], message: 'ok' }]

function response(status: number, body: unknown): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as unknown as Response
}

function route(handlers: Record<string, () => Response>): void {
  rawRequest.mockImplementation(async (url: string, opts?: { method?: string }) => {
    const key = `${opts?.method ?? 'GET'} ${url}`
    const handler = handlers[key]
    if (!handler) throw new Error(`unexpected request ${key}`)
    return handler()
  })
}

async function mountPanel(handlers: Record<string, () => Response>, disabled = false) {
  route({ 'GET /code-sync/rollback/candidates': () => response(200, { branch: 'main', deployed_commit: COMMIT_A, commits: COMMITS }), ...handlers })
  const wrapper = mount(CodeRollbackPanel, { props: { disabled }, global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

async function choose(wrapper: Awaited<ReturnType<typeof mountPanel>>, commit: string) {
  await wrapper.find('select').setValue(commit)
  await wrapper.find('button').trigger('click')
  await flushPromises()
}

describe('CodeRollbackPanel', () => {
  beforeEach(() => {
    rawRequest.mockReset()
  })

  it('lists versions by date and subject, never by id, and will not offer the one already running', async () => {
    const wrapper = await mountPanel({})
    const text = wrapper.findAll('option').map((o) => o.text())
    expect(text[0]).toContain('Fix the updater')
    expect(text[0]).toContain('running now')
    expect(text[1]).toContain('Add the maintenance page')
    expect(wrapper.text()).not.toContain(COMMIT_B)
    expect(wrapper.findAll('option')[0].attributes('disabled')).toBeDefined()
  })

  it('shows what will happen on confirm, then starts the rollback and hands the job to the page', async () => {
    const job = { job_id: 'j1', status: 'pending', stages: [] }
    const wrapper = await mountPanel({
      'GET /code-sync/rollback/preview': () => response(200, { commit: COMMITS[1], allowed: true, refusal: null, checks: CHECK_CLEAR }),
      'POST /code-sync/rollback': () => response(202, job),
    })
    await choose(wrapper, COMMIT_B)
    const modal = wrapper.find('[data-test="modal"]')
    expect(modal.text()).toContain('Roll back to this version?')
    expect(modal.text()).toContain('Add the maintenance page')
    expect(modal.text()).toContain('Never undo a database migration')
    expect(modal.text()).toContain('Checked: two databases')
    expect(modal.text()).toContain('Not checked: SQLite stores, Redis, ChromaDB')
    const confirm = modal.findAll('button').find((b) => b.text() === 'Roll back')!
    await confirm.trigger('click')
    await flushPromises()
    expect(rawRequest).toHaveBeenCalledWith('/code-sync/rollback', { method: 'POST', body: { commit: COMMIT_B } })
    expect(wrapper.emitted('started')?.[0]).toEqual([job])
    expect(wrapper.find('[data-test="modal"]').exists()).toBe(false)
  })

  it('refuses a rollback a migration is in the way of, names the database, and offers no confirm', async () => {
    const wrapper = await mountPanel({
      'GET /code-sync/rollback/preview': () =>
        response(200, {
          commit: COMMITS[1],
          allowed: false,
          refusal: 'The backend database has 1 migration(s) applied that the chosen commit does not have.',
          checks: [{ database: 'backend', status: 'blocked', in_the_way: ['20260901_099'], message: 'backend is ahead' }],
        }),
    })
    await choose(wrapper, COMMIT_B)
    const modal = wrapper.find('[data-test="modal"]')
    expect(modal.text()).toContain('This rollback is not possible')
    expect(modal.text()).toContain('The backend database has 1 migration(s)')
    expect(modal.text()).toContain('20260901_099')
    expect(modal.findAll('button').map((b) => b.text())).not.toContain('Roll back')
    expect(rawRequest).not.toHaveBeenCalledWith('/code-sync/rollback', expect.anything())
  })

  it("shows the server's reason when the start is refused, for example while another update runs", async () => {
    const wrapper = await mountPanel({
      'GET /code-sync/rollback/preview': () => response(200, { commit: COMMITS[1], allowed: true, refusal: null, checks: CHECK_CLEAR }),
      'POST /code-sync/rollback': () => response(409, { detail: 'An update-all job is already running (job_id=x)' }),
    })
    await choose(wrapper, COMMIT_B)
    await wrapper.find('[data-test="modal"]').findAll('button').find((b) => b.text() === 'Roll back')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('An update-all job is already running')
    expect(wrapper.emitted('started')).toBeUndefined()
  })

  it('cannot be used while an update is running', async () => {
    const wrapper = await mountPanel({}, true)
    expect(wrapper.find('select').attributes('disabled')).toBeDefined()
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
  })

  it('shows nothing at all while the server says rollback is not enabled', async () => {
    const wrapper = await mountPanel({
      'GET /code-sync/rollback/candidates': () => response(403, { detail: 'Rollback is not enabled on this SLM' }),
    })
    expect(wrapper.find('select').exists()).toBe(false)
    expect(wrapper.text()).toBe('')
  })
})
