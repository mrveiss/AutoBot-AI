/**
 * TypeScript declarations for defaults.js
 * Issue #172: Added to support network.ts consolidation
 */

export interface NetworkServiceConfig {
  host: string
  port: string
  protocol: string
}

export interface VNCConfig {
  port: string
  protocol: string
}

export interface DefaultConfig {
  network: {
    backend: NetworkServiceConfig
    frontend: NetworkServiceConfig
    npu_worker: NetworkServiceConfig
    redis: NetworkServiceConfig
    ai_stack: NetworkServiceConfig
    browser: NetworkServiceConfig
    ollama: NetworkServiceConfig
  }
  vnc: {
    desktop: VNCConfig
  }
}

export const DEFAULT_CONFIG: DefaultConfig
