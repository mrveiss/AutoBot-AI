// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #15945: the CEO designation card. The three states the backend keeps apart (none, holder gone,
// live), the load failure, the designate action and the server's refusal reason.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { HttpError } from '@autobot/ui'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const put = vi.fn()
const del = vi.fn()

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, put, delete: del }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
// The kit's select menu is built on reka-ui, whose popper does not run in jsdom. A minimal
// stand-in keeps the kit component real and makes its options clickable.
vi.mock('reka-ui', async () => {
  const { defineComponent, h, inject, provide } = await import('vue')
  const passthrough = (name: string) =>
    defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  const SelectRoot = defineComponent({
    name: 'SelectRoot',
    props: { modelValue: { type: String, default: '' } },
    emits: ['update:modelValue'],
    setup(_, { slots, emit }) {
      provide('pick', (v: string) => emit('update:modelValue', v))
      return () => h('div', slots.default?.())
    },
  })
  const SelectItem = defineComponent({
    name: 'SelectItem',
    props: { value: { type: String, required: true } },
    setup(props, { slots }) {
      const pick = inject<(v: string) => void>('pick')!
      return () => h('button', { type: 'button', 'data-option': props.value, onClick: () => pick(props.value) }, slots.default?.())
    },
  })
  const SelectTrigger = defineComponent({
    name: 'SelectTrigger',
    setup: (_, { slots, attrs }) => () => h('button', { type: 'button', 'data-trigger': '', ...attrs }, slots.default?.()),
  })
  const names = [
    'SelectContent', 'SelectItemText', 'SelectPortal', 'SelectValue', 'SelectViewport',
    'PopoverContent', 'PopoverPortal', 'PopoverRoot', 'PopoverTrigger',
    'TabsContent', 'TabsList', 'TabsRoot', 'TabsTrigger',
    'AccordionContent', 'AccordionHeader', 'AccordionItem', 'AccordionRoot', 'AccordionTrigger',
    'DropdownMenuContent', 'DropdownMenuItem', 'DropdownMenuPortal', 'DropdownMenuRoot', 'DropdownMenuSeparator', 'DropdownMenuTrigger',
  ]
  return Object.fromEntries([['SelectRoot', SelectRoot], ['SelectItem', SelectItem], ['SelectTrigger', SelectTrigger], ...names.map((n) => [n, passthrough(n)])])
})

import CompanyCeoCard from '../CompanyCeoCard.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const AGENT = '11111111-1111-4111-8111-111111111111'
const AGENT_B = '22222222-2222-4222-8222-222222222222'
const USER = 'user-ada'

const none = { company_id: 'c1', holder_exists: false }
const live = { company_id: 'c1', holder_type: 'agent', holder_id: AGENT, holder_exists: true }
const gone = { company_id: 'c1', holder_type: 'agent', holder_id: AGENT, holder_exists: false }

function serve(designation: unknown, members: unknown[] = [{ user_id: USER, display_name: 'Ada', role: 'owner' }]) {
  get.mockImplementation((url: string) => {
    if (url.endsWith('/ceo')) return designation instanceof Error ? Promise.reject(designation) : Promise.resolve(designation)
    if (url.endsWith('/org-chart')) {
      return Promise.resolve({
        nodes: [
          { node_id: AGENT, name: 'Planner', is_human: false },
          { node_id: AGENT_B, name: 'Planner', is_human: false },
        ],
      })
    }
    return Promise.resolve(members)
  })
}

