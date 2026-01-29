// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Single Source of Truth Configuration for SLM Admin
 *
 * Centralized configuration for all infrastructure endpoints and settings.
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
  }
  hosts: {
    id: string
    name: string
    ip: string
    description: string
  }[]
}

const config: SLMConfig = {
  httpProtocol: 'http',
  apiBaseUrl: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  wsProtocol: 'ws',
  wsBaseUrl: import.meta.env.VITE_WS_URL || 'ws://localhost:8000',
  vm: {
    main: '172.16.168.20',
    frontend: '172.16.168.21',
    npu: '172.16.168.22',
    redis: '172.16.168.23',
    ai: '172.16.168.24',
    browser: '172.16.168.25',
    slm: '172.16.168.19',
  },
  port: {
    backend: 8001,
    frontend: 5173,
    slmApi: 8000,
    grafana: 3000,
    prometheus: 9090,
    redis: 6379,
    vnc: 6080,
  },
  hosts: [
    { id: 'main', name: 'Main Server', ip: '172.16.168.20', description: 'WSL Backend Server' },
    { id: 'frontend', name: 'Frontend VM', ip: '172.16.168.21', description: 'Vue.js Frontend' },
    { id: 'npu', name: 'NPU VM', ip: '172.16.168.22', description: 'NPU Acceleration' },
    { id: 'redis', name: 'Redis VM', ip: '172.16.168.23', description: 'Redis Stack' },
    { id: 'ai', name: 'AI VM', ip: '172.16.168.24', description: 'AI Processing' },
    { id: 'browser', name: 'Browser VM', ip: '172.16.168.25', description: 'Playwright Automation' },
    { id: 'slm', name: 'SLM Server', ip: '172.16.168.19', description: 'Service Lifecycle Manager' },
  ],
}

export function getConfig(): SLMConfig {
  return config
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
 * Get VNC-enabled hosts with port configuration
 * Related to Issue #729 - SSOT for VNC endpoints
 */
export function getVNCHosts(): Array<{ id: string; name: string; host: string; port: number; description: string }> {
  return [
    { id: 'main', name: 'Main WSL', host: config.vm.main, port: config.port.vnc, description: 'Main backend server VNC' },
  ]
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
