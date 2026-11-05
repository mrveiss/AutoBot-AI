// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useThemeRegistry.ts — installed theme registry (#10472)
 *
 * Fetches the list of admin-installed theme packages from the backend so the
 * user frontend can offer them as selectable variants at runtime. Degrades
 * gracefully to built-in variants only when the registry is unavailable.
 */
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import type { InstalledTheme } from '@autobot/ui'

const log = createLogger('ThemeRegistry')

// The one declaration lives in the kit (#14908); re-exported so this module's importers keep working.
export type { InstalledTheme }

/** Fetch installed theme descriptors. Returns [] on any error (graceful degrade). */
export async function fetchInstalledThemes(): Promise<InstalledTheme[]> {
  try {
    const themes = await apiClient.get<InstalledTheme[]>('/api/themes')
    return Array.isArray(themes) ? themes : []
  } catch (err) {
    log.warn('Failed to fetch installed themes; using built-ins only', err)
    return []
  }
}
