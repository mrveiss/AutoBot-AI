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
 *
 * Contract types (#12420 Phase 3): the request/response shapes below are DERIVED
 * from the generated OpenAPI schema (`@/types/generated/api`), which is produced
 * from the SLM backend's own Pydantic models and CI-guarded by
 * `verify-generated-types-slm`. Do not hand-declare them — a backend schema
 * change must surface here as a type error, not as a silent runtime mismatch.
 */

import slmApiClient from '@/utils/ApiClient'
import type { components } from '@/types/generated/api'

// =============================================================================
// Type Definitions — derived from the generated OpenAPI contract
// =============================================================================

// Both /slm-users and /autobot-users serve the `autobot_shared` user schemas
// (the generated names are FastAPI's disambiguation of two same-named models).
export type RoleResponse =
  components['schemas']['autobot_shared__user_management__schemas__user__RoleResponse']
export type SlmUserResponse =
  components['schemas']['autobot_shared__user_management__schemas__user__UserResponse']
export type SlmUserListResponse = components['schemas']['UserListResponse']
export type CreateUserPayload =
  components['schemas']['autobot_shared__user_management__schemas__user__UserCreate']
export type PasswordChange = components['schemas']['PasswordChange']

export type TeamResponse = components['schemas']['TeamResponse']
export type TeamListResponse = components['schemas']['TeamListResponse']
export type CreateTeamPayload = components['schemas']['TeamCreate']
export type TeamMemberAdd = components['schemas']['TeamMemberAdd']

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
    const body: PasswordChange = { new_password: newPassword }
    await slmApiClient.post(`/slm-users/${userId}/change-password`, body)
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
    const body: PasswordChange = { new_password: newPassword }
    await slmApiClient.post(`/autobot-users/${userId}/change-password`, body)
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
    const body: TeamMemberAdd = { user_id: userId, role }
    await slmApiClient.post(`/autobot-teams/${teamId}/members`, body)
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
