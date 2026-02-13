// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Commit Hash Utilities (Issue #866)
 *
 * Standardizes commit hash display to 12-character format across all views.
 * This matches Git CLI conventions and ensures GitHub traceability.
 */

/**
 * Format a commit hash to standard 12-character display format.
 *
 * @param hash - Full or partial commit hash (can be null/undefined)
 * @returns 12-character hash or 'Unknown' if hash is invalid
 *
 * @example
 * formatCommitHash('aab20ebe36771408f23f5b4b9b390d915e2c2f46') // 'aab20ebe3677'
 * formatCommitHash('aab20ebe') // 'aab20ebe    ' (padded if too short)
 * formatCommitHash(null) // 'Unknown'
 */
export function formatCommitHash(hash: string | null | undefined): string {
  if (!hash || hash.trim() === '') {
    return 'Unknown'
  }

  const trimmed = hash.trim()

  // If hash is already 12 chars or longer, take first 12
  if (trimmed.length >= 12) {
    return trimmed.substring(0, 12)
  }

  // If shorter than 12, return as-is (partial hashes from git log --oneline)
  return trimmed
}

/**
 * Get display text and full hash for tooltip.
 *
 * @param hash - Full or partial commit hash
 * @returns Object with display text and full hash for tooltip
 *
 * @example
 * getCommitHashDisplay('aab20ebe36771408f23f5b4b9b390d915e2c2f46')
 * // { display: 'aab20ebe3677', full: 'aab20ebe36771408f23f5b4b9b390d915e2c2f46' }
 */
export function getCommitHashDisplay(hash: string | null | undefined): {
  display: string
  full: string | null
} {
  if (!hash || hash.trim() === '') {
    return { display: 'Unknown', full: null }
  }

  const trimmed = hash.trim()
  return {
    display: formatCommitHash(trimmed),
    full: trimmed.length === 40 ? trimmed : null, // Only set full if it's a complete hash
  }
}

/**
 * Check if a hash is a full 40-character SHA-1 hash.
 *
 * @param hash - Commit hash to check
 * @returns True if hash is exactly 40 hex characters
 */
export function isFullHash(hash: string | null | undefined): boolean {
  if (!hash) return false
  return /^[0-9a-f]{40}$/i.test(hash.trim())
}
