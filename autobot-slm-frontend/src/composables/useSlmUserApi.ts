// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * SLM User Management API Composable
 *
 * Provides REST API integration for user management via the SLM backend.
 * Manages both SLM admin users (local DB) and AutoBot application users (remote DB).
 * Issue #576 - User Management System.
 *
 * Migrated onto the canonical `slmApiClient` (#12420 Phase 2). The client
 * resolves the base URL via `getSlmApiBase()`, injects the SLM bearer token,
 * and centrally handles 401 for these non-auth endpoints (clear session +
 * redirect to `/login`) — matching the previous axios interceptor that called
 * `authStore.logout()`. Query parameters (skip/limit) are serialised onto the
 * endpoint since the canonical client takes a relative path, not an axios
 * `params` object; call sites receive parsed JSON directly.
 */

import slmApiClient from '@/utils/ApiClient'

// =============================================================================
// Type Definitions
// =============================================================================

export interface RoleResponse {
  id: string
  name: string
  description: string | null
  is_system: boolean
}

export interface SlmUserResponse {
  id: string
  email: string
  username: string
  display_name: string | null
  bio: string | null
  avatar_url: string | null
  org_id: string | null
  is_active: boolean
  is_verified: boolean
  mfa_enabled: boolean
  is_platform_admin: boolean
  preferences: Record<string, unknown>
  roles: RoleResponse[]
  last_login_at: string | null
  created_at: string
  updated_at: string
}

export interface SlmUserListResponse {
  users: SlmUserResponse[]
  total: number
  limit: number
  offset: number
}

export interface TeamResponse {
  id: string
  name: string
  description: string | null
  organization_id: string | null
  created_at: string
  updated_at: string
}

export interface TeamListResponse {
  teams: TeamResponse[]
  total: number
  limit: number
  offset: number
}

export interface CreateUserPayload {
  email: string
  username: string
  password: string
  display_name?: string
  role_ids?: string[]
}

export interface CreateTeamPayload {
  name: string
  description?: string
  organization_id?: string
}

// Serialise pagination params onto the endpoint (the canonical client takes a
// relative path, not an axios `params` object).
function withPaging(path: string, skip: number, limit: number): string {
  const query = new URLSearchParams({
    skip: String(skip),
    limit: String(limit),
  })
  return `${path}?${query.toString()}`
}

export function useSlmUserApi() {
  // ===========================================================================
  // SLM Admin Users (local SLM database)
  // ===========================================================================

  async function getSlmUsers(skip = 0, limit = 100): Promise<SlmUserListResponse> {
    return slmApiClient.get<SlmUserListResponse>(withPaging('/slm-users', skip, limit))
  }

  async function createSlmUser(data: CreateUserPayload): Promise<SlmUserResponse> {
    return slmApiClient.post<SlmUserResponse>('/slm-users', data)
  }

  async function deleteSlmUser(userId: string): Promise<void> {
    await slmApiClient.delete(`/slm-users/${userId}`)
  }

  async function changeSlmUserPassword(userId: string, newPassword: string): Promise<void> {
    await slmApiClient.post(`/slm-users/${userId}/change-password`, { new_password: newPassword })
  }

  // ===========================================================================
  // AutoBot Application Users (remote AutoBot database)
  // ===========================================================================

  async function getAutobotUsers(skip = 0, limit = 100): Promise<SlmUserListResponse> {
    return slmApiClient.get<SlmUserListResponse>(withPaging('/autobot-users', skip, limit))
  }

  async function createAutobotUser(data: CreateUserPayload): Promise<SlmUserResponse> {
    return slmApiClient.post<SlmUserResponse>('/autobot-users', data)
  }

  async function deleteAutobotUser(userId: string): Promise<void> {
    await slmApiClient.delete(`/autobot-users/${userId}`)
  }

  async function changeAutobotUserPassword(userId: string, newPassword: string): Promise<void> {
    await slmApiClient.post(`/autobot-users/${userId}/change-password`, { new_password: newPassword })
  }

  // ===========================================================================
  // AutoBot Teams
  // ===========================================================================

  async function getTeams(skip = 0, limit = 100): Promise<TeamListResponse> {
    return slmApiClient.get<TeamListResponse>(withPaging('/autobot-teams', skip, limit))
  }

  async function createTeam(data: CreateTeamPayload): Promise<TeamResponse> {
    return slmApiClient.post<TeamResponse>('/autobot-teams', data)
  }

  async function deleteTeam(teamId: string): Promise<void> {
    await slmApiClient.delete(`/autobot-teams/${teamId}`)
  }

  async function addTeamMember(
    teamId: string,
    userId: string,
    role = 'member'
  ): Promise<void> {
    await slmApiClient.post(`/autobot-teams/${teamId}/members`, {
      user_id: userId,
      role,
    })
  }

  async function removeTeamMember(teamId: string, userId: string): Promise<void> {
    await slmApiClient.delete(`/autobot-teams/${teamId}/members/${userId}`)
  }

  return {
    // SLM Admin Users
    getSlmUsers,
    createSlmUser,
    deleteSlmUser,
    changeSlmUserPassword,
    // AutoBot Users
    getAutobotUsers,
    createAutobotUser,
    deleteAutobotUser,
    changeAutobotUserPassword,
    // Teams
    getTeams,
    createTeam,
    deleteTeam,
    addTeamMember,
    removeTeamMember,
  }
}
