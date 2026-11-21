// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// A refused board move shows the user why, by i18n key (#20508): the status of the refusal picks the reason,
// so the text is localised rather than whatever the server wrote. A 422 is the WIP-limit refusal only when its
// detail carries the WIP error code (boards.py); FastAPI validation errors are 422 too and read as a plain failure.

const WIP_LIMIT_CODE = 'WIP_LIMIT_EXCEEDED'

function isWipRefusal(err: unknown): boolean {
  const detail = (err as { details?: { detail?: unknown } } | null)?.details?.detail
  return (detail as { code?: unknown } | null)?.code === WIP_LIMIT_CODE
}

/** i18n key for the reason a move was refused, or null when the failure is not a refusal. */
export function moveRefusalKey(err: unknown): string | null {
  const status = (err as { status?: number } | null)?.status
  if (status === 409) return 'llc.board.moveRefusedStatus'
  if (status === 422) return isWipRefusal(err) ? 'llc.board.moveRefusedWipFull' : 'llc.board.moveFailed'
  if (status === 403) return 'llc.board.moveRefusedForbidden'
  return null
}

/** What the board shows for a failed move: the localised refusal reason, else the generic text (the raw error is logged). */
export function moveFailureText(err: unknown, t: (key: string) => string): string {
  const key = moveRefusalKey(err)
  return t(key ?? 'llc.board.moveFailed')
}
