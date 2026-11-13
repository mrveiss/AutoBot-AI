// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { computed } from 'vue'
import type { RouteLocationNormalizedLoaded } from 'vue-router'

/**
 * Issue #3436: which per-project sub-tab the current route is on.
 *
 * Moved out of `CodebaseAnalytics.vue` unchanged (#21003: that file is at its size ceiling).
 */
export function useProjectSubTabs(route: RouteLocationNormalizedLoaded) {
  // Active when on the exact project path (no child segment)
  const isOverviewTabActive = computed(() => /^\/analytics\/codebase\/[^/]+\/?$/.test(route.path))
  const isCodeQualityTabActive = computed(() => route.path.includes('/code-quality'))
  const isCodeReviewTabActive = computed(() => route.path.includes('/code-review'))
  const isEvolutionTabActive = computed(() => route.path.endsWith('/evolution'))
  const isCodeGenerationTabActive = computed(() => route.path.includes('/code-generation'))
  return { isOverviewTabActive, isCodeQualityTabActive, isCodeReviewTabActive, isEvolutionTabActive, isCodeGenerationTabActive }
}
