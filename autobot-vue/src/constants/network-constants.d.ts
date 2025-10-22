/**
 * TypeScript declarations for network-constants.js
 */

/**
 * Core network constants for AutoBot distributed infrastructure
 */
export interface INetworkConstants {
  readonly MAIN_MACHINE_IP: string
  readonly FRONTEND_VM_IP: string
  readonly NPU_WORKER_VM_IP: string
  readonly REDIS_VM_IP: string
  readonly AI_STACK_VM_IP: string
  readonly BROWSER_VM_IP: string
  readonly LOCALHOST_IP: string
  readonly LOCALHOST_NAME: string
  readonly BACKEND_PORT: number
  readonly FRONTEND_PORT: number
  readonly REDIS_PORT: number
  readonly OLLAMA_PORT: number
  readonly VNC_PORT: number
  readonly VNC_DESKTOP_PORT: number
  readonly BROWSER_SERVICE_PORT: number
  readonly AI_STACK_PORT: number
  readonly NPU_WORKER_PORT: number
  readonly DEV_FRONTEND_PORT: number
  readonly DEV_BACKEND_PORT: number
}

/**
 * Pre-built service URLs for common AutoBot services
 */
export interface IServiceURLs {
  readonly BACKEND_API: string
  readonly BACKEND_LOCAL: string
  readonly FRONTEND_VM: string
  readonly FRONTEND_LOCAL: string
  readonly REDIS_VM: string
  readonly REDIS_LOCAL: string
  readonly OLLAMA_LOCAL: string
  readonly OLLAMA_MAIN: string
  readonly VNC_DESKTOP: string
  readonly VNC_LOCAL: string
  readonly BROWSER_SERVICE: string
  readonly AI_STACK_SERVICE: string
  readonly NPU_WORKER_SERVICE: string
}

/**
 * Redis database assignments
 */
export interface IDatabaseConstants {
  readonly MAIN_DB: number
  readonly KNOWLEDGE_DB: number
  readonly CACHE_DB: number
  readonly VECTORS_DB: number
  readonly SESSIONS_DB: number
  readonly METRICS_DB: number
  readonly LOGS_DB: number
  readonly CONFIG_DB: number
  readonly WORKFLOWS_DB: number
  readonly TEMP_DB: number
  readonly MONITORING_DB: number
  readonly RATE_LIMITING_DB: number
}

/**
 * Dynamic network configuration
 */
export class NetworkConfig {
  constructor()
  get backendUrl(): string
  get frontendUrl(): string
  get redisUrl(): string
  get ollamaUrl(): string
  getServiceUrl(serviceName: string): string | null
  getVmIp(vmName: string): string | null
}

export const NetworkConstants: INetworkConstants
export const ServiceURLs: IServiceURLs
export const DatabaseConstants: IDatabaseConstants
export const networkConfig: NetworkConfig

// Legacy compatibility exports
export const BACKEND_URL: string
export const FRONTEND_URL: string
export const REDIS_HOST: string
export const MAIN_MACHINE_IP: string
export const LOCALHOST_IP: string
