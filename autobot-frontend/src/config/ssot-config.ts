// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * SSOT Configuration Loader for TypeScript
 * =========================================
 *
 * Single Source of Truth - reads from Vite environment variables.
 *
 * This module provides typed configuration access across the entire frontend.
 * All configuration values are defined in the master .env file and mapped
 * to VITE_* prefixed variables for Vite to expose them.
 *
 * Usage:
 *   import { getConfig, config } from '@/config/ssot-config';
 *
 *   // Access VM IPs
 *   const redisIp = config.vm.redis;
 *   const backendIp = config.vm.main;
 *
 *   // Access ports
 *   const backendPort = config.port.backend;
 *
 *   // Access computed URLs
 *   const backendUrl = config.backendUrl;
 *   const websocketUrl = config.websocketUrl;
 *
 *   // Access timeouts
 *   const apiTimeout = config.timeout.api;
 *
 * Issue: #601 - SSOT Phase 1: Foundation
 * Related: #599 - SSOT Configuration System Epic
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

// =============================================================================
// Type Definitions
// =============================================================================

/**
 * VM IP address configuration.
 * Supports the 6-VM distributed architecture.
 */
export interface VMConfig {
  /** Main machine (WSL) - Backend API + VNC Desktop */
  main: string;
  /** VM1 Frontend - Web interface */
  frontend: string;
  /** VM2 NPU Worker - Hardware AI acceleration */
  npu: string;
  /** VM3 Redis - Data layer */
  redis: string;
  /** VM4 AI Stack - AI processing */
  aistack: string;
  /** VM5 Browser - Web automation */
  browser: string;
  /** Ollama host (typically localhost) */
  ollama: string;
  /** SLM Backend (Service Lifecycle Manager) - Issue #725 */
  slm: string;
}

/**
 * Service port configuration.
 */
export interface PortConfig {
  backend: number;
  frontend: number;
  redis: number;
  ollama: number;
  vnc: number;
  browser: number;
  aistack: number;
  npu: number;
  prometheus: number;
  grafana: number;
  /** SLM Backend port - Issue #725 */
  slm: number;
  /** SLM Admin frontend port - Issue #729 */
  slmAdmin: number;
}

/**
 * LLM model configuration.
 */
export interface LLMConfig {
  defaultModel: string;
  embeddingModel: string;
  provider: string;
  timeout: number;
}

/**
 * Timeout configuration (in milliseconds).
 */
export interface TimeoutConfig {
  /** API request timeout (ms) */
  api: number;
  /** Knowledge/LLM operations timeout (ms) */
  knowledge: number;
  /** API retry attempts */
  retryAttempts: number;
  /** Delay between retries (ms) */
  retryDelay: number;
  /** WebSocket timeout (ms) */
  websocket: number;
}

/**
 * VNC configuration for desktop streaming.
 * DORMANT: VNC browser path replaced by screenshot panel (#1130). Preserved for #5136 re-integration.
 */
export interface VNCConfig {
  desktop: {
    host: string;
    port: number;
    password: string;
  };
  terminal: {
    host: string;
    port: number;
    password: string;
  };
  playwright: {
    host: string;
    port: number;
    password: string;
  };
}

/**
 * Feature flags configuration.
 */
export interface FeatureConfig {
  debug: boolean;
  rum: boolean;
  cacheDisabled: boolean;
}

// =============================================================================
// Permission System v2 Types - Claude Code Style
// Issue: Permission System v2 - Claude Code Style
// =============================================================================

/**
 * Permission modes matching backend PermissionMode enum.
 */
export type PermissionMode =
  | 'default'
  | 'acceptEdits'
  | 'plan'
  | 'dontAsk'
  | 'bypassPermissions';

/**
 * Permission actions matching backend PermissionAction enum.
 */
export type PermissionAction = 'allow' | 'ask' | 'deny';

/**
 * Permission rule interface.
 */
export interface PermissionRule {
  tool: string;
  pattern: string;
  action: PermissionAction;
  description: string;
}

/**
 * Approval record interface for project memory.
 */
