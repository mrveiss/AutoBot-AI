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
  }
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
  },
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

export default config
