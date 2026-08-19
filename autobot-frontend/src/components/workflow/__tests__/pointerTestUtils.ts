// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * GH#14610: shared helper for dispatching real `PointerEvent`s in tests.
 *
 * `@vue/test-utils`'s `wrapper.trigger('pointerdown', {...})` cannot be used
 * here: after constructing the event (which correctly applies `clientX`,
 * `clientY`, `shiftKey`, `button`, ...), it reassigns every option onto the
 * event a *second* time via `event[key] = options[key]`. That second
 * assignment walks `Object.getPrototypeOf(event)` — `PointerEvent.prototype`
 * — and in this jsdom version `PointerEvent.prototype` does not *own*
 * `clientX`/`clientY`/`shiftKey`/`button`; they are inherited, getter-only,
 * from `MouseEvent.prototype`. The reassignment throws
 * "Cannot set property clientX of #<MouseEvent> which has only a getter".
 * This is exactly the "jsdom does not implement touch/pointer gestures
 * natively" gap: constructing and dispatching the event directly sidesteps
 * `trigger()`'s buggy second pass entirely, and is the same native
 * `PointerEvent` our `@pointerdown`/`@pointermove`/`@pointerup`/
 * `@pointercancel` template bindings listen for.
 */

import { nextTick } from 'vue'

export type PointerEventType = 'pointerdown' | 'pointermove' | 'pointerup' | 'pointercancel'

/**
 * Dispatch a `PointerEvent` on `el` and wait a tick for Vue to react.
 *
 * `pointerId` defaults to `1` — a single simulated pointer is enough for
 * every one-finger/mouse gesture; multi-touch (pinch) tests pass distinct
 * ids explicitly. `pointerType` defaults to `'mouse'`, matching a real
 * browser; touch gestures pass `pointerType: 'touch'` explicitly.
 */
export async function firePointer(
  el: Element,
  type: PointerEventType,
  init: PointerEventInit = {},
): Promise<void> {
  const event = new PointerEvent(type, {
    bubbles: true,
    cancelable: true,
    pointerId: 1,
    pointerType: 'mouse',
    ...init,
  })
  // Mirrors @vue/test-utils' own workaround (vuejs/test-utils#1854): Vue
  // ignores a dispatched event whose timestamp is not after the time its
  // listener was attached, which a manually constructed event does not
  // otherwise carry.
  ;(event as PointerEvent & { _vts?: number })._vts = Date.now() + 1
  el.dispatchEvent(event)
  await nextTick()
}
