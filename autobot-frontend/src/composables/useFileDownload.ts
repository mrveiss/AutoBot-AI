// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable for triggering client-side file downloads from blob responses.
 *
 * Usage:
 *   const { downloadBlob } = useFileDownload()
 *   const response = await ApiClient.get('/api/export')
 *   const blob = await response.blob()
 *   downloadBlob(blob, 'filename.pdf')
 *
 * Or inline:
 *   downloadBlob(await (await ApiClient.get('/api/export')).blob(), 'file.pdf')
 */
export function useFileDownload() {
  /**
   * Trigger a browser download from a Blob object.
   * Creates an ephemeral <a> element, clicks it, and cleans up the object URL.
   *
   * @param blob - The blob to download
   * @param filename - The filename to save as (including extension)
   */
  function downloadBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  return { downloadBlob }
}
