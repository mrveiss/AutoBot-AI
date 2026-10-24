// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useDocumentDirection — the reading direction a kit primitive should use (#14779).
 *
 * Reka UI reads direction from its ConfigProvider and otherwise assumes ltr. Both apps set
 * `dir` on <html> when the locale changes (ar / fa / he / ur are rtl; see each app's
 * i18n/index.ts), so a primitive without an explicit `dir` follows the document, and arrow
 * keys in tabs and menus move the right way in RTL. One observer serves every primitive and
 * tracks a locale switch without a reload.
 */
import { computed, ref, type Ref } from 'vue'

export type Direction = 'ltr' | 'rtl'

const documentDir = ref<Direction>('ltr')
let observing = false

function readDocumentDir(): Direction {
  return document.documentElement.dir === 'rtl' ? 'rtl' : 'ltr'
}

function observeDocumentDir(): void {
  if (observing || typeof document === 'undefined') return
  observing = true
  documentDir.value = readDocumentDir()
  if (typeof MutationObserver === 'undefined') return
  new MutationObserver(() => {
    documentDir.value = readDocumentDir()
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['dir'] })
}

export function useDocumentDirection(explicit: Ref<Direction | undefined>) {
  observeDocumentDir()
  return computed<Direction>(() => explicit.value ?? documentDir.value)
}
