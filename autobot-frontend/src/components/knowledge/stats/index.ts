// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Knowledge Stats Sub-Components
 *
 * Barrel exports for knowledge stats sub-components (stats panels).
 * Extracted from the former KnowledgeStats.vue (#184); mounted into
 * KnowledgeHealthAnalytics.vue (#11562).
 *
 * Issue #184: Split oversized Vue components
 * Issue #11562: Wire in orphaned stats subpanels
 */

export { default as VectorStatsSection } from './VectorStatsSection.vue'
export { default as StatsOverviewCards } from './StatsOverviewCards.vue'
export { default as StatsChartsSection } from './StatsChartsSection.vue'
export { default as RecentActivityPanel } from './RecentActivityPanel.vue'
export { default as TagCloudPanel } from './TagCloudPanel.vue'
export { default as StatsActionsPanel } from './StatsActionsPanel.vue'
