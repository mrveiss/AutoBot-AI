// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * MFA Management API Composable
 *
 * Provides REST API integration for Two-Factor Authentication (2FA/MFA)
 * management via the SLM backend.
 * Issue #576 - User Management System Phase 5 (2FA/MFA).
 *
 * Migrated onto the canonical `slmApiClient` (#12420 Phase 2). The client
 * resolves the base URL via `getSlmApiBase()` and injects the SLM bearer token
 * (same `slm_access_token` storage the auth store reads), so call sites pass
 * endpoints relative to the API base and receive parsed JSON directly.
 */

import slmApiClient from '@/utils/ApiClient'
import { useAuthStore } from '@/stores/auth'

export interface MFASetupResponse {
  secret: string
  otpauth_uri: string
  backup_codes: string[]
}

export interface MFAStatusResponse {
  enabled: boolean
  method: string
  backup_codes_remaining: number
  last_verified_at: string | null
}

export interface MFAVerifyResponse {
  success: boolean
  message: string
  access_token?: string
  token_type?: string
  expires_in?: number
}

export function useMfaApi() {
  const authStore = useAuthStore()

  // The canonical client intentionally skips its session-clearing 401 handler
  // for auth/MFA endpoints (a 401 there is a credential failure, not a rejected
  // session). MFA management historically logged the user out on any 401 — the
  // previous axios response interceptor called `authStore.logout()` — so we
  // preserve that exact behavior explicitly here and re-throw as before.
  async function withAuthGuard<T>(op: () => Promise<T>): Promise<T> {
    try {
      return await op()
    } catch (error) {
      if (error instanceof Error && error.message.startsWith('HTTP 401')) {
        authStore.logout()
      }
      throw error
    }
  }

  async function setupMFA(): Promise<MFASetupResponse> {
    return withAuthGuard(() => slmApiClient.post<MFASetupResponse>('/mfa/setup'))
  }

  async function verifySetup(
    code: string
  ): Promise<{ success: boolean; message: string }> {
    return withAuthGuard(() =>
      slmApiClient.post<{ success: boolean; message: string }>(
        '/mfa/verify-setup',
        { code }
      )
    )
  }

  async function verifyLogin(
    code: string,
    tempToken: string
  ): Promise<MFAVerifyResponse> {
    return withAuthGuard(() =>
      slmApiClient.post<MFAVerifyResponse>('/mfa/verify-login', {
        code,
        temp_token: tempToken,
      })
    )
  }

  async function disableMFA(password: string): Promise<void> {
    await withAuthGuard(() => slmApiClient.post('/mfa/disable', { password }))
  }

  async function getMFAStatus(): Promise<MFAStatusResponse> {
    return withAuthGuard(() =>
      slmApiClient.get<MFAStatusResponse>('/mfa/status')
    )
  }

  async function regenerateBackupCodes(
    password: string
  ): Promise<{ backup_codes: string[] }> {
    return withAuthGuard(() =>
      slmApiClient.post<{ backup_codes: string[] }>('/mfa/backup-codes', {
        password,
      })
    )
  }

  return {
    setupMFA,
    verifySetup,
    verifyLogin,
    disableMFA,
    getMFAStatus,
    regenerateBackupCodes,
  }
}