export interface ApprovalRecord {
  pattern: string;
  tool: string;
  risk_level: string;
  user_id: string;
  created_at: number;
  original_command: string;
  comment?: string;
}

/**
 * Permission system status interface.
 */
export interface PermissionStatus {
  enabled: boolean;
  mode: PermissionMode;
  approval_memory_enabled: boolean;
  approval_memory_ttl_days: number;
  rules_file: string;
  rules_count: {
    allow: number;
    ask: number;
    deny: number;
    total: number;
  };
}

/**
 * Permission configuration interface.
 */
export interface PermissionConfig {
  /** Whether permission system v2 is enabled */
  enabled: boolean;
  /** Current permission mode */
  mode: PermissionMode;
  /** Whether approval memory is enabled */
  approvalMemoryEnabled: boolean;
  /** TTL for approval memory in seconds */
  approvalMemoryTtl: number;
  /** Path to rules YAML file */
  rulesFile: string;
  /** Admin-only modes that require elevated privileges */
  adminOnlyModes: PermissionMode[];
}

/**
 * Match result from permission checker.
 */
export type MatchResult = 'allow' | 'ask' | 'deny' | 'default';

/**
 * Complete AutoBot configuration.
 */
export interface AutoBotConfig {
  // Sub-configurations
  vm: VMConfig;
  port: PortConfig;
  llm: LLMConfig;
  timeout: TimeoutConfig;
  vnc: VNCConfig;
  feature: FeatureConfig;

  // Top-level settings
  deploymentMode: string;
  environment: string;
  debug: boolean;
  httpProtocol: string;

  // Computed URLs (readonly getters)
  readonly backendUrl: string;
  readonly frontendUrl: string;
  readonly redisUrl: string;
  readonly ollamaUrl: string;
  readonly websocketUrl: string;
  readonly aistackUrl: string;
  readonly npuWorkerUrl: string;
  readonly browserServiceUrl: string;
  readonly vncUrl: string;
  /** SLM Backend URL - Issue #725 */
  readonly slmUrl: string;
  /** SLM Admin frontend URL - Issue #729 */
  readonly slmAdminUrl: string;
}

// =============================================================================
// Service Discovery Types (Issue #760 Phase 3)
// =============================================================================

/**
 * Discovered service information from SLM.
 */
export interface DiscoveredService {
  service_name: string;
  url: string;
  host: string;
  port?: number;
  protocol: string;
  healthy: boolean;
  node_id: string;
}

/**
 * Cache entry for discovered services.
 */
interface DiscoveryCacheEntry {
  data: DiscoveredService;
  expiresAt: number;
}

/** Service discovery cache (module-level) */
const discoveryCache = new Map<string, DiscoveryCacheEntry>();
const DISCOVERY_CACHE_TTL_MS = 60000; // 60 seconds

// Lazy-import logger to avoid circular dependencies
let _discoveryLogger: ReturnType<typeof import('@/utils/debugUtils').createLogger> | null = null;
async function getDiscoveryLogger() {
  if (!_discoveryLogger) {
    const { createLogger } = await import('@/utils/debugUtils');
    _discoveryLogger = createLogger('ServiceDiscovery');
  }
  return _discoveryLogger;
}

// =============================================================================
// Environment Variable Helpers
// =============================================================================

/**
 * Get string environment variable with fallback.
 */
function getEnv(key: string, defaultValue: string): string {
  const value = import.meta.env[key];
  if (value === undefined || value === null || value === '') {
    return defaultValue;
  }
  return String(value);
}

/**
 * Get numeric environment variable with fallback.
 */
function getEnvNumber(key: string, defaultValue: number): number {
  const value = import.meta.env[key];
  if (value === undefined || value === null || value === '') {
    return defaultValue;
  }
  const parsed = parseInt(String(value), 10);
  return isNaN(parsed) ? defaultValue : parsed;
}

/**
 * Get boolean environment variable with fallback.
 */
