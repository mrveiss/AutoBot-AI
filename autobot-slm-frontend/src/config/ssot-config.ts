// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Single Source of Truth Configuration for SLM Admin
 *
 * Centralized configuration for all infrastructure endpoints and settings.
 * All values support VITE_* environment variable overrides (#3049).
 */

export interface SLMConfig {
  httpProtocol: 'http' | 'https'
  apiBaseUrl: string
  wsProtocol: 'ws' | 'wss'
  wsBaseUrl: string
  vm: {
    main: string
    frontend: string
    npu: string
    redis: string
    ai: string
    browser: string
    slm: string
  }
  port: {
    backend: number
    frontend: number
    slmApi: number
    grafana: number
    prometheus: number
    redis: number
    vnc: number
    ollama: number
    elasticsearch: number
    tlsFrontend: number
    tlsBackend: number
    tlsRedis: number
  }
  hosts: {
    id: string
    name: string
    ip: string
    description: string
  }[]
}

// =============================================================================
// Environment Variable Helpers
// =============================================================================

/**
 * Get string environment variable with fallback.
 * Matches the pattern used in autobot-frontend ssot-config.ts.
 */
function getEnv(key: string, defaultValue: string): string {
  const value = import.meta.env[key]
  if (value === undefined || value === null || value === '') {
    return defaultValue
  }
  return String(value)
}

/**
 * Get numeric environment variable with fallback.
 * Matches the pattern used in autobot-frontend ssot-config.ts.
 */
function getEnvNumber(key: string, defaultValue: number): number {
  const value = import.meta.env[key]
  if (value === undefined || value === null || value === '') {
    return defaultValue
  }
  const parsed = parseInt(String(value), 10)
  return isNaN(parsed) ? defaultValue : parsed
}

// Detect protocol from browser context
const isSecure = typeof window !== 'undefined' && window.location.protocol === 'https:'

// Build WebSocket URL using current host (nginx proxy handles routing)
// This ensures wss:// is used when page is served over https://
function getWsBaseUrl(): string {
  if (typeof window === 'undefined') return 'ws://localhost:8000'
  const wsProtocol = isSecure ? 'wss:' : 'ws:'
  // Use current host (nginx) - nginx proxies /api/ws to backend
  return `${wsProtocol}//${window.location.host}`
}

// =============================================================================
// Configuration Builder
// =============================================================================

// VM IP addresses — env var names match autobot-frontend convention (#3049)
const vm: SLMConfig['vm'] = {
  main: getEnv('VITE_BACKEND_HOST', ''),
  frontend: getEnv('VITE_FRONTEND_HOST', ''),
  npu: getEnv('VITE_NPU_WORKER_HOST', ''),
  redis: getEnv('VITE_REDIS_HOST', ''),
  ai: getEnv('VITE_AI_STACK_HOST', ''),
  browser: getEnv('VITE_BROWSER_HOST', ''),
  slm: getEnv('VITE_SLM_HOST', ''),
}

const config: SLMConfig = {
  httpProtocol: isSecure ? 'https' : 'http',
  // Use relative path - nginx proxies /api/ to backend
  apiBaseUrl: import.meta.env.VITE_API_URL || '',
  wsProtocol: isSecure ? 'wss' : 'ws',
  // Use current host - nginx proxies WebSocket connections
  wsBaseUrl: import.meta.env.VITE_WS_URL || getWsBaseUrl(),
  vm,
  port: {
    backend: getEnvNumber('VITE_BACKEND_PORT', 8001),
    frontend: getEnvNumber('VITE_FRONTEND_PORT', 5173),
    slmApi: getEnvNumber('VITE_SLM_PORT', 8000),
    grafana: getEnvNumber('VITE_GRAFANA_PORT', 3000),
    prometheus: getEnvNumber('VITE_PROMETHEUS_PORT', 9090),
    redis: getEnvNumber('VITE_REDIS_PORT', 6379),
    vnc: getEnvNumber('VITE_DESKTOP_VNC_PORT', 6080), // DORMANT: VNC replaced by screenshot panel (#1130); see #5136
    ollama: getEnvNumber('VITE_OLLAMA_PORT', 11434),
    elasticsearch: getEnvNumber('VITE_ELASTICSEARCH_PORT', 9200),
    tlsFrontend: getEnvNumber('VITE_TLS_FRONTEND_PORT', 443),
    tlsBackend: getEnvNumber('VITE_TLS_BACKEND_PORT', 8443),
    tlsRedis: getEnvNumber('VITE_TLS_REDIS_PORT', 6380),
  },
  // Derive IPs from vm object — single source, no duplication (#3049)
  hosts: [
    { id: 'main', name: 'Main Server', ip: vm.main, description: 'WSL Backend Server' },
    { id: 'frontend', name: 'Frontend VM', ip: vm.frontend, description: 'Vue.js Frontend' },
    { id: 'npu', name: 'NPU VM', ip: vm.npu, description: 'NPU Acceleration' },
    { id: 'redis', name: 'Redis VM', ip: vm.redis, description: 'Redis Stack' },
    { id: 'ai', name: 'AI VM', ip: vm.ai, description: 'AI Processing' },
    { id: 'browser', name: 'Browser VM', ip: vm.browser, description: 'Playwright Automation' },
    { id: 'slm', name: 'SLM Server', ip: vm.slm, description: 'Service Lifecycle Manager' },
  ],
}

export function getConfig(): SLMConfig {
  return config
}

/**
 * Get the SLM API base path (#2829).
 *
 * Standalone SLM (separate host): VITE_API_URL is empty -> returns '/api'
 * Co-located with user frontend:  VITE_API_URL='/slm'  -> returns '/slm/api'
 *
 * All SLM composables should use this instead of hardcoding '/api'.
 */
export function getSlmApiBase(): string {
  const prefix = config.apiBaseUrl // '' or '/slm'
  return `${prefix}/api`
}

/**
 * Get Grafana URL for embedding dashboards
 * Uses the SLM Grafana via nginx proxy at /grafana/
 * Dashboards are provisioned from AutoBot/config/grafana/dashboards/
 */
export function getGrafanaUrl(): string {
  // Use relative path for nginx-proxied Grafana
  return '/grafana'
}

/**
 * Get Prometheus URL for direct queries
 * Uses the SLM Prometheus via nginx proxy at /prometheus/
 */
export function getPrometheusUrl(): string {
  // Use relative path for nginx-proxied Prometheus
  return '/prometheus'
}

/**
 * Get the main AutoBot backend URL for monitoring API
 * Uses nginx proxy at /autobot-api/ to avoid CORS issues
 */
export function getBackendUrl(): string {
  // Use relative path for nginx-proxied AutoBot backend
  return '/autobot-api'
}

/**
 * Get all configured hosts for terminal/SSH access
 * Related to Issue #729 - SSOT for hardcoded IPs
 */
export function getHosts(): SLMConfig['hosts'] {
  return config.hosts
}

/**
 * Get VNC-enabled hosts with port configuration.
 * Returns empty -- VNC hosts are discovered dynamically via the SLM API
 * from nodes that have the 'vnc' role active (#2900).
 * DORMANT: VNC browser path replaced by screenshot panel (#1130). Preserved for #5136 re-integration.
 */
export function getVNCHosts(): Array<{ id: string; name: string; host: string; port: number; description: string }> {
  return []
}

/**
 * Get known hosts for log forwarding
 * Related to Issue #729 - SSOT for infrastructure hosts
 */
export function getKnownHosts(): Array<{ hostname: string; ip: string }> {
  return [
    { hostname: 'autobot-main', ip: config.vm.main },
    { hostname: 'autobot-frontend', ip: config.vm.frontend },
    { hostname: 'autobot-npu', ip: config.vm.npu },
    { hostname: 'autobot-redis', ip: config.vm.redis },
    { hostname: 'autobot-ai', ip: config.vm.ai },
    { hostname: 'autobot-browser', ip: config.vm.browser },
  ]
}

export default config
