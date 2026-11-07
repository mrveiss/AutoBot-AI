// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0

/**
 * First usable backend timestamp as a Date, or undefined when the entry carries none
 * (#20865). An absent, empty, unparseable or epoch-0 value is "undated" so it is never
 * displayed as 1970. This is the one place session timestamps are converted.
 */
export function toSessionDate(...candidates: Array<string | undefined>): Date | undefined {
  for (const candidate of candidates) {
    if (!candidate) continue
    const date = new Date(candidate)
    if (!Number.isNaN(date.getTime()) && date.getTime() > 0) return date
  }
  return undefined
}
