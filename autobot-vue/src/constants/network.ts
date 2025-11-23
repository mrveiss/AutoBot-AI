// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Network Constants - Consolidated TypeScript Implementation
 *
 * Issue #172: Consolidated from network-constants.js
 * - Preserves ALL features from network-constants.js
 * - Adds TypeScript type safety
 * - NO HARDCODED VALUES - all values from DEFAULT_CONFIG (.env)
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

import { DEFAULT_CONFIG } from '../config/defaults.js'

/**
 * Core network constants for AutoBot distributed infrastructure
 * CRITICAL: All values read from DEFAULT_CONFIG (which reads from .env)
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
  // Main machine (WSL) - reads from VITE_BACKEND_HOST
  MAIN_MACHINE_IP: DEFAULT_CONFIG.network.backend.host as string,

  // VM Infrastructure IPs - read from VITE_*_HOST environment variables
  FRONTEND_VM_IP: DEFAULT_CONFIG.network.frontend.host as string,
  NPU_WORKER_VM_IP: DEFAULT_CONFIG.network.npu_worker.host as string,
  REDIS_VM_IP: DEFAULT_CONFIG.network.redis.host as string,
  AI_STACK_VM_IP: DEFAULT_CONFIG.network.ai_stack.host as string,
  BROWSER_VM_IP: DEFAULT_CONFIG.network.browser.host as string,

  // Local/Localhost addresses - these are standard and don't need env vars
  LOCALHOST_IP: "127.0.0.1" as const,
  LOCALHOST_NAME: "localhost" as const,

  // Standard ports - read from VITE_*_PORT environment variables
  BACKEND_PORT: parseInt(DEFAULT_CONFIG.network.backend.port as string),
  FRONTEND_PORT: parseInt(DEFAULT_CONFIG.network.frontend.port as string),
  REDIS_PORT: parseInt(DEFAULT_CONFIG.network.redis.port as string),
  OLLAMA_PORT: parseInt(DEFAULT_CONFIG.network.ollama.port as string),
  VNC_PORT: parseInt(DEFAULT_CONFIG.vnc.desktop.port as string),
  VNC_DESKTOP_PORT: parseInt(DEFAULT_CONFIG.vnc.desktop.port as string), // Alias for clarity
  BROWSER_SERVICE_PORT: parseInt(DEFAULT_CONFIG.network.browser.port as string),
  AI_STACK_PORT: parseInt(DEFAULT_CONFIG.network.ai_stack.port as string),
  NPU_WORKER_PORT: parseInt(DEFAULT_CONFIG.network.npu_worker.port as string),

  // Development ports - same as standard ports in current config
  DEV_FRONTEND_PORT: parseInt(DEFAULT_CONFIG.network.frontend.port as string),
  DEV_BACKEND_PORT: parseInt(DEFAULT_CONFIG.network.backend.port as string)
})

/**
 * Pre-built service URLs for common AutoBot services
 * CRITICAL: Built from NetworkConstants which reads from DEFAULT_CONFIG
 * Protocol (http/https) comes from DEFAULT_CONFIG.network.*.protocol
 */
export const ServiceURLs = Object.freeze({
  // Backend API URLs
  BACKEND_API: `${DEFAULT_CONFIG.network.backend.protocol}://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`,
  BACKEND_LOCAL: `${DEFAULT_CONFIG.network.backend.protocol}://${NetworkConstants.LOCALHOST_NAME}:${NetworkConstants.BACKEND_PORT}`,

  // Frontend URLs
  FRONTEND_VM: `${DEFAULT_CONFIG.network.frontend.protocol}://${NetworkConstants.FRONTEND_VM_IP}:${NetworkConstants.FRONTEND_PORT}`,
  FRONTEND_LOCAL: `${DEFAULT_CONFIG.network.frontend.protocol}://${NetworkConstants.LOCALHOST_NAME}:${NetworkConstants.FRONTEND_PORT}`,

  // Redis URLs
  REDIS_VM: `redis://${NetworkConstants.REDIS_VM_IP}:${NetworkConstants.REDIS_PORT}`,
  REDIS_LOCAL: `redis://${NetworkConstants.LOCALHOST_IP}:${NetworkConstants.REDIS_PORT}`,

  // Ollama LLM URLs
  OLLAMA_LOCAL: `${DEFAULT_CONFIG.network.ollama.protocol}://${NetworkConstants.LOCALHOST_NAME}:${NetworkConstants.OLLAMA_PORT}`,
  OLLAMA_MAIN: `${DEFAULT_CONFIG.network.ollama.protocol}://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.OLLAMA_PORT}`,

  // VNC Desktop URLs
  VNC_DESKTOP: `${DEFAULT_CONFIG.vnc.desktop.protocol}://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.VNC_PORT}/vnc.html`,
  VNC_LOCAL: `${DEFAULT_CONFIG.vnc.desktop.protocol}://${NetworkConstants.LOCALHOST_NAME}:${NetworkConstants.VNC_PORT}/vnc.html`,

  // Browser automation service
  BROWSER_SERVICE: `${DEFAULT_CONFIG.network.browser.protocol}://${NetworkConstants.BROWSER_VM_IP}:${NetworkConstants.BROWSER_SERVICE_PORT}`,

  // AI Stack service
  AI_STACK_SERVICE: `${DEFAULT_CONFIG.network.ai_stack.protocol}://${NetworkConstants.AI_STACK_VM_IP}:${NetworkConstants.AI_STACK_PORT}`,

  // NPU Worker service
  NPU_WORKER_SERVICE: `${DEFAULT_CONFIG.network.npu_worker.protocol}://${NetworkConstants.NPU_WORKER_VM_IP}:${NetworkConstants.NPU_WORKER_PORT}`
})

/**
 * Dynamic network configuration based on environment
 */
export class NetworkConfig {
  private _deploymentMode: string
  private _isDevelopment: boolean

  constructor() {
    this._deploymentMode = import.meta.env.VITE_AUTOBOT_DEPLOYMENT_MODE || 'distributed'
    this._isDevelopment = import.meta.env.MODE === 'development'
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
