// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Unit tests for useTabs composable (#11571).
 *
 * Covers:
 *  - default initial value (first tab)
 *  - opts.initial respected
 *  - invalid opts.initial falls back to first tab
 *  - selectTab updates activeTab
 *  - isActive truth values
 *  - tabAttrs shape (id, role, aria-selected, aria-controls, tabindex)
 *  - panelAttrs shape (id, role, aria-labelledby)
 *  - handleKeydown: ArrowRight wraps forward
 *  - handleKeydown: ArrowLeft wraps backward
 *  - handleKeydown: Home jumps to first
 *  - handleKeydown: End jumps to last
 *  - handleKeydown: unrelated keys are ignored (no state change)
 *  - throws when tabIds is empty
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { useTabs } from '../useTabs'

// nextTick needs to flush properly inside tests
beforeEach(() => {
  vi.clearAllMocks()
})

const TABS = ['alpha', 'beta', 'gamma'] as const
type T = (typeof TABS)[number]

function makeKeyEvent(key: string): KeyboardEvent {
  return { key, preventDefault: vi.fn() } as unknown as KeyboardEvent
}

describe('useTabs — initialization', () => {
  it('defaults to the first tab when no initial is provided', () => {
    const { activeTab } = useTabs(TABS)
    expect(activeTab.value).toBe('alpha')
  })

  it('respects opts.initial when it is a valid tab id', () => {
    const { activeTab } = useTabs(TABS, { initial: 'gamma' })
    expect(activeTab.value).toBe('gamma')
  })

  it('falls back to the first tab when opts.initial is not in tabIds', () => {
    const { activeTab } = useTabs(TABS, { initial: 'nonexistent' as T })
    expect(activeTab.value).toBe('alpha')
  })

  it('throws when tabIds is empty', () => {
    expect(() => useTabs([])).toThrow('useTabs: tabIds must not be empty')
  })

  it('exposes tabIds', () => {
    const { tabIds } = useTabs(TABS)
    expect(tabIds).toEqual(TABS)
  })
})

describe('useTabs — selectTab / isActive', () => {
  it('selectTab changes the active tab', () => {
    const { activeTab, selectTab } = useTabs(TABS)
    selectTab('beta')
    expect(activeTab.value).toBe('beta')
  })

  it('isActive returns true for the active tab', () => {
    const { isActive, selectTab } = useTabs(TABS)
    selectTab('gamma')
    expect(isActive('gamma')).toBe(true)
    expect(isActive('alpha')).toBe(false)
    expect(isActive('beta')).toBe(false)
  })
})

describe('useTabs — tabAttrs shape', () => {
  it('produces correct attrs for the active tab', () => {
    const { tabAttrs } = useTabs(TABS, { initial: 'beta' })
    expect(tabAttrs('beta')).toEqual({
      id: 'tab-beta',
      role: 'tab',
      'aria-selected': true,
      'aria-controls': 'tabpanel-beta',
      tabindex: 0,
    })
  })

  it('produces correct attrs for an inactive tab', () => {
    const { tabAttrs } = useTabs(TABS, { initial: 'beta' })
    expect(tabAttrs('alpha')).toEqual({
      id: 'tab-alpha',
      role: 'tab',
      'aria-selected': false,
      'aria-controls': 'tabpanel-alpha',
      tabindex: -1,
    })
  })
})

describe('useTabs — panelAttrs shape', () => {
  it('produces correct panel attrs', () => {
    const { panelAttrs } = useTabs(TABS)
    expect(panelAttrs('gamma')).toEqual({
      id: 'tabpanel-gamma',
      role: 'tabpanel',
      'aria-labelledby': 'tab-gamma',
    })
  })
})

describe('useTabs — handleKeydown', () => {
  it('ArrowRight moves to the next tab', async () => {
    const { activeTab, handleKeydown } = useTabs(TABS)
    const evt = makeKeyEvent('ArrowRight')
    await handleKeydown(evt)
    await nextTick()
    expect(activeTab.value).toBe('beta')
    expect(evt.preventDefault).toHaveBeenCalled()
  })

  it('ArrowRight wraps from last to first', async () => {
    const { activeTab, selectTab, handleKeydown } = useTabs(TABS)
    selectTab('gamma')
    const evt = makeKeyEvent('ArrowRight')
    await handleKeydown(evt)
    await nextTick()
    expect(activeTab.value).toBe('alpha')
  })

  it('ArrowLeft moves to the previous tab', async () => {
    const { activeTab, selectTab, handleKeydown } = useTabs(TABS)
    selectTab('beta')
    const evt = makeKeyEvent('ArrowLeft')
    await handleKeydown(evt)
    await nextTick()
    expect(activeTab.value).toBe('alpha')
  })

  it('ArrowLeft wraps from first to last', async () => {
    const { activeTab, handleKeydown } = useTabs(TABS)
    // starts on alpha
    const evt = makeKeyEvent('ArrowLeft')
    await handleKeydown(evt)
    await nextTick()
    expect(activeTab.value).toBe('gamma')
  })

  it('Home jumps to the first tab', async () => {
    const { activeTab, selectTab, handleKeydown } = useTabs(TABS)
    selectTab('gamma')
    const evt = makeKeyEvent('Home')
    await handleKeydown(evt)
    await nextTick()
    expect(activeTab.value).toBe('alpha')
  })

  it('End jumps to the last tab', async () => {
    const { activeTab, handleKeydown } = useTabs(TABS)
    // starts on alpha
    const evt = makeKeyEvent('End')
    await handleKeydown(evt)
    await nextTick()
    expect(activeTab.value).toBe('gamma')
  })

  it('unrelated keys do not change active tab', async () => {
    const { activeTab, handleKeydown } = useTabs(TABS)
    const evt = makeKeyEvent('Enter')
    await handleKeydown(evt)
    expect(activeTab.value).toBe('alpha')
    expect(evt.preventDefault).not.toHaveBeenCalled()
  })

  it('calls focus() on the newly selected tab button element', async () => {
    const { handleKeydown, tablistRef, activeTab } = useTabs(TABS)

    // Wire a mock DOM node so querySelector works
    const mockFocus = vi.fn()
    const mockTabBtns = [
      { focus: vi.fn() },
      { focus: mockFocus },
      { focus: vi.fn() },
    ]
    tablistRef.value = {
      querySelectorAll: (_sel: string) => mockTabBtns,
    } as unknown as HTMLElement

    await handleKeydown(makeKeyEvent('ArrowRight'))
    await nextTick()

    expect(activeTab.value).toBe('beta')
    expect(mockTabBtns[1].focus).toHaveBeenCalled()
  })
})
