// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useUiMode.ts - Minimal / Full interface mode (#18240, #17856 row 7)
 *
 * The ONE writer of `data-ui` on <html> (guarded by
 * repo_tests/single_attribute_writer_18240_test.py); the pre-mount copy in
 * theme-variant-init.ts is the single sanctioned exception, and mirrors the
 * storage key below. CSS reads the attribute: `html[data-ui="minimal"] .adv`
 * hides advanced-only chrome (assets/css/components.css).
 *
 * State is a module-level singleton, written through to localStorage. The
 * account copy (ui_mode / ui_start) is synced by usePreferences, which watches
 * `uiMode` and `uiStart` exactly as it watches the theme refs.
 */

import { ref, readonly } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAnnounce } from '@autobot/ui'

export type UiMode = 'minimal' | 'full'
export type UiStart = 'last' | UiMode

export const UI_MODE_STORAGE_KEY = 'autobot-ui-mode'
export const UI_START_STORAGE_KEY = 'autobot-ui-start'

const DEFAULT_MODE: UiMode = 'full'
const DEFAULT_START: UiStart = 'last'

const isMode = (v: unknown): v is UiMode => v === 'minimal' || v === 'full'
const isStart = (v: unknown): v is UiStart => v === 'last' || isMode(v)

function readStored<T>(key: string, valid: (v: unknown) => v is T, fallback: T): T {
  try {
    const stored = localStorage.getItem(key)
    return valid(stored) ? stored : fallback
  } catch {
    return fallback
  }
}

function writeStored(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // localStorage may be unavailable (private mode / sandbox)
  }
}

const currentMode = ref<UiMode>(readStored(UI_MODE_STORAGE_KEY, isMode, DEFAULT_MODE))
const currentStart = ref<UiStart>(readStored(UI_START_STORAGE_KEY, isStart, DEFAULT_START))

function applyMode(mode: UiMode): void {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-ui', mode)
}

applyMode(currentMode.value)

/** The mode a session opens in: the last-used mode, or the pinned start mode. */
export function resolveStartMode(mode: UiMode, start: UiStart): UiMode {
  return start === 'last' ? mode : start
}

function setMode(mode: UiMode): void {
  currentMode.value = mode
  writeStored(UI_MODE_STORAGE_KEY, mode)
  applyMode(mode)
}

function setStart(start: UiStart): void {
  currentStart.value = start
  writeStored(UI_START_STORAGE_KEY, start)
}

/**
 * Apply the account copy at login: remember the start preference and open in
 * the mode it resolves to. Unknown values are ignored, never written.
 */
function applyAccount(mode: unknown, start: unknown): void {
  const nextStart = isStart(start) ? start : currentStart.value
  const nextMode = isMode(mode) ? mode : currentMode.value
  setStart(nextStart)
  setMode(resolveStartMode(nextMode, nextStart))
}

export function useUiMode() {
  return {
    uiMode: readonly(currentMode),
    uiStart: readonly(currentStart),
    setMode,
    setStart,
    toggle: () => setMode(currentMode.value === 'minimal' ? 'full' : 'minimal'),
    applyAccount,
  }
}

/**
 * Component-side helper: returns a function that announces a mode change via
 * the kit's one live region. Call from `setup()` (useAnnounce / useI18n bind
 * to the component), never from the singleton above.
 */
export function useUiModeAnnouncer(): (mode: UiMode) => void {
  const { t } = useI18n()
  const { announce } = useAnnounce()
  return (mode) => announce(t(mode === 'minimal' ? 'nav.uiMode.announceMinimal' : 'nav.uiMode.announceFull'))
}