function getEnvBoolean(key: string, defaultValue: boolean): boolean {
  const value = import.meta.env[key];
  if (value === undefined || value === null || value === '') {
    return defaultValue;
  }
  const strValue = String(value).toLowerCase();
  return strValue === 'true' || strValue === '1' || strValue === 'yes';
}

// =============================================================================
// Runtime Protocol Helper
// =============================================================================

/**
 * Detect the HTTP protocol at runtime from window.location.
 * Falls back to VITE_HTTP_PROTOCOL for SSR / non-browser contexts.
 * Exported so callers outside ssot-config can reuse the same detection logic
 * without importing the full config singleton.
 */
export function runtimeHttpProto(): string {
  if (typeof window !== 'undefined' && window.location?.protocol) {
    return window.location.protocol === 'https:' ? 'https' : 'http';
  }
  return getEnv('VITE_HTTP_PROTOCOL', 'http');
}

// =============================================================================
// Configuration Builder
// =============================================================================

/**
 * Build the complete configuration from environment variables.
 * This is called once on first access.
 */
function buildConfig(): AutoBotConfig {
  // VM IP addresses — fall back to window.location.hostname so dev builds
  // without VITE_*_HOST vars never produce malformed ws://:PORT URLs (#5627, #5646)
  const mainHost = getEnv('VITE_BACKEND_HOST', '') || (typeof window !== 'undefined' ? window.location.hostname : 'localhost');
  const resolveHost = (envVar: string) => getEnv(envVar, '') || mainHost;

  const vm: VMConfig = {
    main:     mainHost,
    frontend: resolveHost('VITE_FRONTEND_HOST'),
    npu:      resolveHost('VITE_NPU_WORKER_HOST'),
    redis:    resolveHost('VITE_REDIS_HOST'),
    aistack:  resolveHost('VITE_AI_STACK_HOST'),
    browser:  resolveHost('VITE_BROWSER_HOST'),
    ollama:   resolveHost('VITE_OLLAMA_HOST'),
    slm:      getEnv('VITE_SLM_HOST', ''),  // intentionally empty — slmUrl guards this
  };

  // Service ports
  const port: PortConfig = {
    backend: getEnvNumber('VITE_BACKEND_PORT', 8001),
    frontend: getEnvNumber('VITE_FRONTEND_PORT', 5173),
    redis: getEnvNumber('VITE_REDIS_PORT', 6379),
    ollama: getEnvNumber('VITE_OLLAMA_PORT', 11434),
    vnc: getEnvNumber('VITE_DESKTOP_VNC_PORT', 6080),
    browser: getEnvNumber('VITE_BROWSER_PORT', 9001),
    aistack: getEnvNumber('VITE_AI_STACK_PORT', 8080),
    npu: getEnvNumber('VITE_NPU_WORKER_PORT', 8081),
    prometheus: getEnvNumber('VITE_PROMETHEUS_PORT', 9090),
    grafana: getEnvNumber('VITE_GRAFANA_PORT', 3000),
    slm: getEnvNumber('VITE_SLM_PORT', 8000),
    slmAdmin: getEnvNumber('VITE_SLM_ADMIN_PORT', 5174),
  };

  // LLM configuration
  const llm: LLMConfig = {
    defaultModel: getEnv('VITE_LLM_DEFAULT_MODEL', 'qwen3.5:9b'),  // Quality tier (#2553)
    embeddingModel: getEnv('VITE_LLM_EMBEDDING_MODEL', 'nomic-embed-text:latest'),
    provider: getEnv('VITE_LLM_PROVIDER', 'ollama'),
    timeout: getEnvNumber('VITE_LLM_TIMEOUT', 30000),
  };

  // Timeout configuration (all in milliseconds)
  const timeout: TimeoutConfig = {
    api: getEnvNumber('VITE_API_TIMEOUT', 60000),
    knowledge: getEnvNumber('VITE_KNOWLEDGE_TIMEOUT', 300000),
    retryAttempts: getEnvNumber('VITE_API_RETRY_ATTEMPTS', 3),
    retryDelay: getEnvNumber('VITE_API_RETRY_DELAY', 1000),
    websocket: getEnvNumber('VITE_WEBSOCKET_TIMEOUT', 30000),
  };

  // DORMANT: VNC browser path replaced by screenshot panel (#1130). Preserved for #5136 re-integration.
  // VNC configuration
  const vnc: VNCConfig = {
    desktop: {
      host: getEnv('VITE_DESKTOP_VNC_HOST', vm.main),
      port: getEnvNumber('VITE_DESKTOP_VNC_PORT', 6080),
      password: getEnv('VITE_DESKTOP_VNC_PASSWORD', 'autobot'),
    },
    terminal: {
      host: getEnv('VITE_TERMINAL_VNC_HOST', vm.main),
      port: getEnvNumber('VITE_TERMINAL_VNC_PORT', 6080),
      password: getEnv('VITE_TERMINAL_VNC_PASSWORD', 'autobot'),
    },
    playwright: {
      host: getEnv('VITE_PLAYWRIGHT_VNC_HOST', vm.browser),
      port: getEnvNumber('VITE_PLAYWRIGHT_VNC_PORT', 6081),
      password: getEnv('VITE_PLAYWRIGHT_VNC_PASSWORD', 'playwright'),
    },
  };

  // Feature flags
  const feature: FeatureConfig = {
    debug: getEnvBoolean('VITE_ENABLE_DEBUG', false),
    rum: getEnvBoolean('VITE_ENABLE_RUM', true),
    cacheDisabled: getEnvBoolean('VITE_DISABLE_CACHE', false),
  };

  // Top-level settings
  const deploymentMode = getEnv('VITE_DEPLOYMENT_MODE', 'distributed');
  const environment = getEnv('VITE_ENVIRONMENT', 'development');
  const debug = getEnvBoolean('VITE_DEBUG', false);
  const httpProtocol = getEnv('VITE_HTTP_PROTOCOL', 'http');

  // Build the config object with computed URL getters
  const configObj: AutoBotConfig = {
    vm,
    port,
    llm,
    timeout,
    vnc,
    feature,
    deploymentMode,
    environment,
    debug,
    httpProtocol,

    // #6795: detect protocol at runtime from window.location instead of
    // build-time VITE_HTTP_PROTOCOL (which defaults to 'http' and produces
    // mixed-content blocks on HTTPS deploys). Sister fix to #6642 (websocketUrl);
    // applied uniformly to every browser-facing URL builder.
    get backendUrl(): string {
      return `${runtimeHttpProto()}://${vm.main}:${port.backend}`;
    },

    get frontendUrl(): string {
      return `${runtimeHttpProto()}://${vm.frontend}:${port.frontend}`;
    },

    get redisUrl(): string {
      return `redis://${vm.redis}:${port.redis}`;
    },

    get ollamaUrl(): string {
      return `${runtimeHttpProto()}://${vm.ollama}:${port.ollama}`;
    },

    get websocketUrl(): string {
      if (runtimeHttpProto() === 'https') {
        const host =
          typeof window !== 'undefined' ? window.location.host : vm.main;
        return `wss://${host}/api/ws`;
      }
      return `ws://${vm.main}:${port.backend}/api/ws`;
    },

    get aistackUrl(): string {
      return `${runtimeHttpProto()}://${vm.aistack}:${port.aistack}`;
    },

    get npuWorkerUrl(): string {
      return `${runtimeHttpProto()}://${vm.npu}:${port.npu}`;
    },

    get browserServiceUrl(): string {
      return `${runtimeHttpProto()}://${vm.browser}:${port.browser}`;
    },

    // DORMANT: VNC browser path replaced by screenshot panel (#1130). Preserved for #5136 re-integration.
    get vncUrl(): string {
      return `${runtimeHttpProto()}://${vm.main}:${port.vnc}/vnc.html`;
    },

    get slmUrl(): string {
      // Issue #1875: When vm.slm is empty, use relative /slm path
      // for Docker/nginx deployments where SLM is proxied
      if (!vm.slm) return '/slm';
      return `${runtimeHttpProto()}://${vm.slm}:${port.slm}`;
    },

    get slmAdminUrl(): string {
      // Issue #729: SLM Admin is behind nginx on port 443
      // Nginx proxies / -> slm-admin:5174, /api/ -> slm-server:8000
      // Issue #1875: When vm.slm is empty, use relative /slm path
      if (!vm.slm) return '/slm';
      return `${runtimeHttpProto()}://${vm.slm}`;
    },
  };

  return configObj;
}

