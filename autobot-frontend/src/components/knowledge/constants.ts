// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Shared constants for knowledge graph components (Issue #759).
 *
 * Extracted from EntityDetail.vue and KnowledgeGraphExplorer.vue
 * to eliminate duplication (H2 in #1077).
 */

import type { IconName } from '@/components/ui/Icon.vue'

export const entityTypeColorMap: Record<string, string> = {
  person: 'rgba(59, 130, 246, 0.8)',
  organization: 'rgba(168, 85, 247, 0.8)',
  location: 'rgba(34, 197, 94, 0.8)',
  concept: 'rgba(249, 115, 22, 0.8)',
  technology: 'rgba(14, 165, 233, 0.8)',
  event: 'rgba(244, 63, 94, 0.8)',
  document: 'rgba(107, 114, 128, 0.8)',
  other: 'rgba(156, 163, 175, 0.8)',
}

export function getEntityTypeColor(type: string): string {
  return entityTypeColorMap[type.toLowerCase()] ?? entityTypeColorMap.other
}

export const eventTypeColorMap: Record<string, string> = {
  action: 'rgba(59, 130, 246, 0.9)',
  decision: 'rgba(168, 85, 247, 0.9)',
  change: 'rgba(249, 115, 22, 0.9)',
  milestone: 'rgba(34, 197, 94, 0.9)',
  occurrence: 'rgba(107, 114, 128, 0.9)',
}

export function getEventTypeColor(type: string): string {
  return eventTypeColorMap[type.toLowerCase()] ?? eventTypeColorMap.occurrence
}

// #9724: consumed by <Icon :name="..."> (EventTimeline) — must be SVG
// IconNames; the previous FA class strings rendered empty SVGs.
export const eventTypeIconMap: Record<string, IconName> = {
  action: 'bolt',
  decision: 'check-square',
  change: 'exchange-alt',
  milestone: 'flag',
  occurrence: 'circle',
}

export function getEventTypeIcon(type: string): IconName {
  return eventTypeIconMap[type.toLowerCase()] ?? eventTypeIconMap.occurrence
}
