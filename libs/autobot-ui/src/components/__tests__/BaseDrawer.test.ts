// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseDrawer behaviour (#14780). Teleport is stubbed so the panel renders in place, and
// `attachTo: document.body` keeps focus state live, as in BaseModal's suite.

import { describe, it, expect, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, ref, nextTick } from 'vue'
import BaseDrawer from '../BaseDrawer.vue'

const SLOTS = { default: '<button class="body-btn">Body</button><a href="#" class="body-link">Link</a>' }

function mountDrawer(props: Record<string, unknown> = {}, slots: Record<string, string> = SLOTS) {
  return mount(BaseDrawer, {
    props: { modelValue: true, title: 'Node details', closeLabel: 'Close panel', ...props },
    slots,
    global: { stubs: { Teleport: true } },
    attachTo: document.body,
  })
}

let wrapper: VueWrapper | null = null
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
  document.body.style.overflow = ''
})

describe('BaseDrawer', () => {
  it('renders a labelled modal dialog with the title, subtitle, body and footer', () => {
    wrapper = mountDrawer({}, { ...SLOTS, subtitle: 'node-01', actions: '<button class="act">Done</button>' })
    const panel = wrapper.find('[role="dialog"]')
    expect(panel.attributes('aria-modal')).toBe('true')
    const heading = wrapper.find(`#${panel.attributes('aria-labelledby')}`)
    expect(heading.text()).toBe('Node details')
    expect(wrapper.find('.aui-drawer-subtitle').text()).toBe('node-01')
    expect(wrapper.find('.body-btn').exists()).toBe(true)
    expect(wrapper.find('.aui-drawer-actions .act').exists()).toBe(true)
  })

  it('renders nothing while closed', () => {
    wrapper = mountDrawer({ modelValue: false })
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('takes its width from the prop, a number as px', () => {
    wrapper = mountDrawer({ width: 640 })
    expect(wrapper.find('.aui-drawer').attributes('style')).toContain('width: 640px')
    wrapper.unmount()
    wrapper = mountDrawer({ width: '48rem' })
    expect(wrapper.find('.aui-drawer').attributes('style')).toContain('width: 48rem')
  })

  it('closes on the close button, Escape and a backdrop click', async () => {
    wrapper = mountDrawer()
    await wrapper.find('.aui-drawer-close').trigger('click')
    await wrapper.find('.aui-drawer-overlay').trigger('keydown', { key: 'Escape' })
    await wrapper.find('.aui-drawer-overlay').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(3)
    expect(wrapper.emitted('update:modelValue')).toEqual([[false], [false], [false]])
  })

  it('does not close on a click inside the panel', async () => {
    wrapper = mountDrawer()
    await wrapper.find('.body-btn').trigger('click')
    expect(wrapper.emitted('close')).toBeUndefined()
  })

  it('honours closeOnOverlay and closeOnEsc', async () => {
    wrapper = mountDrawer({ closeOnOverlay: false, closeOnEsc: false })
    await wrapper.find('.aui-drawer-overlay').trigger('click')
    await wrapper.find('.aui-drawer-overlay').trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('close')).toBeUndefined()
    expect(wrapper.find('.aui-drawer-close').exists()).toBe(true)
  })

  it('locked: no backdrop click, no Escape and no close button, whatever the other props say', async () => {
    wrapper = mountDrawer({ locked: true, closeOnOverlay: true, closeOnEsc: true })
    await wrapper.find('.aui-drawer-overlay').trigger('click')
    await wrapper.find('.aui-drawer-overlay').trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.aui-drawer-close').exists()).toBe(false)
    expect(wrapper.emitted('close')).toBeUndefined()
  })

  it('flush drops the body padding class only when asked', () => {
    wrapper = mountDrawer()
    expect(wrapper.find('.aui-drawer-body').classes()).not.toContain('aui-drawer-body--flush')
    wrapper.unmount()
    wrapper = mountDrawer({ flush: true })
    expect(wrapper.find('.aui-drawer-body').classes()).toContain('aui-drawer-body--flush')
  })

  it('labels the close button with the closeLabel prop', () => {
    wrapper = mountDrawer({ closeLabel: 'Schließen' })
    expect(wrapper.find('.aui-drawer-close').attributes('aria-label')).toBe('Schließen')
  })

  it('forwards consumer attributes to the dialog element, not the Teleport root', () => {
    wrapper = mount(BaseDrawer, {
      props: { modelValue: true, title: 'Node details' },
      attrs: { 'data-testid': 'node-drawer', 'aria-describedby': 'node-help', class: 'consumer' },
      global: { stubs: { Teleport: true } },
      attachTo: document.body,
    })
    const panel = wrapper.find('[role="dialog"]')
    expect(panel.attributes('data-testid')).toBe('node-drawer')
    expect(panel.attributes('aria-describedby')).toBe('node-help')
    expect(panel.classes()).toEqual(expect.arrayContaining(['aui-drawer', 'consumer']))
    expect(wrapper.findAll('[data-testid="node-drawer"]')).toHaveLength(1)
  })

  it('locks body scroll while open and releases it when unmounted open', () => {
    wrapper = mountDrawer()
    expect(document.body.style.overflow).toBe('hidden')
    wrapper.unmount()
    wrapper = null
    expect(document.body.style.overflow).toBe('')
  })

  it('returns focus to the trigger when a parent unmounts it while open', async () => {
    // the NPUDetailsPanel shape: a v-if removes the drawer whose modelValue is still true
    const Host = defineComponent({
      components: { BaseDrawer },
      setup: () => ({ shown: ref(false) }),
      template: `<button class="trigger" @click="shown = true">Open</button>
        <BaseDrawer v-if="shown" :model-value="true" title="T" close-label="Close"><button class="b">B</button></BaseDrawer>`,
    })
    wrapper = mount(Host, { global: { stubs: { Teleport: true } }, attachTo: document.body })
    const trigger = wrapper.find('.trigger').element as HTMLElement
    trigger.focus()
    await wrapper.find('.trigger').trigger('click')
    await flushPromises()
    ;(wrapper.find('.b').element as HTMLElement).focus()
    ;(wrapper.vm as unknown as { shown: boolean }).shown = false
    await nextTick()
    expect(document.activeElement).toBe(trigger)
  })

  describe('keyboard', () => {
    it('Tab from the last focusable wraps to the first, Shift+Tab from the first wraps to the last', async () => {
      wrapper = mountDrawer()
      await flushPromises()
      const close = wrapper.find('.aui-drawer-close').element as HTMLElement
      const link = wrapper.find('.body-link').element as HTMLElement
      link.focus()
      await wrapper.find('.aui-drawer').trigger('keydown', { key: 'Tab' })
      expect(document.activeElement).toBe(close)
      close.focus()
      await wrapper.find('.aui-drawer').trigger('keydown', { key: 'Tab', shiftKey: true })
      expect(document.activeElement).toBe(link)
    })

    it('returns focus to the trigger when it closes', async () => {
      const Host = defineComponent({
        components: { BaseDrawer },
        setup: () => ({ open: ref(false) }),
        template: `<button class="trigger" @click="open = true">Open</button>
          <BaseDrawer v-model="open" title="T" close-label="Close"><button class="b">B</button></BaseDrawer>`,
      })
      wrapper = mount(Host, { global: { stubs: { Teleport: true } }, attachTo: document.body })
      const trigger = wrapper.find('.trigger').element as HTMLElement
      trigger.focus()
      await wrapper.find('.trigger').trigger('click')
      await flushPromises()
      await wrapper.find('.aui-drawer-close').trigger('click')
      await nextTick()
      await flushPromises()
      expect(document.activeElement).toBe(trigger)
    })
  })
})