// =============================================================================
// Singleton Configuration
// =============================================================================

/** Cached configuration instance */
let _config: AutoBotConfig | null = null;

/**
 * Get the singleton configuration instance.
 *
 * Configuration is loaded from Vite environment variables on first access.
 * Subsequent calls return the cached instance.
 *
 * @returns AutoBotConfig instance
 */
export function getConfig(): AutoBotConfig {
  if (_config === null) {
    _config = buildConfig();
  }
  return _config;
}

/**
 * Force reload of configuration.
 *
 * Clears the cached config and creates a new instance.
 * Use this when environment has changed dynamically.
 *
 * @returns Fresh AutoBotConfig instance
 */
export function reloadConfig(): AutoBotConfig {
  _config = null;
  return getConfig();
}

/**
 * Get a service URL by name.
 *
 * @param serviceName - Name of service (backend, frontend, redis, etc.)
 * @returns Service URL or undefined if not found
 */
export function getServiceUrl(serviceName: string): string | undefined {
  const cfg = getConfig();
  const urlMap: Record<string, string> = {
    backend: cfg.backendUrl,
    frontend: cfg.frontendUrl,
    redis: cfg.redisUrl,
    ollama: cfg.ollamaUrl,
    websocket: cfg.websocketUrl,
    aistack: cfg.aistackUrl,
    ai_stack: cfg.aistackUrl,
    npu: cfg.npuWorkerUrl,
    npu_worker: cfg.npuWorkerUrl,
    browser: cfg.browserServiceUrl,
    vnc: cfg.vncUrl,
    slm: cfg.slmUrl,
    slm_admin: cfg.slmAdminUrl,
    slmadmin: cfg.slmAdminUrl,
  };
  return urlMap[serviceName.toLowerCase()];
}

