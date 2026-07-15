// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Detect code-split chunk load failures.
 *
 * When a redeploy replaces hashed chunk filenames, a client still holding a
 * stale index.html requests the old names and the import fails. Browsers and
 * Vite report this in several ways — older bundlers say "Loading chunk" /
 * "ChunkLoadError", while Vite 5+ emits "Failed to fetch dynamically imported
 * module" (or "error loading dynamically imported module"). Recovery logic must
 * match all of them, or the auto-reload never fires and the user is stuck on a
 * failed navigation until a manual hard reload.
 */

function errorMessageOf(error: unknown): string {
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  if (error && typeof error === 'object' && 'message' in error) {
    const message = (error as { message?: unknown }).message
    if (typeof message === 'string') return message
  }
  return ''
}

/** True for any code-split chunk load failure (JS or CSS), across bundler versions. */
export function isChunkLoadError(error: unknown): boolean {
  const message = errorMessageOf(error)
  if (!message) return false
  return (
    message.includes('Loading chunk') ||
    message.includes('Loading CSS chunk') ||
    message.includes('ChunkLoadError') ||
    message.includes('Failed to fetch dynamically imported module') ||
    message.includes('error loading dynamically imported module')
  )
}

/** True specifically for a CSS chunk load failure (subset of isChunkLoadError). */
export function isCssChunkLoadError(error: unknown): boolean {
  return errorMessageOf(error).includes('Loading CSS chunk')
}
