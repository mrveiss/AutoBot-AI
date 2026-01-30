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
// Configuration Builder
// =============================================================================

/**
 * Build the complete configuration from environment variables.
 * This is called once on first access.
 */
function buildConfig(): AutoBotConfig {
  // VM IP addresses
  const vm: VMConfig = {
    main: getEnv('VITE_BACKEND_HOST', '172.16.168.20'),
    frontend: getEnv('VITE_FRONTEND_HOST', '172.16.168.21'),
    npu: getEnv('VITE_NPU_WORKER_HOST', '172.16.168.22'),
    redis: getEnv('VITE_REDIS_HOST', '172.16.168.23'),
    aistack: getEnv('VITE_AI_STACK_HOST', '172.16.168.24'),
    browser: getEnv('VITE_BROWSER_HOST', '172.16.168.25'),
    ollama: getEnv('VITE_OLLAMA_HOST', '127.0.0.1'),
    slm: getEnv('VITE_SLM_HOST', '172.16.168.19'),
  };

  // Service ports
  const port: PortConfig = {
    backend: getEnvNumber('VITE_BACKEND_PORT', 8001),
    frontend: getEnvNumber('VITE_FRONTEND_PORT', 5173),
    redis: getEnvNumber('VITE_REDIS_PORT', 6379),
    ollama: getEnvNumber('VITE_OLLAMA_PORT', 11434),
    vnc: getEnvNumber('VITE_DESKTOP_VNC_PORT', 6080),
    browser: getEnvNumber('VITE_BROWSER_PORT', 3000),
    aistack: getEnvNumber('VITE_AI_STACK_PORT', 8080),
    npu: getEnvNumber('VITE_NPU_WORKER_PORT', 8081),
    prometheus: getEnvNumber('VITE_PROMETHEUS_PORT', 9090),
    grafana: getEnvNumber('VITE_GRAFANA_PORT', 3000),
    slm: getEnvNumber('VITE_SLM_PORT', 8000),
  };

  // LLM configuration
  const llm: LLMConfig = {
    defaultModel: getEnv('VITE_LLM_DEFAULT_MODEL', 'mistral:7b-instruct'),
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

    // Computed URLs as getters
    get backendUrl(): string {
      return `${httpProtocol}://${vm.main}:${port.backend}`;
    },

    get frontendUrl(): string {
      return `${httpProtocol}://${vm.frontend}:${port.frontend}`;
    },

    get redisUrl(): string {
      return `redis://${vm.redis}:${port.redis}`;
    },

    get ollamaUrl(): string {
      return `${httpProtocol}://${vm.ollama}:${port.ollama}`;
    },

    get websocketUrl(): string {
      const wsProtocol = httpProtocol === 'https' ? 'wss' : 'ws';
      return `${wsProtocol}://${vm.main}:${port.backend}/ws`;
    },

    get aistackUrl(): string {
      return `${httpProtocol}://${vm.aistack}:${port.aistack}`;
    },

    get npuWorkerUrl(): string {
      return `${httpProtocol}://${vm.npu}:${port.npu}`;
    },

    get browserServiceUrl(): string {
      return `${httpProtocol}://${vm.browser}:${port.browser}`;
    },

    get vncUrl(): string {
      return `${httpProtocol}://${vm.main}:${port.vnc}/vnc.html`;
    },

    get slmUrl(): string {
      return `${httpProtocol}://${vm.slm}:${port.slm}`;
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
 */
export function getBackendUrl(): string {
  return getConfig().backendUrl;
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
 */
export function getBackendWsUrl(): string {
  const backendUrl = getConfig().backendUrl;
  // Convert http(s) to ws(s) protocol
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
 */
export function getSLMUrl(): string {
  return getConfig().slmUrl;
}
