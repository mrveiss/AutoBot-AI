// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// A refused board move shows the user why, by i18n key (#20508): the status of the refusal picks the reason,
// so the text is localised rather than whatever the server wrote.

/** i18n key for the reason a move was refused, or null when the failure is not a refusal. */
export function moveRefusalKey(err: unknown): string | null {
  const status = (err as { status?: number } | null)?.status
  if (status === 409) return 'llc.board.moveRefusedStatus'
  if (status === 422) return 'llc.board.moveRefusedWipFull'
  if (status === 403) return 'llc.board.moveRefusedForbidden'
  return null
}

/** What the board shows for a failed move: the localised refusal reason, else the error's own message. */
export function moveFailureText(err: unknown, t: (key: string) => string): string {
  const key = moveRefusalKey(err)
  return key ? t(key) : err instanceof Error ? err.message : String(err)
}
