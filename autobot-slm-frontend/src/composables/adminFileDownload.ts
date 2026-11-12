// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Byte-exact download for the SLM File Browser (#21029).
 *
 * `GET /files/read` returns the file as a JSON string decoded with replacement characters,
 * so a binary file saved from it is corrupt. This fetches the raw route and keeps the
 * bytes as a Blob from the response to the saved file; the kit's `saveBlob` does the save.
 */

import { HttpError, saveBlob } from '@autobot/ui'
import { createAutobotBackendClient } from '@/composables/useAutobotApi'

const client = createAutobotBackendClient()

/** Fetch `path` from the main backend as raw bytes and save it as `filename`. */
export async function downloadAdminFile(path: string, filename: string): Promise<void> {
  const response = await client.rawRequest('/files/raw', { method: 'GET', params: { path } })
  if (!response.ok) {
    throw new HttpError(response.status, response.statusText || undefined)
  }
  saveBlob(await response.blob(), filename)
}

/** i18n key shown when the main backend refuses the SLM token (#10193); null for any other error. */
export const DOWNLOAD_UNAUTHORIZED_KEY = 'tools.admin.fileBrowserTool.downloadUnauthorized'

export function downloadErrorKey(error: unknown): string | null {
  return error instanceof HttpError && error.status === 401 ? DOWNLOAD_UNAUTHORIZED_KEY : null
}