/**
 * Get a VM IP address by name.
 *
 * @param vmName - Name of VM (main, frontend, redis, etc.)
 * @returns IP address or undefined if not found
 */
export function getVmIp(vmName: string): string | undefined {
  const cfg = getConfig();
  const vmMap: Record<string, string> = {
    main: cfg.vm.main,
    frontend: cfg.vm.frontend,
    npu: cfg.vm.npu,
    npu_worker: cfg.vm.npu,
    redis: cfg.vm.redis,
    aistack: cfg.vm.aistack,
    ai_stack: cfg.vm.aistack,
    browser: cfg.vm.browser,
    ollama: cfg.vm.ollama,
    slm: cfg.vm.slm,
  };
  return vmMap[vmName.toLowerCase()];
}

// =============================================================================
// Default Export
// =============================================================================

/**
 * Lazy-loaded configuration singleton.
 *
 * Usage:
 *   import config from '@/config/ssot-config';
 *   console.log(config.backendUrl);
 */
const config = getConfig();
export default config;

// =============================================================================
// Backward Compatibility Exports
// =============================================================================

/**
 * Get backend URL (backward compatibility).
 * Returns empty string when VITE_BACKEND_HOST is not explicitly set,
 * enabling proxy mode where nginx at the frontend VM routes API calls.
 */
export function getBackendUrl(): string {
  // Explicit base URL override takes highest priority
  const explicitBaseUrl = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL;
  if (explicitBaseUrl) return explicitBaseUrl;
  // If no explicit backend host, return '' for proxy mode via nginx
  const explicitHost = import.meta.env.VITE_BACKEND_HOST;
  if (!explicitHost) return '';
  return getConfig().backendUrl;
}


