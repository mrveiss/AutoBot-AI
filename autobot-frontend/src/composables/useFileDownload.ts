// autobot-frontend/src/composables/useFileDownload.ts
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

/**
 * Composable for client-side file downloads
 *
 * Provides a reusable interface for downloading blobs as files.
 * Handles proper cleanup and browser compatibility.
 *
 * @example
 * ```ts
 * const { download } = useFileDownload()
 *
 * // Download from Response
 * const response = await fetch('/api/export')
 * const blob = await response.blob()
 * download(blob, 'export.pdf')
 *
 * // Download from string content
 * const content = JSON.stringify(data, null, 2)
 * const blob = new Blob([content], { type: 'application/json' })
 * download(blob, 'data.json')
 * ```
 */

export interface FileDownloadOptions {
  /**
   * Whether to append the link element to the document body.
   * Some browsers require this for the download to work.
   * @default true
   */
  appendToBody?: boolean
}

export function useFileDownload() {
  /**
   * Trigger a file download in the browser
   *
   * @param blob - The blob content to download
   * @param filename - The filename to save as (including extension)
   * @param options - Optional configuration
   */
  function download(
    blob: Blob,
    filename: string,
    options: FileDownloadOptions = {}
  ): void {
    const { appendToBody = true } = options

    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename

    if (appendToBody) {
      document.body.appendChild(link)
    }

    link.click()

    if (appendToBody) {
      document.body.removeChild(link)
    }

    URL.revokeObjectURL(url)
  }

  /**
   * Download text content as a file
   *
   * @param content - The text content to download
   * @param filename - The filename to save as
   * @param mimeType - MIME type for the blob (default: 'text/plain')
   */
  function downloadText(
    content: string,
    filename: string,
    mimeType: string = 'text/plain'
  ): void {
    const blob = new Blob([content], { type: mimeType })
    download(blob, filename)
  }

  return {
    download,
    downloadText
  }
}
