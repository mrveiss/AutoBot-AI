// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #14860: frontend mount helpers were constructing a fresh `createI18n`
// instance — carrying the full `en` (and frequently `ar`) message bundle, about
// 400KB each — on EVERY mount. A file that mounts 30 times re-ingested the
// whole message tree 30 times for a plugin that is read-only in the test. That
// cost is what pushed individual specs past the 10s per-test `testTimeout`
// under runner load (#14854, #14842, #14613).
//
// Where a helper builds a *static* instance the fix is a module-scope `const`,
// which needs no helper. This module exists for the other shape: a helper that
// takes the locale as a parameter, so each call is deliberately different and a
// blind hoist would be wrong. Memoizing per locale keeps every call site
// honest — `makeI18n('ar')` still returns an Arabic instance — while building
// at most one instance per locale per test file.
//
// The cache is module scope, and Vitest runs every test file in its own worker
// (`isolate: true`, the default), so the cache never spans files.
//
// DO NOT use this for an instance a test MUTATES (`i18n.global.locale.value =
// …`, `setLocaleMessage`, …). A mutated instance handed to the next caller is a
// cross-test leak. Such call sites must keep building their own instance — see
// `views/llc/__tests__/OrgChart.teamCanvas.test.ts` for that pattern.

/**
 * Wrap a per-locale factory so each distinct locale is built at most once.
 *
 * Deliberately generic over the built value rather than typed to vue-i18n: the
 * call site keeps its own precise `createI18n` inference, including which
 * message bundles it imported.
 */
export function memoizeByLocale<T>(build: (locale: string) => T): (locale: string) => T {
  const cache = new Map<string, T>()
  return (locale: string): T => {
    const cached = cache.get(locale)
    if (cached !== undefined) {
      return cached
    }
    const created = build(locale)
    cache.set(locale, created)
    return created
  }
}
