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
import { ref } from 'vue'

export type KitDirection = 'ltr' | 'rtl'

function readDocumentDirection(): KitDirection {
  return document.documentElement.dir === 'rtl' ? 'rtl' : 'ltr'
}

/** Mirrors `html[dir]`; a computed that reads it re-runs when the app switches locale. */
const documentDirection = ref<KitDirection>('ltr')
let observing = false

function observeDocumentDirection(): void {
  if (observing || typeof document === 'undefined') return
  observing = true
  documentDirection.value = readDocumentDirection()
  new MutationObserver(() => {
    documentDirection.value = readDocumentDirection()
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['dir'] })
}

export function resolveDirection(dir?: KitDirection): KitDirection {
  if (dir) return dir
  if (typeof document === 'undefined') return 'ltr'
  observeDocumentDirection()
  void documentDirection.value // the dependency a computed re-runs on; the read below is never stale
  return readDocumentDirection()
}
