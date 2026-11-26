// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The desktop VM's endpoint as the backend resolves it (the SLM's registered VNC desktop node), the one
 * answer the picker, the page and the controls share. No node registered = `null`, never a guess.
 */

import ApiClient from '@/utils/ApiClient'
import type { DesktopVmEndpoint } from '@/config/vnc-client'

/** The desktop VM endpoint, or null when no VNC desktop node is registered. Throws when the registry is unreadable. */
export async function fetchDesktopVmEndpoint(): Promise<DesktopVmEndpoint | null> {
  return (await ApiClient.call('get', '/api/vnc-proxy/desktop/endpoint')) ?? null
}

/**
 * The i18n key explaining why the desktop VM cannot be shown, or null when it can: a registered node means
 * the viewer may load; none, or an unreadable registry, is a localised state instead of a broken iframe.
 */
export async function desktopVmBlockedKey(): Promise<string | null> {
  try {
    return (await fetchDesktopVmEndpoint()) ? null : 'desktop.interface.desktopVmUnavailable'
  } catch {
    return 'desktop.interface.registryUnavailable'
  }
}
