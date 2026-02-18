// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Network Constants - Consolidated TypeScript Implementation
 *
 * Issue #603: Migrated to use SSOT config (ssot-config.ts)
 * Issue #172: Original consolidation from network-constants.js
 *
 * All values now come from the Single Source of Truth configuration.
 * No hardcoded values - everything derives from environment variables.
 *
 * Usage:
 *     import { NetworkConstants, ServiceURLs, DatabaseConstants } from '@/constants/network'
 *
 *     // Use VM IP addresses
 *     const redisUrl = `redis://${NetworkConstants.REDIS_VM_IP}:6379`
 *
 *     // Use service URLs
 *     const backendUrl = ServiceURLs.BACKEND_API
 */

import { getConfig, getServiceUrl, getVmIp } from '../config/ssot-config';

// Get the singleton config instance
const config = getConfig();

/**
 * Core network constants for AutoBot distributed infrastructure
 * CRITICAL: All values read from SSOT config (which reads from environment)
 *
 * Service Distribution (6-VM Architecture):
 * - Main Machine (WSL): Backend API + VNC Desktop
 * - VM1 Frontend: Web interface (SINGLE FRONTEND SERVER)
 * - VM2 NPU Worker: Hardware AI acceleration
 * - VM3 Redis: Data layer
 * - VM4 AI Stack: AI processing
 * - VM5 Browser: Web automation (Playwright)
 */
export const NetworkConstants = Object.freeze({
  // Main machine (WSL) - from SSOT config
  MAIN_MACHINE_IP: config.vm.main,

  // VM Infrastructure IPs - from SSOT config
  FRONTEND_VM_IP: config.vm.frontend,
  NPU_WORKER_VM_IP: config.vm.npu,
  REDIS_VM_IP: config.vm.redis,
  AI_STACK_VM_IP: config.vm.aistack,
  BROWSER_VM_IP: config.vm.browser,

  // Local/Localhost addresses - these are standard and don't need env vars
  LOCALHOST_IP: "127.0.0.1" as const,
  LOCALHOST_NAME: "localhost" as const,

  // Standard ports - from SSOT config
  BACKEND_PORT: config.port.backend,
  FRONTEND_PORT: config.port.frontend,
  REDIS_PORT: config.port.redis,
  OLLAMA_PORT: config.port.ollama,
  VNC_PORT: config.port.vnc,
  VNC_DESKTOP_PORT: config.port.vnc, // Alias for clarity
  BROWSER_SERVICE_PORT: config.port.browser,
  AI_STACK_PORT: config.port.aistack,
  NPU_WORKER_PORT: config.port.npu,

  // Development ports - same as standard ports in current config
  DEV_FRONTEND_PORT: config.port.frontend,
  DEV_BACKEND_PORT: config.port.backend
})

/**
 * Pre-built service URLs for common AutoBot services
 * CRITICAL: All URLs derived from SSOT config
 */
export const ServiceURLs = Object.freeze({
  // Backend API URLs
  BACKEND_API: config.backendUrl,
  BACKEND_LOCAL: `${config.httpProtocol}://${NetworkConstants.LOCALHOST_NAME}:${config.port.backend}`,

  // Frontend URLs
  FRONTEND_VM: config.frontendUrl,
  FRONTEND_LOCAL: `${config.httpProtocol}://${NetworkConstants.LOCALHOST_NAME}:${config.port.frontend}`,

  // Redis URLs
  REDIS_VM: config.redisUrl,
  REDIS_LOCAL: `redis://${NetworkConstants.LOCALHOST_IP}:${config.port.redis}`,

  // Ollama LLM URLs
  OLLAMA_LOCAL: `${config.httpProtocol}://${NetworkConstants.LOCALHOST_NAME}:${config.port.ollama}`,
  OLLAMA_MAIN: config.ollamaUrl,

  // VNC Desktop URLs
  VNC_DESKTOP: config.vncUrl,
  VNC_LOCAL: `${config.httpProtocol}://${NetworkConstants.LOCALHOST_NAME}:${config.port.vnc}/vnc.html`,

  // Browser automation service
  BROWSER_SERVICE: config.browserServiceUrl,

  // AI Stack service
  AI_STACK_SERVICE: config.aistackUrl,

  // NPU Worker service
  NPU_WORKER_SERVICE: config.npuWorkerUrl,

  // WebSocket URLs
  WEBSOCKET_API: config.websocketUrl,
  WEBSOCKET_LOCAL: `ws://${NetworkConstants.LOCALHOST_NAME}:${config.port.backend}/ws`
})

