// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Type definitions for AppConfig.js
 *
 * Provides TypeScript interfaces for the application configuration service.
 * This eliminates the need for 'as any' type casts when accessing configuration.
 *
 * Issue #156: Complete type safety for configuration access
 */

import type { ServicesConfig, InfrastructureConfig } from '@/config/AppConfig'

/**
 * Terminal host configuration
 */
export interface HostConfig {
  id: string
  name: string
  ip: string
  port: number
  description: string
  protocol?: string
  username?: string
  type?: 'ssh' | 'telnet' | 'serial'
}

/**
 * Backend configuration from AppConfig service
 */
export interface BackendConfig {
  /**
   * Primary hosts configuration
   */
  hosts?: HostConfig[]

  /**
   * Alternative nested configuration structure
   */
  config?: {
    hosts?: HostConfig[]
    services?: ServicesConfig | Record<string, unknown>
  }

  /**
   * Service configurations
   */
  services?: ServicesConfig | Record<string, unknown>

  /**
   * Infrastructure settings
   */
  infrastructure?: InfrastructureConfig | Record<string, unknown>

  /**
   * Network settings
   */
  network?: {
    backend?: { host: string; port: string; protocol: string }
    frontend?: { host: string; port: string; protocol: string }
    redis?: { host: string; port: string }
    [key: string]: unknown
  }
}

/**
 * AppConfig service interface
 */
export interface AppConfigService {
  /**
   * Get backend configuration
   */
  getBackendConfig(): Promise<BackendConfig>

  /**
   * Get API URL for a specific service
   */
  getApiUrl(service: string): Promise<string>

  /**
   * Get network configuration
   */
  getNetworkConfig(): Promise<BackendConfig['network']>

  /**
   * Initialize configuration
   */
  init(): Promise<void>
}

/**
 * Module declaration for JavaScript AppConfig
 */
declare module '@/config/AppConfig.js' {
  const appConfig: AppConfigService
  export default appConfig
}

/**
 * Alternative module path
 */
declare module '@/config/AppConfig' {
  const appConfig: AppConfigService
  export default appConfig
}
