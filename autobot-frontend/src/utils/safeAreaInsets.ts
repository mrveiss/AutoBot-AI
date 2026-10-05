// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The device's safe-area insets in pixels (#14771), for code that positions
 * `position: fixed` UI by coordinates (a context menu clamped to the viewport).
 *
 * Read from #app's computed padding, which base.css sets to the --safe-* tokens:
 * getComputedStyle resolves env() there to px. Reading the --safe-* custom
 * properties directly would return the unresolved `env(...)` text instead.
 */
export interface SafeAreaInsets {
  top: number
  right: number
  bottom: number
  left: number
}

export function safeAreaInsets(): SafeAreaInsets {
  const app = document.getElementById('app')
  if (!app) return { top: 0, right: 0, bottom: 0, left: 0 }
  const style = getComputedStyle(app)
  const px = (value: string): number => Number.parseFloat(value) || 0
  return {
    top: px(style.paddingTop),
    right: px(style.paddingRight),
    bottom: px(style.paddingBottom),
    left: px(style.paddingLeft),
  }
}
