// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Type definitions for AppConfig.js
 *
 * Provides TypeScript interfaces for the application configuration service.
 * This eliminates the need for 'as any' type casts when accessing configuration.
 *
 * Issue #156: Complete type safety for configuration access
 */

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
    services?: Record<string, any>
  }

  /**
   * Service configurations
   */
  services?: Record<string, any>

  /**
   * Infrastructure settings
   */
  infrastructure?: Record<string, any>

  /**
   * Network settings
   */
  network?: {
    backend?: { host: string; port: string; protocol: string }
    frontend?: { host: string; port: string; protocol: string }
    redis?: { host: string; port: string }
    [key: string]: any
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
