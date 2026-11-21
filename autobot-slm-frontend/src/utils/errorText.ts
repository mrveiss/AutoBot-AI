// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import i18n from '@/i18n'

/** JSON text of a value, or '' when it carries nothing readable (undefined, null, `{}`, circular). */
function jsonText(value: unknown): string {
  try {
    const text = JSON.stringify(value)
    return typeof text === 'string' && text !== 'null' && text !== '{}' ? text : ''
  } catch {
    return ''
  }
}

/**
 * Readable text for a caught value; never "[object Object]" and never empty (#19068).
 * An Error's non-empty message, a non-empty string as is, any other value as JSON, else the
 * translated `fallback`. As with `autobotApiErrorMessage`, the fallback is translated text
 * supplied by the caller; the default is the shared `common.errors.unknown`.
 */
export function errorText(err: unknown, fallback: string = i18n.global.t('common.errors.unknown')): string {
  if (err instanceof Error) return err.message.length > 0 ? err.message : fallback
  if (typeof err === 'string') return err.length > 0 ? err : fallback
  return jsonText(err) || fallback
}
