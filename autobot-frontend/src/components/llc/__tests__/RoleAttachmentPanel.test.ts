// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14221: the add/remove control the Roles tab uses four times.
//
// RolesView's tests emit `add`/`remove` ON this component to check the parent's
// handlers, which never runs the component's own logic — the trim, the guards,
// the draft reset. This file drives the real DOM instead, so the contract
// between the two is exercised from both sides rather than assumed at the seam.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'

import RoleAttachmentPanel from '../RoleAttachmentPanel.vue'

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(RoleAttachmentPanel, {
    props: {
      panelKey: 'permissions',
      title: 'Permissions',
      items: ['knowledge.read'],
      addLabel: 'Grant',
      removeLabel: 'Revoke',
      emptyLabel: 'No permissions granted.',
      ...props,
    },
    global: { stubs: { BaseButton: { template: '<button><slot /></button>' } } },
  })
}

describe('RoleAttachmentPanel (#14221)', () => {
  it('renders each item and the count', async () => {
    const wrapper = mountPanel({ items: ['a.read', 'a.write'] })

    expect(wrapper.text()).toContain('a.read')
    expect(wrapper.text()).toContain('a.write')
    expect(wrapper.text()).toContain('2')
  })

  it('shows the empty label instead of a bare heading', async () => {
    const wrapper = mountPanel({ items: [] })

    expect(wrapper.text()).toContain('No permissions granted.')
  })

  it('emits the trimmed value and clears the draft', async () => {
    // Trimming matters: a stray space creates a permission the backend will
    // reject, and leaving the draft behind invites a duplicate submit.
    const wrapper = mountPanel()
    await wrapper.find('input').setValue('  knowledge.write  ')
    await wrapper.find('form').trigger('submit')

    expect(wrapper.emitted('add')).toEqual([['knowledge.write']])
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('')
  })

  it('does not emit for an empty or whitespace-only draft', async () => {
    const wrapper = mountPanel()
    await wrapper.find('form').trigger('submit')
    await wrapper.find('input').setValue('   ')
    await wrapper.find('form').trigger('submit')

    expect(wrapper.emitted('add')).toBeUndefined()
  })

  it('emits nothing while busy, and keeps the draft for a retry', async () => {
    // The real sequence: the user types, submits, the request starts (busy),
    // and they hit Enter again before it returns.
    //
    // Mounting with busy already true would test nothing — `setValue` on a
    // disabled input never updates the model, so `submit()` would return on the
    // empty check and pass even with the guard deleted. Verified by mutation.
    const wrapper = mountPanel()
    await wrapper.find('input').setValue('knowledge.write')

    await wrapper.setProps({ busy: true })
    await wrapper.find('form').trigger('submit')

    expect(wrapper.emitted('add')).toBeUndefined()
    // The draft survives, so a blocked submit does not make the user retype it.
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('knowledge.write')
  })

  it('emits the item to remove when its control is clicked', async () => {
    const wrapper = mountPanel({ items: ['a.read', 'a.write'] })
    await wrapper.findAll('.attachment-remove')[1].trigger('click')

    expect(wrapper.emitted('remove')).toEqual([['a.write']])
  })

  it('disables both controls while busy', async () => {
    const wrapper = mountPanel({ busy: true })

    expect(wrapper.find('input').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.attachment-remove').attributes('disabled')).toBeDefined()
  })

  it('ties the label to its own input via the locale-independent key', async () => {
    // The id must come from panelKey, never the translated title — a non-Latin
    // title used to slug to the empty string and collide across panels.
    const wrapper = mountPanel({ panelKey: 'credentials', title: 'بيانات الاعتماد' })

    expect(wrapper.find('input').attributes('id')).toBe('attachment-credentials')
    expect(wrapper.find('label').attributes('for')).toBe('attachment-credentials')
  })

  it('labels the remove control with the item, not just an icon', async () => {
    // A row of bare × buttons is unusable with a screen reader.
    const wrapper = mountPanel({ items: ['a.read'] })

    expect(wrapper.find('.attachment-remove').attributes('aria-label')).toBe('Revoke: a.read')
  })
})