/**
 * Get the API base path for the autobot backend.
 * Returns '/api' by default. Override with VITE_API_BASE_PATH if needed.
 *
 * All frontend code should call this instead of hardcoding '/api'.
 * Consistent with getSlmApiBase() pattern in autobot-slm-frontend.
 */
export function getApiBase(): string {
  return import.meta.env.VITE_API_BASE_PATH || '/api'
}

/**
 * Get WebSocket URL (backward compatibility).
 */
export function getWebsocketUrl(): string {
  return getConfig().websocketUrl;
}

/**
 * Get Backend WebSocket URL base (without /ws suffix).
 * Used by SSHTerminal and other WebSocket-based components that need
 * to build their own WebSocket paths (e.g., /api/terminal/ws/ssh/{host_id}).
 *
 * Note: This differs from getWebsocketUrl() which includes /ws suffix
 * for the main chat WebSocket endpoint.
 * Returns a window.location-relative WS URL when in proxy mode.
 */
export function getBackendWsUrl(): string {
  const backendUrl = getBackendUrl();
  if (!backendUrl) {
    // Proxy mode: derive WS URL from current page location
    if (typeof window !== 'undefined') {
      const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${wsProto}//${window.location.host}`;
    }
    return '';
  }
  return backendUrl.replace(/^http/, 'ws');
}

/**
 * Get API timeout in milliseconds (backward compatibility).
 */
export function getApiTimeout(): number {
  return getConfig().timeout.api;
}

/**
 * Get SLM Backend URL (Issue #725).
 * Returns relative '/slm' when VITE_SLM_HOST is not set,
 * enabling proxy mode where nginx routes SLM API calls.
 * Bare-metal deployments set VITE_SLM_HOST to the SLM IP.
 */
export function getSLMUrl(): string {
  return getConfig().slmUrl;
}

/**
 * Get SLM Admin frontend URL (Issue #729).
 */
export function getSLMAdminUrl(): string {
  return getConfig().slmAdminUrl;
}

// =============================================================================
// Service Discovery Functions (Issue #760 Phase 3)
// =============================================================================

/**
 * Discover a service by name with fallback chain.
 *
 * Fallback order:
 * 1. Cache (60s TTL)
 * 2. SLM /api/discover/{serviceName}
 * 3. Environment-based getServiceUrl()
 * 4. Error
 *
 * @param serviceName - Service identifier (e.g., 'redis', 'ollama')
 * @param authToken - JWT token for SLM authentication
 * @returns Service URL
 * @throws Error if service not configured anywhere
 */
export async function discoverService(
  serviceName: string,
  authToken: string
): Promise<string> {
  const logger = await getDiscoveryLogger();

  // 1. Check cache
  const cached = discoveryCache.get(serviceName);
  if (cached && Date.now() < cached.expiresAt) {
    return cached.data.url;
  }

  // 2. Try SLM
  try {
    const slmUrl = getConfig().slmUrl;
    const response = await fetch(`${slmUrl}/api/discover/${serviceName}`, {
      headers: {
        Authorization: `Bearer ${authToken}`,
        'Content-Type': 'application/json',
      },
    });

    if (response.ok) {
      const data: DiscoveredService = await response.json();
      discoveryCache.set(serviceName, {
        data,
        expiresAt: Date.now() + DISCOVERY_CACHE_TTL_MS,
      });
      return data.url;
    }

    if (response.status !== 404) {
      logger.warn(`SLM discovery failed for ${serviceName}: ${response.status}`);
    }
  } catch (err) {
    logger.warn(`SLM discovery error for ${serviceName}:`, err);
  }

  // 3. Env var fallback (via existing getServiceUrl)
  const envUrl = getServiceUrl(serviceName);
  if (envUrl) {
    logger.info(`Service ${serviceName} discovered via env fallback`);
    return envUrl;
  }

  // 4. Error
  throw new Error(`Service '${serviceName}' not configured in SLM or environment`);
}

/**
 * Clear the service discovery cache.
 * Useful when services are known to have changed.
 */
export function clearDiscoveryCache(): void {
  discoveryCache.clear();
}
