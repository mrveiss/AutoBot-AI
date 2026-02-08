// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * SLM User Management API Composable
 *
 * Provides REST API integration for user management via the SLM backend.
 * Manages both SLM admin users (local DB) and AutoBot application users (remote DB).
 * Issue #576 - User Management System.
 */

import axios, { type AxiosInstance } from 'axios'
import { useAuthStore } from '@/stores/auth'

// SLM API is proxied via nginx at /api/
const SLM_API_BASE = '/api'

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

export function useSlmUserApi() {
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

  // ===========================================================================
  // SLM Admin Users (local DB on 172.16.168.19)
  // ===========================================================================

  async function getSlmUsers(skip = 0, limit = 100): Promise<SlmUserListResponse> {
    const response = await client.get<SlmUserListResponse>('/slm-users', {
      params: { skip, limit },
    })
    return response.data
  }

  async function createSlmUser(data: CreateUserPayload): Promise<SlmUserResponse> {
    const response = await client.post<SlmUserResponse>('/slm-users', data)
    return response.data
  }

  async function deleteSlmUser(userId: string): Promise<void> {
    await client.delete(`/slm-users/${userId}`)
  }

  // ===========================================================================
  // AutoBot Application Users (remote DB on 172.16.168.23)
  // ===========================================================================

  async function getAutobotUsers(skip = 0, limit = 100): Promise<SlmUserListResponse> {
    const response = await client.get<SlmUserListResponse>('/autobot-users', {
      params: { skip, limit },
    })
    return response.data
  }

  async function createAutobotUser(data: CreateUserPayload): Promise<SlmUserResponse> {
    const response = await client.post<SlmUserResponse>('/autobot-users', data)
    return response.data
  }

  async function deleteAutobotUser(userId: string): Promise<void> {
    await client.delete(`/autobot-users/${userId}`)
  }

  // ===========================================================================
  // AutoBot Teams
  // ===========================================================================

  async function getTeams(skip = 0, limit = 100): Promise<TeamListResponse> {
    const response = await client.get<TeamListResponse>('/autobot-teams', {
      params: { skip, limit },
    })
    return response.data
  }

  async function createTeam(data: CreateTeamPayload): Promise<TeamResponse> {
    const response = await client.post<TeamResponse>('/autobot-teams', data)
    return response.data
  }

  async function deleteTeam(teamId: string): Promise<void> {
    await client.delete(`/autobot-teams/${teamId}`)
  }

  async function addTeamMember(
    teamId: string,
    userId: string,
    role = 'member'
  ): Promise<void> {
    await client.post(`/autobot-teams/${teamId}/members`, {
      user_id: userId,
      role,
    })
  }

  async function removeTeamMember(teamId: string, userId: string): Promise<void> {
    await client.delete(`/autobot-teams/${teamId}/members/${userId}`)
  }

  return {
    // SLM Admin Users
    getSlmUsers,
    createSlmUser,
    deleteSlmUser,
    // AutoBot Users
    getAutobotUsers,
    createAutobotUser,
    deleteAutobotUser,
    // Teams
    getTeams,
    createTeam,
    deleteTeam,
    addTeamMember,
    removeTeamMember,
  }
}
