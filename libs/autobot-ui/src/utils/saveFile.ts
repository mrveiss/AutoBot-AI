// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Save something to the user's disk from the browser: the one implementation (#20770).
 *
 * A temporary anchor with `download` set is attached to the document, clicked and removed.
 * Attaching it is what some browsers need before a synthetic click starts a download. An
 * object URL this module created is revoked once the click has been dispatched, so no
 * caller leaks one. The revoke runs in a later task, not right after the click: some
 * browsers still read the URL after the click task returns, and an early revoke can
 * fail the download (#20872).
 */

function clickAnchor(href: string, filename: string): void {
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = filename
  anchor.rel = 'noopener noreferrer' // an external URL gets no handle on this window
  anchor.style.display = 'none'
  document.body.appendChild(anchor)
  try {
    anchor.click()
  } finally {
    anchor.remove()
  }
}

/** Save a URL the caller already has (a `data:` URL from a canvas, say) as `filename`. */
export function saveUrl(href: string, filename: string): void {
  clickAnchor(href, filename)
}

/** Save a Blob as `filename`. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  try {
    clickAnchor(url, filename)
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }
}

/** Save text as `filename`, with the MIME `type` it is served as (default `text/plain`). */
export function saveTextFile(content: string, filename: string, type = 'text/plain'): void {
  saveBlob(new Blob([content], { type }), filename)
}
