// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Shared constants + helpers for the LLM-provider sign-in redirect flow (#19241).
 * The initiating component and the callback view MUST post the identical
 * redirect_uri, so it is built in exactly one place.
 */
import { getConfig } from '@/config/ssot-config'

/**
 * SPA route the provider redirects back to with `?code=..&state=..`. The backend
 * accepts only this exact path: PROVIDER_OAUTH_CALLBACK_PATH in
 * autobot-backend/api/provider_auth_scope.py -- change both together.
 */
export const PROVIDER_OAUTH_CALLBACK_PATH = '/preferences/oauth/callback'

/** SPA route hosting Settings (the page that owns the API Keys tab). */
export const PROVIDER_OAUTH_SETTINGS_PATH = '/preferences'

export type ProviderAuthScope = 'system' | 'user'
export type ProviderAuthFlow = 'redirect' | 'device'

export interface ProviderInfo {
  name: string
  label: string
  flows: ProviderAuthFlow[]
  configured: boolean
  missing_settings: string[]
}

/** SSOT frontend origin + callback path. */
export function buildProviderRedirectUri(): string {
  return `${getConfig().frontendUrl}${PROVIDER_OAUTH_CALLBACK_PATH}`
}
