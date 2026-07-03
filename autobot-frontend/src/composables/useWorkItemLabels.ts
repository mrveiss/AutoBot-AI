// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Work-item enum label composable (#10818).
 *
 * LLC board views (Sprint Board, Backlog, Work Item Detail) render work-item
 * type / priority / sprint-status enum values directly in the UI. This maps
 * those closed enum sets to localized labels under `llc.enums.*`, falling back
 * to the humanized raw value for any value without a translation key (board
 * statuses are configurable, so a missing key must not surface a raw key path).
 */

import { useI18n } from 'vue-i18n'

export function useWorkItemLabels() {
  const { t, te } = useI18n()

  const label = (namespace: string, value: string | null | undefined): string => {
    if (!value) return ''
    const key = `llc.enums.${namespace}.${value}`
    return te(key) ? t(key) : value.replace(/_/g, ' ')
  }

  return {
    workItemTypeLabel: (value: string | null | undefined) => label('workItemType', value),
    priorityLabel: (value: string | null | undefined) => label('priority', value),
    sprintStatusLabel: (value: string | null | undefined) => label('sprintStatus', value),
  }
}
