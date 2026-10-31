// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Slice helper for large Pinia setup stores (#19834).
 *
 * A store's actions live as module-level functions taking the store's context first, so each is
 * short and testable on its own; the `defineStore` setup binds them to one context and returns
 * the result. `bindSlice` is that binding, and keeps every action's remaining parameters and
 * return type.
 */

type Action<C> = (ctx: C, ...args: never[]) => unknown

type Bound<F> = F extends (ctx: never, ...args: infer A) => infer R ? (...args: A) => R : never

export type BoundSlice<C, T extends Record<string, Action<C>>> = { [K in keyof T]: Bound<T[K]> }

export function bindSlice<C, T extends Record<string, Action<C>>>(ctx: C, actions: T): BoundSlice<C, T> {
  const bound: Record<string, unknown> = {}
  for (const [name, action] of Object.entries(actions)) {
    bound[name] = (...args: never[]) => action(ctx, ...args)
  }
  return bound as BoundSlice<C, T>
}
