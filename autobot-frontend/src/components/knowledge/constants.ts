// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Shared constants for knowledge graph components (Issue #759).
 *
 * Extracted from EntityDetail.vue and KnowledgeGraphExplorer.vue
 * to eliminate duplication (H2 in #1077).
 */

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

export const eventTypeIconMap: Record<string, string> = {
  action: 'fas fa-bolt',
  decision: 'fas fa-gavel',
  change: 'fas fa-exchange-alt',
  milestone: 'fas fa-flag',
  occurrence: 'fas fa-circle',
}

export function getEventTypeIcon(type: string): string {
  return eventTypeIconMap[type.toLowerCase()] ?? eventTypeIconMap.occurrence
}
