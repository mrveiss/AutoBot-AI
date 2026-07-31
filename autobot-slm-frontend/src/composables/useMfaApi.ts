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
 *
 * Contract types (#12420 Phase 3): the request/response shapes below are DERIVED
 * from the generated OpenAPI schema (`@/types/generated/api`), which is produced
 * from the SLM backend's own Pydantic models and CI-guarded by
 * `verify-generated-types-slm`. Do not hand-declare them — a backend schema
 * change must surface here as a type error, not as a silent runtime mismatch.
 */

import slmApiClient from '@/utils/ApiClient'
import { useAuthStore } from '@/stores/auth'
import { createAuthGuard } from '@/utils/slmAuthGuard'
import type { components } from '@/types/generated/api'

export type MFASetupResponse = components['schemas']['MFASetupResponse']
export type MFAStatusResponse = components['schemas']['MFAStatusResponse']
export type MFAVerifyRequest = components['schemas']['MFAVerifyRequest']
export type MFADisableRequest = components['schemas']['MFADisableRequest']
export type BackupCodesResponse = components['schemas']['BackupCodesResponse']

/**
 * `POST /mfa/verify-login` and `/mfa/verify-setup` declare no response_model on
 * the backend, so the generated response type is an untyped object and there is
 * no schema to derive from — these two shapes stay hand-declared until the
 * backend types the endpoints.
 */
export interface MFAVerifyResponse {
  success: boolean
  message: string
  access_token?: string
  token_type?: string
  expires_in?: number
}

export function useMfaApi() {
  const authStore = useAuthStore()

  // Preserve the historic "logout on 401" behaviour: the canonical client skips
  // its session-clearing 401 handler for /mfa/ (auth) endpoints, so the guard
  // re-applies it explicitly (shared helper — see utils/slmAuthGuard.ts).
  const withAuthGuard = createAuthGuard(authStore.logout)

  async function setupMFA(): Promise<MFASetupResponse> {
    return withAuthGuard(() => slmApiClient.post<MFASetupResponse>('/mfa/setup'))
  }

  async function verifySetup(
    code: string
  ): Promise<{ success: boolean; message: string }> {
    const body: MFAVerifyRequest = { code }
    return withAuthGuard(() =>
      slmApiClient.post<{ success: boolean; message: string }>(
        '/mfa/verify-setup',
        body
      )
    )
  }

  /**
   * Verify the MFA code during login.
   *
   * `temp_token` is a QUERY parameter, not a body field: the backend declares it
   * as a bare `str` argument alongside the Pydantic body model
   * (`autobot-slm-backend/api/mfa.py:96-99`), which FastAPI binds from the query
   * string — the generated contract confirms it
   * (`operations.verify_mfa_login_api_mfa_verify_login_post.parameters.query`).
   * It used to be sent in the JSON body, which the backend rejects with a 422
   * for the missing required query parameter.
   */
  async function verifyLogin(
    code: string,
    tempToken: string
  ): Promise<MFAVerifyResponse> {
    const body: MFAVerifyRequest = { code }
    const query = new URLSearchParams({ temp_token: tempToken })
    return withAuthGuard(() =>
      slmApiClient.post<MFAVerifyResponse>(
        `/mfa/verify-login?${query.toString()}`,
        body
      )
    )
  }

  async function disableMFA(password: string): Promise<void> {
    const body: MFADisableRequest = { password }
    await withAuthGuard(() => slmApiClient.post('/mfa/disable', body))
  }

  async function getMFAStatus(): Promise<MFAStatusResponse> {
    return withAuthGuard(() =>
      slmApiClient.get<MFAStatusResponse>('/mfa/status')
    )
  }

  async function regenerateBackupCodes(
    password: string
  ): Promise<BackupCodesResponse> {
    const body: MFADisableRequest = { password }
    return withAuthGuard(() =>
      slmApiClient.post<BackupCodesResponse>('/mfa/backup-codes', body)
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
