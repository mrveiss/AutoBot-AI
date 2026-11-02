// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useUiMode — the Minimal / Full interface mode (#18240). The composable is a
 * module-level singleton, so each test imports a fresh instance.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

const MODE_KEY = 'autobot-ui-mode'
const START_KEY = 'autobot-ui-start'

async function fresh() {
  vi.resetModules()
  return import('../useUiMode')
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-ui')
})

describe('useUiMode state', () => {
  it('defaults to full / last and writes data-ui=full on load', async () => {
    const { useUiMode } = await fresh()
    const { uiMode, uiStart } = useUiMode()
    expect(uiMode.value).toBe('full')
    expect(uiStart.value).toBe('last')
    expect(document.documentElement.getAttribute('data-ui')).toBe('full')
  })

  it('restores a stored mode and start, ignoring unknown values', async () => {
    localStorage.setItem(MODE_KEY, 'minimal')
    localStorage.setItem(START_KEY, 'bogus')
    const { useUiMode } = await fresh()
    const { uiMode, uiStart } = useUiMode()
    expect(uiMode.value).toBe('minimal')
    expect(uiStart.value).toBe('last')
    expect(document.documentElement.getAttribute('data-ui')).toBe('minimal')
  })

  it('toggle flips the mode, sets data-ui and writes through to localStorage', async () => {
    const { useUiMode } = await fresh()
    const ui = useUiMode()
    ui.toggle()
    expect(ui.uiMode.value).toBe('minimal')
    expect(document.documentElement.getAttribute('data-ui')).toBe('minimal')
    expect(localStorage.getItem(MODE_KEY)).toBe('minimal')
    ui.toggle()
    expect(document.documentElement.getAttribute('data-ui')).toBe('full')
    expect(localStorage.getItem(MODE_KEY)).toBe('full')
  })

  it('setStart persists the start preference without changing the mode', async () => {
    const { useUiMode } = await fresh()
    const ui = useUiMode()
    ui.setStart('minimal')
    expect(localStorage.getItem(START_KEY)).toBe('minimal')
    expect(ui.uiMode.value).toBe('full')
  })
})

describe('start-mode resolution at login', () => {
  it('resolveStartMode: last uses the last-used mode, a pinned start wins', async () => {
    const { resolveStartMode } = await fresh()
    expect(resolveStartMode('minimal', 'last')).toBe('minimal')
    expect(resolveStartMode('full', 'last')).toBe('full')
    expect(resolveStartMode('full', 'minimal')).toBe('minimal')
    expect(resolveStartMode('minimal', 'full')).toBe('full')
  })

  it('applyAccount with start=last opens in the account ui_mode', async () => {
    const { useUiMode } = await fresh()
    const ui = useUiMode()
    ui.applyAccount('minimal', 'last')
    expect(ui.uiMode.value).toBe('minimal')
    expect(ui.uiStart.value).toBe('last')
    expect(document.documentElement.getAttribute('data-ui')).toBe('minimal')
  })

  it('applyAccount with a pinned start opens in the start mode', async () => {
    const { useUiMode } = await fresh()
    const ui = useUiMode()
    ui.applyAccount('full', 'minimal')
    expect(ui.uiMode.value).toBe('minimal')
    expect(ui.uiStart.value).toBe('minimal')
  })

  it('applyAccount ignores values it does not know and writes nothing for them', async () => {
    const { useUiMode } = await fresh()
    const ui = useUiMode()
    ui.applyAccount(undefined, 'sideways')
    expect(ui.uiMode.value).toBe('full')
    expect(ui.uiStart.value).toBe('last')
  })
})
