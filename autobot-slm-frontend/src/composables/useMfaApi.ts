// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * MFA Management API Composable
 *
 * Provides REST API integration for Two-Factor Authentication (2FA/MFA)
 * management via the SLM backend.
 * Issue #576 - User Management System Phase 5 (2FA/MFA).
 */

import axios, { type AxiosInstance } from 'axios'
import { useAuthStore } from '@/stores/auth'

const SLM_API_BASE = '/api'

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

  const client: AxiosInstance = axios.create({
    baseURL: SLM_API_BASE,
    headers: { 'Content-Type': 'application/json' },
    timeout: 30000,
  })

  client.interceptors.request.use((config) => {
    const token = authStore.token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  client.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response?.status === 401) {
        authStore.logout()
      }
      return Promise.reject(error)
    }
  )

  async function setupMFA(): Promise<MFASetupResponse> {
    const response = await client.post<MFASetupResponse>('/mfa/setup')
    return response.data
  }

  async function verifySetup(
    code: string
  ): Promise<{ success: boolean; message: string }> {
    const response = await client.post<{ success: boolean; message: string }>(
      '/mfa/verify-setup',
      { code }
    )
    return response.data
  }

  async function verifyLogin(
    code: string,
    tempToken: string
  ): Promise<MFAVerifyResponse> {
    const response = await client.post<MFAVerifyResponse>(
      '/mfa/verify-login',
      { code, temp_token: tempToken }
    )
    return response.data
  }

  async function disableMFA(password: string): Promise<void> {
    await client.post('/mfa/disable', { password })
  }

  async function getMFAStatus(): Promise<MFAStatusResponse> {
    const response = await client.get<MFAStatusResponse>('/mfa/status')
    return response.data
  }

  async function regenerateBackupCodes(
    password: string
  ): Promise<{ backup_codes: string[] }> {
    const response = await client.post<{ backup_codes: string[] }>(
      '/mfa/backup-codes',
      { password }
    )
    return response.data
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
