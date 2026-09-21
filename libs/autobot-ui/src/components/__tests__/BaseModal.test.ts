// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseModal behavioral tests (#14786 batch 1) — the highest-risk of the 5
// exported components (70 consumer call sites across both apps). Covers
// BaseModal's OWN contract: props driving classes/attrs, slots rendering,
// v-model + close events firing on the right triggers. It does NOT assert on
// the internals of useFocusTrap / useFocusRestore / useInitialFocus /
// useBodyScrollLock — those composables are out of scope for this batch
// (covered directly in batch 2); they still run as part of mounting
// BaseModal (it calls them unconditionally in <script setup>), and nothing
// they touch (document.activeElement, document.body.style, getComputedStyle,
// querySelectorAll, .focus()) is unavailable under jsdom.
//
// Teleport is stubbed (renders its default slot content in place instead of
// moving it to document.body) — the same pattern already proven in
// autobot-frontend/src/components/ui/__tests__/BaseModal.test.ts, which
// tests this exact component via its @autobot/ui import. That keeps the
// teleported dialog content directly queryable via wrapper.find() instead of
// requiring raw `document.body.querySelector` calls. `attachTo: document.body`
// is still required so focus-related DOM state stays live (document.activeElement
// only updates for elements attached to a real document).
//
// modelValue starts `true` on every mount here (not toggled false→true) so
// Vue's <Transition> never has to run and complete a real enter transition
// under jsdom — Vue skips the enter transition entirely for content already
// present on the very first render (no `appear` prop is set), so the dialog
// is synchronously in the DOM after mount. All the close-trigger tests just
// assert the emit, which `handleClose` fires synchronously regardless of any
// transition/animation state.

import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import BaseModal, { type ModalSize } from '../BaseModal.vue'

const SIZES: ModalSize[] = ['sm', 'md', 'lg']

const DEFAULT_SLOTS = { default: '<button class="body-btn">Body</button>' }

function mountModal(props: Record<string, unknown> = {}, slots: Record<string, string> = DEFAULT_SLOTS) {
  return mount(BaseModal, {
    props: { modelValue: true, title: 'Dialog title', ...props },
    slots,
    global: { stubs: { Teleport: true, Transition: false } },
    attachTo: document.body,
  })
}

