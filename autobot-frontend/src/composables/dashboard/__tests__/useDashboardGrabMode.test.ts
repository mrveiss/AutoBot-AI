// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** Keyboard grab mode: the owner's ruling on #18242, key by key. */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import type { DashboardWidget } from '../dashboardLayoutModel'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string, p: Record<string, unknown>) => `${key}:${p.name}@${p.position}` }),
}))

const { useDashboardGrabMode } = await import('../useDashboardGrabMode')

const w = (id: string, span: DashboardWidget['span'] = 6): DashboardWidget => ({
  id, type: 'system', title: id, span, height: 320, props: {},
})
const key = (k: string, shiftKey = false) => ({ key: k, shiftKey }) as KeyboardEvent

function setup() {
  const widgets = ref([w('a'), w('b'), w('c')])
  return { widgets, ...useDashboardGrabMode(widgets) }
}

describe('useDashboardGrabMode', () => {
  it('ignores arrows until a widget is grabbed', () => {
    const { widgets, onKeydown } = setup()
    expect(onKeydown('a', key('ArrowRight'))).toBe(false)
    expect(widgets.value.map((x) => x.id)).toEqual(['a', 'b', 'c'])
  })

  it('Space grabs, ArrowRight moves one slot, Enter drops, each announced', () => {
    const { widgets, onKeydown, grabbedId, announcement } = setup()
    onKeydown('a', key(' '))
    expect(grabbedId.value).toBe('a')
    expect(announcement.value).toBe('dashboardGrid.announce.grabbed:a@1')
    onKeydown('a', key('ArrowRight'))
    expect(widgets.value.map((x) => x.id)).toEqual(['b', 'a', 'c'])
    expect(announcement.value).toBe('dashboardGrid.announce.moved:a@2')
    onKeydown('a', key('Enter'))
    expect(grabbedId.value).toBeNull()
    expect(announcement.value).toBe('dashboardGrid.announce.dropped:a@2')
  })

  it('Escape restores the position and size it had before the grab', () => {
    const { widgets, onKeydown, grabbedId } = setup()
    onKeydown('a', key(' '))
    onKeydown('a', key('ArrowRight'))
    onKeydown('a', key('ArrowRight', true))
    onKeydown('a', key('Escape'))
    expect(grabbedId.value).toBeNull()
    expect(widgets.value.map((x) => `${x.id}:${x.span}`)).toEqual(['a:6', 'b:6', 'c:6'])
  })

  it('Shift+Left/Right steps the span; Shift+Up/Down steps the height', () => {
    const { widgets, onKeydown } = setup()
    onKeydown('b', key(' '))
    onKeydown('b', key('ArrowRight', true))
    expect(widgets.value[1].span).toBe(8)
    onKeydown('b', key('ArrowDown', true))
    expect(widgets.value[1].height).toBe(400)
    onKeydown('b', key('ArrowUp', true))
    onKeydown('b', key('ArrowUp', true))
    expect(widgets.value[1].height).toBe(240)
  })

  it.each([
    [8, ['b', 'a', 'c', 'd']],
    [4, ['b', 'c', 'd', 'a']],
  ] as const)('ArrowDown on span %i moves by the whole widgets that fit in a row', (span, order) => {
    // fails if span 8 (1.5 per row) rounds up to a 2-slot step and skips a slot
    const widgets = ref([w('a', span), w('b', span), w('c', span), w('d', span)])
    const { onKeydown } = useDashboardGrabMode(widgets)
    onKeydown('a', key(' '))
    onKeydown('a', key('ArrowDown'))
    expect(widgets.value.map((x) => x.id)).toEqual(order)
  })

  it('a key on a widget that is not the grabbed one does nothing', () => {
    const { widgets, onKeydown } = setup()
    onKeydown('a', key(' '))
    expect(onKeydown('c', key('ArrowLeft'))).toBe(false)
    expect(widgets.value.map((x) => x.id)).toEqual(['a', 'b', 'c'])
  })
})
