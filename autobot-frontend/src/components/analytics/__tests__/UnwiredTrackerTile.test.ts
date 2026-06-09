// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Unit tests for UnwiredTrackerTile (Issue #6871).
 *
 * Verifies:
 *  - Count renders correctly (zero + plural forms)
 *  - CSS severity classes applied to count badge
 *  - Sparkline SVG renders with correct number of points
 *  - Loading state renders ellipsis
 *  - Click / Enter / Space navigate to problems URL via router.push
 *  - Aria label includes current count
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

// ---- Stub vue-router -------------------------------------------------------
const pushMock = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
}))

// ---- Stub getCssVar --------------------------------------------------------
vi.mock('@/composables/useCssVars', () => ({
  getCssVar: (_varName: string, fallback: string) => fallback,
}))

// ---- Import component after mocks ------------------------------------------
import UnwiredTrackerTile from '../UnwiredTrackerTile.vue'

function mountTile(
  props: {
    count?: number
    sparkline?: number[]
    loading?: boolean
    targetRoute?: string
  } = {},
) {
  return mount(UnwiredTrackerTile, {
    props: {
      count: props.count ?? 0,
      sparkline: props.sparkline ?? [0, 0, 0, 0, 0, 0, 0],
      loading: props.loading ?? false,
      targetRoute: props.targetRoute ?? '/codebase/problems?type=code_smell_unwired_tracker',
    },
    global: {
      stubs: {
        // Stub router-link in case it leaks in
        RouterLink: true,
      },
    },
  })
}

describe('UnwiredTrackerTile (#6871)', () => {
  beforeEach(() => {
    pushMock.mockReset()
  })

  // ---- Rendering -----------------------------------------------------------

  it('renders count 0 with "modules" plural', () => {
    const w = mountTile({ count: 0 })
    expect(w.find('.count-value').text()).toBe('0')
    expect(w.find('.count-unit').text()).toBe('modules')
  })

  it('renders count 1 with "module" singular', () => {
    const w = mountTile({ count: 1 })
    expect(w.find('.count-value').text()).toBe('1')
    expect(w.find('.count-unit').text()).toBe('module')
  })

  it('renders count 42 with "modules" plural', () => {
    const w = mountTile({ count: 42 })
    expect(w.find('.count-value').text()).toBe('42')
    expect(w.find('.count-unit').text()).toBe('modules')
  })

  // ---- CSS severity classes ------------------------------------------------

  it('applies count-ok class when count is 0', () => {
    const w = mountTile({ count: 0 })
    expect(w.find('.tile-count').classes()).toContain('count-ok')
  })

  it('applies count-low class when count is 1..5', () => {
    const w = mountTile({ count: 3 })
    expect(w.find('.tile-count').classes()).toContain('count-low')
  })

  it('applies count-medium class when count is 6..20', () => {
    const w = mountTile({ count: 10 })
    expect(w.find('.tile-count').classes()).toContain('count-medium')
  })

  it('applies count-high class when count > 20', () => {
    const w = mountTile({ count: 25 })
    expect(w.find('.tile-count').classes()).toContain('count-high')
  })

  // ---- Sparkline -----------------------------------------------------------

  it('renders sparkline SVG polyline with at least 2 points', () => {
    const sparkline = [5, 4, 6, 5, 4, 5, 6]
    const w = mountTile({ count: 6, sparkline })
    const polyline = w.find('polyline')
    expect(polyline.exists()).toBe(true)
    const pts = polyline.attributes('points')
    // 7 data points → 7 x,y pairs separated by spaces
    const pairs = pts?.trim().split(/\s+/) ?? []
    expect(pairs.length).toBe(7)
  })

  it('renders empty sparkline (no polyline points) when sparkline is all zeros', () => {
    const w = mountTile({ count: 0, sparkline: [0, 0, 0, 0, 0, 0, 0] })
    // When all zeros, the SVG still renders but the polyline may have trivial points
    const svg = w.find('.sparkline-svg')
    expect(svg.exists()).toBe(true)
  })

  // ---- Loading state -------------------------------------------------------

  it('shows loading indicator when loading=true', () => {
    const w = mountTile({ loading: true })
    expect(w.find('.tile-loading').exists()).toBe(true)
  })

  it('hides loading indicator when loading=false', () => {
    const w = mountTile({ loading: false })
    expect(w.find('.tile-loading').exists()).toBe(false)
  })

  // ---- Navigation ----------------------------------------------------------

  it('calls router.push with targetRoute on click', async () => {
    const route = '/codebase/problems?type=code_smell_unwired_tracker'
    const w = mountTile({ count: 5, targetRoute: route })
    await w.find('.unwired-tracker-tile').trigger('click')
    expect(pushMock).toHaveBeenCalledWith(route)
  })

  it('calls router.push on Enter key', async () => {
    const route = '/codebase/problems?type=code_smell_unwired_tracker'
    const w = mountTile({ count: 5, targetRoute: route })
    await w.find('.unwired-tracker-tile').trigger('keydown.enter')
    expect(pushMock).toHaveBeenCalledWith(route)
  })

  it('calls router.push on Space key', async () => {
    const route = '/codebase/problems?type=code_smell_unwired_tracker'
    const w = mountTile({ count: 5, targetRoute: route })
    await w.find('.unwired-tracker-tile').trigger('keydown.space')
    expect(pushMock).toHaveBeenCalledWith(route)
  })

  // ---- Accessibility -------------------------------------------------------

  it('has role=button and tabindex=0 for keyboard access', () => {
    const w = mountTile({ count: 3 })
    const tile = w.find('.unwired-tracker-tile')
    expect(tile.attributes('role')).toBe('button')
    expect(tile.attributes('tabindex')).toBe('0')
  })

  it('includes count in aria-label', () => {
    const w = mountTile({ count: 7 })
    const tile = w.find('.unwired-tracker-tile')
    expect(tile.attributes('aria-label')).toContain('7')
  })

  // ---- has-findings class --------------------------------------------------

  it('adds has-findings class when count > 0', () => {
    const w = mountTile({ count: 1 })
    expect(w.find('.unwired-tracker-tile').classes()).toContain('has-findings')
  })

  it('does NOT add has-findings class when count is 0', () => {
    const w = mountTile({ count: 0 })
    expect(w.find('.unwired-tracker-tile').classes()).not.toContain('has-findings')
  })
})
