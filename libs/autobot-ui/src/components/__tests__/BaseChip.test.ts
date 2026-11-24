// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseChip behavioural tests (#21995): the toggle chip is a real button whose pressed
// state is `aria-pressed`, controlled by the caller, with no text of its own.
import { describe, it, expect } from 'vitest'
import { h } from 'vue'
import { mount } from '@vue/test-utils'
import chipSource from '../BaseChip.vue?raw'
import BaseChip from '../BaseChip.vue'

describe('BaseChip', () => {
  it('renders a real <button type="button"> with the label slot', () => {
    // fails if the root stops being a native button or the default slot is not projected
    const w = mount(BaseChip, { slots: { default: 'Web' } })
    expect(w.element.tagName).toBe('BUTTON')
    expect(w.attributes('type')).toBe('button')
    expect(w.find('[data-slot="chip-label"]').text()).toBe('Web')
  })

  it('is unpressed by default and exposes aria-pressed="false"', () => {
    // fails if the unpressed state drops the attribute (a toggle must always state its state)
    const w = mount(BaseChip)
    expect(w.attributes('aria-pressed')).toBe('false')
    expect(w.classes()).not.toContain('aui-chip--pressed')
  })

  it('reflects pressed as aria-pressed="true" and the pressed class', () => {
    // fails if the pressed prop is not mirrored to assistive tech
    const w = mount(BaseChip, { props: { pressed: true } })
    expect(w.attributes('aria-pressed')).toBe('true')
    expect(w.classes()).toContain('aui-chip--pressed')
  })

  it('emits update:pressed with the inverted value on click (the native Enter/Space activation)', async () => {
    // Enter and Space activate a native button as a click; jsdom does not synthesise that,
    // so the click is the activation event. Fails if a custom key handler or a non-button root replaces it.
    const w = mount(BaseChip, { props: { pressed: false } })
    await w.trigger('click')
    expect(w.emitted('update:pressed')).toEqual([[true]])
    await w.setProps({ pressed: true })
    await w.trigger('click')
    expect(w.emitted('update:pressed')?.[1]).toEqual([false])
  })

  it('has no key handlers of its own, so Enter/Space cannot fire twice', () => {
    // fails if a @keydown/@keyup toggle is added next to the native activation
    expect(chipSource.split('<style')[0]).not.toMatch(/@key(down|up|press)/)
  })

  it('does not emit while disabled and sets the native disabled attribute', async () => {
    // fails if a disabled chip can still toggle
    const w = mount(BaseChip, { props: { disabled: true } })
    expect(w.attributes('disabled')).toBeDefined()
    await w.trigger('click')
    expect(w.emitted('update:pressed')).toBeUndefined()
  })

  it('passes attributes through to the button', () => {
    // fails if inheritAttrs is disabled or the attrs land on a wrapper
    const w = mount(BaseChip, { attrs: { 'aria-label': 'Web search', 'data-testid': 'c', title: 't' } })
    expect(w.attributes('aria-label')).toBe('Web search')
    expect(w.attributes('data-testid')).toBe('c')
    expect(w.attributes('title')).toBe('t')
  })

  it('renders the icon slot only when given, hidden from assistive tech', () => {
    // fails if an empty icon wrapper is rendered or the icon is announced
    expect(mount(BaseChip).find('[data-slot="chip-icon"]').exists()).toBe(false)
    const w = mount(BaseChip, { slots: { icon: () => h('svg') } })
    expect(w.find('[data-slot="chip-icon"]').attributes('aria-hidden')).toBe('true')
  })

  it('applies the size class', () => {
    // fails if size is not reflected
    expect(mount(BaseChip, { props: { size: 'sm' } }).classes()).toContain('aui-chip--sm')
    expect(mount(BaseChip).classes()).toContain('aui-chip--md')
  })

  it('styles with tokens only and holds no text', () => {
    // fails if a literal colour or a hardcoded label enters the kit component
    const css = chipSource.split('<style scoped>')[1]
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/)
    expect(chipSource.split('<template>')[1].split('</template>')[0]).not.toMatch(/>\s*[A-Za-z]{3,}\s*</)
  })
})
