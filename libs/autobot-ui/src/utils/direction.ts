// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Reading direction for the headless-library primitives (#14779).
 *
 * The primitives take an optional `dir` prop. When it is absent they follow the document's
 * direction, which each app sets from the active locale (`ar`, `fa`, `he`, `ur` are `rtl`),
 * so a primitive in an RTL locale moves arrow-key focus the right way round without every
 * call site passing `dir`.
 */
export type KitDirection = 'ltr' | 'rtl'

export function resolveDirection(dir?: KitDirection): KitDirection {
  if (dir) return dir
  if (typeof document === 'undefined') return 'ltr'
  return document.documentElement.dir === 'rtl' ? 'rtl' : 'ltr'
}