/**
 * Dynamic network configuration based on environment
 */
export class NetworkConfig {
  private _deploymentMode: string
  private _isDevelopment: boolean

  constructor() {
    this._deploymentMode = config.deploymentMode
    this._isDevelopment = config.environment === 'development'
  }

  get backendUrl(): string {
    if (this._deploymentMode === 'local') {
      return ServiceURLs.BACKEND_LOCAL
    }
    return ServiceURLs.BACKEND_API
  }

  get frontendUrl(): string {
    if (this._deploymentMode === 'local') {
      return ServiceURLs.FRONTEND_LOCAL
    }
    return ServiceURLs.FRONTEND_VM
  }

  get redisUrl(): string {
    if (this._deploymentMode === 'local') {
      return ServiceURLs.REDIS_LOCAL
    }
    return ServiceURLs.REDIS_VM
  }

  get ollamaUrl(): string {
    return ServiceURLs.OLLAMA_LOCAL // Always local for now
  }

  getServiceUrl(serviceName: string): string | null {
    // Use SSOT helper function
    const url = getServiceUrl(serviceName)
    if (url) return url

    // Fallback for deployment mode-specific URLs
    const serviceMap: Record<string, string> = {
      'backend': this.backendUrl,
      'frontend': this.frontendUrl,
      'redis': this.redisUrl,
      'ollama': this.ollamaUrl,
      'browser': ServiceURLs.BROWSER_SERVICE,
      'ai_stack': ServiceURLs.AI_STACK_SERVICE,
      'npu_worker': ServiceURLs.NPU_WORKER_SERVICE,
      'vnc': ServiceURLs.VNC_DESKTOP
    }
    return serviceMap[serviceName] || null
  }

  getVmIp(vmName: string): string | null {
    // Use SSOT helper function
    const ip = getVmIp(vmName)
    if (ip) return ip

    // Fallback for direct lookups
    const vmMap: Record<string, string> = {
      'main': NetworkConstants.MAIN_MACHINE_IP,
      'frontend': NetworkConstants.FRONTEND_VM_IP,
      'npu_worker': NetworkConstants.NPU_WORKER_VM_IP,
      'redis': NetworkConstants.REDIS_VM_IP,
      'ai_stack': NetworkConstants.AI_STACK_VM_IP,
      'browser': NetworkConstants.BROWSER_VM_IP
    }
    return vmMap[vmName] || null
  }
}

// Global network configuration instance
export const networkConfig = new NetworkConfig()

/**
 * Redis database assignments to eliminate hardcoded database numbers
 */
export const DatabaseConstants = Object.freeze({
  // Core databases
  MAIN_DB: 0,
  KNOWLEDGE_DB: 1,
  CACHE_DB: 2,
  VECTORS_DB: 8,

  // Specialized databases
  SESSIONS_DB: 3,
  METRICS_DB: 4,
  LOGS_DB: 5,
  CONFIG_DB: 6,
  WORKFLOWS_DB: 7,
  TEMP_DB: 9,
  MONITORING_DB: 10,
  RATE_LIMITING_DB: 11
})

// Legacy compatibility exports
export const BACKEND_URL = ServiceURLs.BACKEND_API
export const FRONTEND_URL = ServiceURLs.FRONTEND_VM
export const REDIS_HOST = NetworkConstants.REDIS_VM_IP
export const MAIN_MACHINE_IP = NetworkConstants.MAIN_MACHINE_IP
export const LOCALHOST_IP = NetworkConstants.LOCALHOST_IP

// Default export
export default NetworkConstants
