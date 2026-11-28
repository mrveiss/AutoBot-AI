// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Shared test environment for the Reka UI wrappers (#14779). jsdom has no layout engine, so
// the collision-aware positioning and the pointer/scroll helpers Reka calls need minimal stubs.
// The stubs are inert: they never change what the keyboard and ARIA tests assert.
import { vi } from 'vitest'

export function installRekaDomStubs(): void {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  vi.stubGlobal('ResizeObserver', ResizeObserverStub)
  const proto = window.HTMLElement.prototype
  proto.scrollIntoView ??= () => {}
  proto.hasPointerCapture ??= () => false
  proto.releasePointerCapture ??= () => {}
  proto.setPointerCapture ??= () => {}
}

/** Dispatch a real KeyboardEvent on an element (Reka listens on the element itself). */
export async function press(
  target: Element | null,
  key: string,
  init: KeyboardEventInit = {},
): Promise<void> {
  if (!target) throw new Error(`press(${key}): no target element`)
  target.dispatchEvent(
    new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init }),
  )
  await new Promise((resolve) => setTimeout(resolve, 0))
}
