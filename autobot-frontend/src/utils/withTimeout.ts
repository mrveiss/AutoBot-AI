// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Race a promise against a deadline, then clear the deadline's timer whichever
 * side settles first (#16274; first used by TerminalModals, #16285).
 *
 * The bare pattern -- `Promise.race([work, new Promise((_, r) => setTimeout(r, ms))])`
 * -- leaves the losing timer pending. The rejection lands in a race that has
 * already settled, so nobody sees it, but the timer still holds its closure until
 * it fires.
 */
export function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(message)), ms)
  })
  return Promise.race([promise, deadline]).finally(() => clearTimeout(timer))
}
