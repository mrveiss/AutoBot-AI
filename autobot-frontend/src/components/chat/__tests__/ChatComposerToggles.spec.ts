// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatComposerToggles (#18243): the option chips are kit toggle chips with aria-pressed; Overseer and Thinking
// are advanced; the thinking budget steps appear only while thinking is on.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ChatComposerToggles from '../ChatComposerToggles.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const base = { knowledge: true, overseer: false, thinking: false, budget: 5000 }
const render = (props: Record<string, unknown> = {}) =>
  mount(ChatComposerToggles, { props: { ...base, ...props }, attachTo: document.body, global: { plugins: [i18n] } })
const chip = (w: ReturnType<typeof render>, id: string) => w.get(`[data-testid="toggle-${id}"] button`)

describe('ChatComposerToggles', () => {
  it('renders each toggle as a button carrying its state in aria-pressed', () => {
    const w = render({ overseer: true })
    expect(chip(w, 'knowledge').attributes('aria-pressed')).toBe('true')
    expect(chip(w, 'overseer').attributes('aria-pressed')).toBe('true')
    expect(chip(w, 'thinking').attributes('aria-pressed')).toBe('false')
    w.unmount()
  })

  it('labels the chips from the locale: Use Knowledge, Overseer, Thinking', () => {
    const w = render()
    expect(chip(w, 'knowledge').text()).toBe(en.chat.input.useKnowledge)
    expect(chip(w, 'overseer').text()).toBe(en.chat.input.overseerLabel)
    expect(chip(w, 'thinking').text()).toBe(en.chat.composer.thinkingLabel)
    w.unmount()
  })

  it('marks Overseer and Thinking advanced and leaves Use Knowledge visible in Minimal mode', () => {
    const w = render()
    expect(w.get('[data-testid="toggle-overseer"]').classes()).toContain('adv')
    expect(w.get('[data-testid="toggle-thinking"]').classes()).toContain('adv')
    expect(w.get('[data-testid="toggle-knowledge"]').classes()).not.toContain('adv')
    w.unmount()
  })

  it('emits the new knowledge value, and the Overseer and Thinking intents', async () => {
    const w = render()
    await chip(w, 'knowledge').trigger('click')
    expect(w.emitted('update:knowledge')).toEqual([[false]])
    await chip(w, 'overseer').trigger('click')
    expect(w.emitted('toggle-overseer')).toHaveLength(1)
    await chip(w, 'thinking').trigger('click')
    expect(w.emitted('toggle-thinking')).toHaveLength(1)
    w.unmount()
  })

  it('disables only the knowledge chip while the composer is busy, as before', () => {
    const w = render({ disabled: true })
    expect(chip(w, 'knowledge').attributes('disabled')).toBeDefined()
    expect(chip(w, 'overseer').attributes('disabled')).toBeUndefined()
    w.unmount()
  })

  it('shows the budget steps only while thinking is on, with the current step pressed', async () => {
    const off = render()
    expect(off.findAll('[data-testid="budget-step"]')).toHaveLength(0)
    off.unmount()
    const w = render({ thinking: true, budget: 10000 })
    const steps = w.findAll('[data-testid="budget-step"]')
    expect(steps.map((s) => s.text())).toEqual(['1k', '5k', '10k', '32k', 'max'])
    expect(steps.map((s) => s.attributes('aria-pressed'))).toEqual(['false', 'false', 'true', 'false', 'false'])
    await steps[3].trigger('click')
    expect(w.emitted('set-budget')).toEqual([[32000]])
    w.unmount()
  })
})
