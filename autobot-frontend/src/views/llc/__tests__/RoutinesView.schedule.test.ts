// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #18432: RoutinesView uses the shared schedule picker. Existing cron strings
// are read as {cron, UTC}, listed as a derived summary (never cron), saved back
// unchanged, and the server preview being absent (404) never breaks the form.

import { describe, it, expect, beforeAll, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
const patch = vi.fn()

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post, patch, delete: vi.fn() }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import RoutinesView from '../RoutinesView.vue'

const ROUTINE = {
  id: 'r1', company_id: 'c1', name: 'Daily digest', description: null, cron_schedule: '0 9 * * 1-5',
  assignee_agent_id: null, status: 'active', produces: 'new_work_item', work_item_template: null, last_fired_at: null,
}
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function routeGets() {
  get.mockImplementation(async (url: string) => (url.includes('/routines') ? [ROUTINE] : []))
}

async function mountView() {
  const wrapper = mount(RoutinesView, { props: { companyId: 'c1' }, global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('RoutinesView schedule picker (#18432)', () => {
  beforeAll(async () => {
    routeGets()
    await mountView() // warm the cold imports so the first real test is not a timeout
  })

  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    patch.mockReset()
    routeGets()
    post.mockRejectedValue(new Error('HTTP 404: Not Found')) // preview endpoint not deployed
    patch.mockResolvedValue(ROUTINE)
  })

  it('lists the schedule as a summary and never shows cron', async () => {
    const wrapper = await mountView()
    const row = wrapper.find('tbody tr')
    expect(row.text()).toContain('Every weekday at 09:00, UTC')
    expect(row.text()).not.toContain('0 9 * * 1-5')
  })

  it('opens the existing cron in the picker as {cron, UTC} and saves it back unchanged', async () => {
    const wrapper = await mountView()
    const edit = wrapper.findAll('tbody tr button').find((b) => b.text() === 'Edit')!
    await edit.trigger('click')
    await flushPromises()
    expect(wrapper.find('.aui-sched__summary').text()).toContain('Every weekday at 09:00, UTC')
    expect(wrapper.find('.aui-sched__list').exists()).toBe(true) // advisory runs, no server preview
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(patch).toHaveBeenCalledTimes(1)
    const [url, body] = patch.mock.calls[0]
    expect(url).toBe('/api/llc/routines/r1')
    expect(body.cron_schedule).toBe('0 9 * * 1-5')
    expect('schedule_spec' in body).toBe(false) // exactly one field, today's payload
  })

  it('offers only UTC, the zone the routine scheduler evaluates in', async () => {
    const wrapper = await mountView()
    const edit = wrapper.findAll('tbody tr button').find((b) => b.text() === 'Edit')!
    await edit.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('select[id$="-zone"] option').map((o) => o.text())).toEqual(['UTC'])
  })

  it('calls no preview endpoint until the backend serves one (#18432 backend half)', async () => {
    const wrapper = await mountView()
    await wrapper.findAll('tbody tr button').find((b) => b.text() === 'Edit')!.trigger('click')
    await new Promise((r) => setTimeout(r, 400)) // longer than the picker debounce
    await flushPromises()
    expect(post.mock.calls.some(([u]) => String(u).includes('/schedules/'))).toBe(false)
  })

  it('a new routine starts from a default schedule and posts a spec', async () => {
    post.mockResolvedValue(ROUTINE)
    const wrapper = await mountView()
    await wrapper.findAll('button').find((b) => b.text() === 'New Routine')!.trigger('click')
    await flushPromises()
    await wrapper.find('input[type="text"]').setValue('Nightly sweep')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const call = post.mock.calls.find(([u]) => u === '/api/llc/companies/c1/routines')!
    expect(call[1].cron_schedule).toBe('0 9 * * 1-5')
    expect('schedule_spec' in call[1]).toBe(false)
  })

  it('a calendar routine saves schedule_spec only, never cron_schedule', async () => {
    const spec = { kind: 'calendar', timezone: 'UTC', rrule: 'FREQ=MONTHLY;BYMONTHDAY=-1;BYHOUR=9;BYMINUTE=0' }
    get.mockImplementation(async (url: string) =>
      url.includes('/routines') ? [{ ...ROUTINE, cron_schedule: '', schedule_spec: spec }] : [])
    const wrapper = await mountView()
    expect(wrapper.find('tbody tr').text()).toContain('On the last day of every month at 09:00, UTC')
    await wrapper.findAll('tbody tr button').find((b) => b.text() === 'Edit')!.trigger('click')
    await flushPromises()
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const body = patch.mock.calls[0][1]
    expect(body.schedule_spec).toEqual(spec)
    expect('cron_schedule' in body).toBe(false)
  })
})