async function mountCard() {
  const wrapper = mount(CompanyCeoCard, { props: { companyId: 'c1' }, global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('CompanyCeoCard (#15945)', () => {
  beforeEach(() => {
    get.mockReset()
    put.mockReset()
    del.mockReset()
  })

  it('shows loading until the designation answers', async () => {
    get.mockImplementation(() => new Promise(() => {}))
    const wrapper = mount(CompanyCeoCard, { props: { companyId: 'c1' }, global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.find('[data-testid="ceo-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ceo-none"]').exists()).toBe(false)
  })

  it('says so when the designation could not be read, and retries', async () => {
    serve(new HttpError(500, 'boom'))
    const wrapper = await mountCard()
    expect(wrapper.find('[data-testid="ceo-failed"]').exists()).toBe(true)
    // A failed read is not "no CEO".
    expect(wrapper.find('[data-testid="ceo-none"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="ceo-clear"]').attributes('disabled')).toBeDefined()

    serve(none)
    await wrapper.find('[data-testid="ceo-failed"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ceo-none"]').exists()).toBe(true)
  })

  it('shows no designation as its own state', async () => {
    serve(none)
    const wrapper = await mountCard()
    expect(wrapper.find('[data-testid="ceo-none"]').text()).toContain('No CEO designated')
    expect(wrapper.find('[data-testid="ceo-gone"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="ceo-clear"]').attributes('disabled')).toBeDefined()
  })

  it('shows a holder that no longer exists as a different state from no designation', async () => {
    serve(gone)
    const wrapper = await mountCard()
    const box = wrapper.find('[data-testid="ceo-gone"]')
    expect(box.text()).toContain('The CEO no longer exists')
    expect(box.text()).toContain(AGENT)
    expect(wrapper.find('[data-testid="ceo-none"]').exists()).toBe(false)
    // Clearing a dangling designation is exactly what the person needs.
    expect(wrapper.find('[data-testid="ceo-clear"]').attributes('disabled')).toBeUndefined()
  })

  it('shows a live holder by name, with the id second', async () => {
    serve(live)
    const wrapper = await mountCard()
    expect(wrapper.find('[data-testid="ceo-name"]').text()).toBe('Planner')
    expect(wrapper.find('[data-testid="ceo-live"]').text()).toContain(AGENT)
  })

  it('tells two holders with one name apart in the picker', async () => {
    serve(none)
    const wrapper = await mountCard()
    const labels = wrapper.findAll('[data-option]').map((o) => o.text())
    expect(labels).toContain('Planner (Agent) 11111111')
    expect(labels).toContain('Planner (Agent) 22222222')
    expect(labels).toContain('Ada (Person)')
  })

  it('designates the chosen holder through PUT and reloads', async () => {
    serve(none)
    put.mockResolvedValue({ ...live })
    const wrapper = await mountCard()
    expect(wrapper.find('[data-testid="ceo-set"]').attributes('disabled')).toBeDefined()

    await wrapper.find(`[data-option="user:${USER}"]`).trigger('click')
    serve(live)
    await wrapper.find('[data-testid="ceo-set"]').trigger('click')
    await flushPromises()

    expect(put).toHaveBeenCalledWith('/api/llc/companies/c1/ceo', { holder_type: 'user', holder_id: USER })
    expect(wrapper.find('[data-testid="ceo-live"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ceo-notice"]').text()).toContain('Ada (Person)')
  })

  it("shows the server's reason when the designation is refused, and keeps the old one", async () => {
    serve(live)
    const reason = `agent ${AGENT_B} has no company recorded, so it cannot be designated CEO of one.`
    put.mockRejectedValue(HttpError.withDetail(422, 'Unprocessable Entity', reason))
    const wrapper = await mountCard()

    await wrapper.find(`[data-option="agent:${AGENT_B}"]`).trigger('click')
    await wrapper.find('[data-testid="ceo-set"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="ceo-error"]').text()).toContain(reason)
    expect(wrapper.find('[data-testid="ceo-name"]').text()).toBe('Planner')
  })

  it('clears the designation through DELETE', async () => {
    serve(live)
    del.mockResolvedValue({})
    const wrapper = await mountCard()
    serve(none)
    await wrapper.find('[data-testid="ceo-clear"]').trigger('click')
    await flushPromises()

    expect(del).toHaveBeenCalledWith('/api/llc/companies/c1/ceo')
    expect(wrapper.find('[data-testid="ceo-none"]').exists()).toBe(true)
  })

  it('says when the people could not be loaded instead of offering an empty list as the truth', async () => {
    get.mockImplementation((url: string) =>
      url.endsWith('/ceo') ? Promise.resolve(none) : Promise.reject(new HttpError(500, 'boom')),
    )
    const wrapper = await mountCard()
    expect(wrapper.find('[data-testid="ceo-people-failed"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ceo-no-candidates"]').exists()).toBe(false)
  })
})
