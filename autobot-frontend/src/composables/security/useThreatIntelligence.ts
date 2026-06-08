// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useThreatIntelligence — API wrappers for threat-intelligence and
 * domain-security endpoints used by ThreatIntelligenceDashboard.
 *
 * Extracted from ThreatIntelligenceDashboard.vue (issue #6090).
 */

import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'

export interface ThreatIntelStatus {
  any_service_configured: boolean
  virustotal: Record<string, unknown> | null
  urlvoid: Record<string, unknown> | null
  cache_stats: Record<string, unknown> | null
}

export interface DomainSecurityStats {
  whitelist_count: number
  blacklist_count: number
  suspicious_tlds_count: number
  settings: Record<string, unknown> | null
  threat_intelligence: Record<string, unknown> | null
}

export interface CheckUrlResult {
  success: boolean
  url: string
  overall_score: number
  threat_level: string
  virustotal_score: number | null
  urlvoid_score: number | null
  sources_checked: number
  cached: boolean
  message?: string
}

export function useThreatIntelligence() {
  /** Fetch threat-intelligence service status. */
  async function fetchThreatIntelStatus(): Promise<ThreatIntelStatus> {
    const response = await apiClient.get<any>(`${getApiBase()}/security/threat-intel/status`)
    const data = (response as { data?: Record<string, unknown> }).data
    return {
      any_service_configured: (data?.any_service_configured as boolean) ?? false,
      virustotal: (data?.virustotal as Record<string, unknown> | null) ?? null,
      urlvoid: (data?.urlvoid as Record<string, unknown> | null) ?? null,
      cache_stats: (data?.cache_stats as Record<string, unknown> | null) ?? null,
    }
  }

  /** Fetch domain-security statistics. */
  async function fetchDomainSecurityStats(): Promise<DomainSecurityStats> {
    const response = await apiClient.get<any>(`${getApiBase()}/security/domain-security/stats`)
    const data = (response as { data?: Record<string, unknown> }).data
    const stats = (data?.success ? (data.stats as Record<string, unknown>) : null) ?? {}
    return {
      whitelist_count: (stats.whitelist_count as number) || 0,
      blacklist_count: (stats.blacklist_count as number) || 0,
      suspicious_tlds_count: (stats.suspicious_tlds_count as number) || 0,
      settings: (stats.settings as Record<string, unknown>) || null,
      threat_intelligence: (stats.threat_intelligence as Record<string, unknown>) || null,
    }
  }

  /** Check a URL against threat-intelligence services. */
  async function checkUrl(url: string): Promise<CheckUrlResult> {
    const response = await apiClient.post<any>(`${getApiBase()}/security/threat-intel/check-url`, { url })
    const data = (response as { data?: CheckUrlResult }).data
    if (!data) {
      throw new Error('Empty response from threat-intel check-url')
    }
    return data
  }

  return { fetchThreatIntelStatus, fetchDomainSecurityStats, checkUrl }
}
