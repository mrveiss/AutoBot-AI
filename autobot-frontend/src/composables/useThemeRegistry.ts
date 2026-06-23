// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useThemeRegistry.ts — installed theme registry (#10472)
 *
 * Fetches the list of admin-installed theme packages from the backend so the
 * user frontend can offer them as selectable variants at runtime. Degrades
 * gracefully to built-in variants only when the registry is unavailable.
 */
import { apiClient } from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const log = createLogger('ThemeRegistry')

export interface InstalledTheme {
  id: string
  name: string
  author: string
  version: string
  supports: string[]
}

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
