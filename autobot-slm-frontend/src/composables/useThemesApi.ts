// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Theme packages (#20605): the main backend's `/themes` routes (autobot-backend/api/themes.py),
 * reached through the shared main-backend client, which the SLM proxy serves at `/autobot-api`.
 *
 * `GET /themes` answers a bare list of descriptors (`ThemeDescriptor` in theme_install.py);
 * `POST /themes` takes a multipart `file` (a .zip holding theme.json and theme.css) and answers the
 * installed descriptor; `DELETE /themes/{id}` answers `{ status: "deleted", id }`. The writes are
 * admin only on the backend, and the SLM proxy lets only an admin session through at all.
 */

import { isHttpError, type InstalledTheme } from '@autobot/ui'
import i18n from '@/i18n'
import { createAutobotBackendClient } from '@/composables/useAutobotApi'

/** The proxy refused the body before the main backend saw it: its own size cap (413). */
export const UPLOAD_TOO_LARGE_STATUS = 413
/** The client's own message for a request that timed out (ApiClientBase `armAbort`). */
const TIMEOUT_MESSAGE = /^Request timeout/
/** What the proxy answers when the main backend does not. */
const MAIN_APP_DOWN_STATUSES = [502, 503, 504]

// The one declaration lives in the kit (#14908); re-exported so this module's importers keep working.
export type { InstalledTheme }

/**
 * True when the main app could not be reached: the proxy's 502/503/504, or a request that never
 * got an answer: a network failure (fetch's TypeError) or the client's timeout. Any other error is
 * an answer the screen reads as a failure.
 */
export function isMainAppUnavailable(err: unknown): boolean {
  if (isHttpError(err)) return MAIN_APP_DOWN_STATUSES.includes(err.status)
  return err instanceof TypeError || (err instanceof Error && TIMEOUT_MESSAGE.test(err.message))
}

export function useThemesApi() {
  const client = createAutobotBackendClient()

  async function list(): Promise<InstalledTheme[]> {
    const response = await client.get<InstalledTheme[]>('/themes', { maxRetries: 1 })
    if (!Array.isArray(response)) throw new Error(i18n.global.t('settings.admin.themeManager.malformedList'))
    return response
  }

  /** Admin only. Rejects with the backend's `detail` for a bad package (400) or a taken id (409). */
  function install(file: File): Promise<InstalledTheme> {
    const form = new FormData()
    form.append('file', file)
    return client.post<InstalledTheme>('/themes', form)
  }

  /** Admin only. */
  async function uninstall(id: string): Promise<void> {
    await client.delete(`/themes/${encodeURIComponent(id)}`)
  }

  return { list, install, uninstall }
}
