// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** The backend's stable desktop-control error codes (api/vnc_host_target.py) mapped to i18n keys (#22191). */
export const CONTROL_ERROR_KEYS: Record<string, string> = {
  vnc_credential_missing: 'desktop.interface.vncCredentialMissing',
  host_not_found: 'desktop.interface.hostNotFound',
  host_fields_missing: 'desktop.interface.hostFieldsMissing',
  host_vnc_unavailable: 'desktop.interface.hostVncUnavailable'
}

/** The translated text for a control failure: by stable code when known, else the response's own message. */
export function controlErrorText(
  result: { message: string; code?: string },
  t: (key: string) => string
): string {
  const key = result.code ? CONTROL_ERROR_KEYS[result.code] : undefined
  return key ? t(key) : result.message
}
