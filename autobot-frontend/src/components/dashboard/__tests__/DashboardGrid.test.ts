// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** DashboardGrid's keyboard grab mode is exposed to assistive tech (#18896 review). */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import type { DashboardWidget } from '@/composables/dashboard/dashboardLayoutModel'

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))

const { default: DashboardGrid } = await import('../DashboardGrid.vue')

const w = (id: string): DashboardWidget => ({ id, type: 'system', title: id, span: 6, height: 320, props: {} })

function mountGrid() {
  const wrapper = mount(DashboardGrid, {
    attachTo: document.body,
    props: {
      widgets: [w('a'), w('b')],
      editing: true,
      'onUpdate:widgets': (next: DashboardWidget[]) => wrapper.setProps({ widgets: next }),
    },
  })
  return wrapper
}
const handle = (wrapper: ReturnType<typeof mountGrid>, id: string) => wrapper.get(`[data-grab-handle="${id}"]`)

describe('DashboardGrid grab mode', () => {
  it('exposes the grab state through aria-pressed on the handle', async () => {
    const wrapper = mountGrid()
    expect(handle(wrapper, 'a').attributes('aria-pressed')).toBe('false')
    await handle(wrapper, 'a').trigger('keydown', { key: ' ' })
    expect(handle(wrapper, 'a').attributes('aria-pressed')).toBe('true')
    wrapper.unmount()
  })

  it('keeps focus on the moved widget handle after a keyboard move', async () => {
    const wrapper = mountGrid()
    ;(handle(wrapper, 'a').element as HTMLElement).focus()
    await handle(wrapper, 'a').trigger('keydown', { key: ' ' })
    await handle(wrapper, 'a').trigger('keydown', { key: 'ArrowRight' })
    await nextTick()
    await nextTick()
    expect(wrapper.emitted('update:widgets')?.at(-1)?.[0].map((x: DashboardWidget) => x.id)).toEqual(['b', 'a'])
    expect(document.activeElement).toBe(handle(wrapper, 'a').element)
    wrapper.unmount()
  })

  it('leaving the handle while grabbed cancels the grab and restores the order', async () => {
    const wrapper = mountGrid()
    await handle(wrapper, 'a').trigger('keydown', { key: ' ' })
    await handle(wrapper, 'a').trigger('keydown', { key: 'ArrowRight' })
    await nextTick()
    await handle(wrapper, 'a').trigger('blur')
    expect(handle(wrapper, 'a').attributes('aria-pressed')).toBe('false')
    expect(wrapper.emitted('update:widgets')?.at(-1)?.[0].map((x: DashboardWidget) => x.id)).toEqual(['a', 'b'])
    wrapper.unmount()
  })

  it('leaving edit mode mid-grab puts the widget back and clears the grab', async () => {
    // fails if the grab outline and moved order outlive edit mode
    const wrapper = mountGrid()
    await handle(wrapper, 'a').trigger('keydown', { key: ' ' })
    await handle(wrapper, 'a').trigger('keydown', { key: 'ArrowRight' })
    await nextTick()
    await wrapper.setProps({ editing: false })
    expect(wrapper.emitted('update:widgets')?.at(-1)?.[0].map((x: DashboardWidget) => x.id)).toEqual(['a', 'b'])
    expect(wrapper.find('.outline-2').exists()).toBe(false)
    wrapper.unmount()
  })

  it('has no handles outside edit mode', () => {
    const wrapper = mount(DashboardGrid, { props: { widgets: [w('a')], editing: false } })
    expect(wrapper.find('[data-grab-handle]').exists()).toBe(false)
  })
})