describe('BaseModal', () => {
  beforeEach(() => {
    document.body.replaceChildren()
  })

  describe('modelValue gating', () => {
    it('does not render the dialog when modelValue=false', async () => {
      // fails if `v-if="modelValue"` is removed or inverted
      const wrapper = mountModal({ modelValue: false })
      await flushPromises()
      expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
      wrapper.unmount()
    })

    it('renders role="dialog" and aria-modal="true" when modelValue=true', async () => {
      // fails if the static a11y attrs on the dialog element are changed or removed
      const wrapper = mountModal()
      await flushPromises()
      const dialog = wrapper.find('[role="dialog"]')
      expect(dialog.exists()).toBe(true)
      expect(dialog.attributes('aria-modal')).toBe('true')
      wrapper.unmount()
    })
  })

  describe('aria labelling', () => {
    it('wires aria-labelledby/aria-describedby to the actual header/content element ids', async () => {
      // fails if titleId/descriptionId stop being applied to the h3 / content
      // div they claim to label — the attribute could still be "present" and
      // non-empty while pointing at nothing, which is the real a11y break
      const wrapper = mountModal()
      await flushPromises()
      const dialog = wrapper.find('[role="dialog"]')
      const labelledby = dialog.attributes('aria-labelledby')
      const describedby = dialog.attributes('aria-describedby')
      expect(labelledby).toBeTruthy()
      expect(describedby).toBeTruthy()
      expect(wrapper.find('h3').attributes('id')).toBe(labelledby)
      expect(wrapper.find('.aui-dialog-content').attributes('id')).toBe(describedby)
      wrapper.unmount()
    })
  })

  describe('title prop vs #title slot', () => {
    it('renders the title prop in the header when no #title slot is given', async () => {
      // fails if `<slot name="title">{{ title }}</slot>` stops falling back to the prop
      const wrapper = mountModal({ title: 'My Dialog' })
      await flushPromises()
      expect(wrapper.find('h3').text()).toBe('My Dialog')
      wrapper.unmount()
    })

    it('lets the #title slot override the title prop', async () => {
      // fails if the slot fallback is replaced with unconditional prop
      // rendering (the slot would stop taking priority over the prop)
      const wrapper = mountModal({ title: 'Prop title' }, { ...DEFAULT_SLOTS, title: '<em>Slot title</em>' })
      await flushPromises()
      const h3 = wrapper.find('h3')
      expect(h3.text()).toBe('Slot title')
      expect(h3.text()).not.toContain('Prop title')
      wrapper.unmount()
    })
  })

  describe('default and #actions slots', () => {
    it('renders the default slot inside .aui-dialog-content', async () => {
      // fails if the unnamed <slot></slot> is removed from .aui-dialog-content
      const wrapper = mountModal()
      await flushPromises()
      expect(wrapper.find('.aui-dialog-content .body-btn').exists()).toBe(true)
      wrapper.unmount()
    })

    it('omits .aui-dialog-actions when no #actions slot is provided', async () => {
      // fails if `v-if="$slots.actions"` is dropped (an empty footer would
      // always render, wasting layout space for every consumer that has no actions)
      const wrapper = mountModal()
      await flushPromises()
      expect(wrapper.find('.aui-dialog-actions').exists()).toBe(false)
      wrapper.unmount()
    })

    it('renders .aui-dialog-actions with the #actions slot content when provided', async () => {
      // fails if the #actions slot stops being projected into .aui-dialog-actions
      const wrapper = mountModal({}, { ...DEFAULT_SLOTS, actions: '<button class="confirm">OK</button>' })
      await flushPromises()
      const actions = wrapper.find('.aui-dialog-actions')
      expect(actions.exists()).toBe(true)
      expect(actions.find('.confirm').exists()).toBe(true)
      wrapper.unmount()
    })
  })

  describe('showClose / closeLabel', () => {
    it('renders a close button with aria-label="Close" by default', async () => {
      // fails if showClose's withDefaults() default changes from true, or
      // closeLabel's default changes from 'Close'
      const wrapper = mountModal()
      await flushPromises()
      expect(wrapper.find('.aui-dialog-close').attributes('aria-label')).toBe('Close')
      wrapper.unmount()
    })

    it('omits the close button when showClose=false', async () => {
      // fails if `v-if="showClose"` is dropped from the close button
      const wrapper = mountModal({ showClose: false })
      await flushPromises()
      expect(wrapper.find('.aui-dialog-close').exists()).toBe(false)
      wrapper.unmount()
    })

    it('uses the closeLabel prop as the close button aria-label', async () => {
      // fails if `:aria-label="closeLabel"` stops reading the prop
      const wrapper = mountModal({ closeLabel: 'Dismiss dialog' })
      await flushPromises()
      expect(wrapper.find('.aui-dialog-close').attributes('aria-label')).toBe('Dismiss dialog')
      wrapper.unmount()
    })
  })

  describe('size / width', () => {
    it.each(SIZES)('applies the aui-dialog-%s class for size=%s', async (size) => {
      // fails if a ModalSize value stops mapping to its own aui-dialog-{size} class
      const wrapper = mountModal({ size })
      await flushPromises()
      expect(wrapper.find('.aui-dialog').classes()).toContain(`aui-dialog-${size}`)
      wrapper.unmount()
    })

    it('defaults to size=md when no size prop is given', async () => {
      // fails if the `size` prop's withDefaults() default changes from 'md'
      const wrapper = mountModal()
      await flushPromises()
      expect(wrapper.find('.aui-dialog').classes()).toContain('aui-dialog-md')
      wrapper.unmount()
    })

    it('applies a numeric width as an inline pixel max-width, overriding size', async () => {
      // fails if numeric widths stop being suffixed with "px", or dialogStyle
      // stops overriding the size-derived max-width via inline style
      const wrapper = mountModal({ size: 'sm', width: 640 })
      await flushPromises()
      const dialog = wrapper.find('.aui-dialog')
      expect(dialog.classes()).toContain('aui-dialog-sm')
      expect(dialog.attributes('style') || '').toContain('max-width: 640px')
      wrapper.unmount()
    })

    it('passes a string width through unchanged', async () => {
      // fails if string widths are coerced/suffixed instead of passed through as-is
      const wrapper = mountModal({ width: '42rem' })
      await flushPromises()
      expect(wrapper.find('.aui-dialog').attributes('style') || '').toContain('max-width: 42rem')
      wrapper.unmount()
    })

    it('adds no inline max-width when width is absent (size preset governs)', async () => {
      // fails if dialogStyle stops returning undefined for an absent width,
      // e.g. always emitting a max-width style even without the prop
      const wrapper = mountModal({ size: 'lg' })
      await flushPromises()
      const dialog = wrapper.find('.aui-dialog')
      expect(dialog.classes()).toContain('aui-dialog-lg')
      expect(dialog.attributes('style') || '').not.toContain('max-width')
      wrapper.unmount()
    })
  })

  describe('scrollable', () => {
    it('applies aui-dialog-scrollable by default', async () => {
      // fails if the `scrollable` prop's withDefaults() default changes from true
      const wrapper = mountModal()
      await flushPromises()
      expect(wrapper.find('.aui-dialog').classes()).toContain('aui-dialog-scrollable')
      wrapper.unmount()
    })

    it('omits aui-dialog-scrollable when scrollable=false', async () => {
      // fails if the `scrollable` prop stops driving the aui-dialog-scrollable class
      const wrapper = mountModal({ scrollable: false })
      await flushPromises()
      expect(wrapper.find('.aui-dialog').classes()).not.toContain('aui-dialog-scrollable')
      wrapper.unmount()
    })
  })

  describe('close triggers', () => {
    it('emits update:modelValue(false) and close when the close button is clicked', async () => {
      // fails if handleClose stops emitting either event, or the close
      // button's @click handler is detached
      const wrapper = mountModal()
      await flushPromises()
      await wrapper.find('.aui-dialog-close').trigger('click')
      expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
      expect(wrapper.emitted('close')).toHaveLength(1)
      wrapper.unmount()
    })

    it('emits update:modelValue(false) and close on Escape keydown over the overlay', async () => {
      // fails if `@keydown.esc="handleClose"` is removed from the overlay element
      const wrapper = mountModal()
      await flushPromises()
      await wrapper.find('.aui-dialog-overlay').trigger('keydown', { key: 'Escape' })
      expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
      expect(wrapper.emitted('close')).toHaveLength(1)
      wrapper.unmount()
    })

    it('emits update:modelValue(false) and close on overlay click when closeOnOverlay=true (default)', async () => {
      // fails if handleOverlayClick stops calling handleClose when closeOnOverlay is true
      const wrapper = mountModal()
      await flushPromises()
      await wrapper.find('.aui-dialog-overlay').trigger('click')
      expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
      expect(wrapper.emitted('close')).toHaveLength(1)
      wrapper.unmount()
    })

    it('does NOT close on overlay click when closeOnOverlay=false', async () => {
      // fails if handleOverlayClick stops checking props.closeOnOverlay and
      // closes unconditionally regardless of the prop
      const wrapper = mountModal({ closeOnOverlay: false })
      await flushPromises()
      await wrapper.find('.aui-dialog-overlay').trigger('click')
      expect(wrapper.emitted('update:modelValue')).toBeUndefined()
      expect(wrapper.emitted('close')).toBeUndefined()
      wrapper.unmount()
    })

    it('does not close when a click on the inner dialog bubbles toward the overlay', async () => {
      // fails if the `.stop` modifier is removed from the inner dialog's
      // @click.stop, letting any click inside the dialog bubble up and close it
      const wrapper = mountModal()
      await flushPromises()
      await wrapper.find('.aui-dialog').trigger('click')
      expect(wrapper.emitted('update:modelValue')).toBeUndefined()
      expect(wrapper.emitted('close')).toBeUndefined()
      wrapper.unmount()
    })
  })
})
