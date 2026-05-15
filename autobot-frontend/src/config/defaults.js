/**
 * Centralized Default Configuration Values
 *
 * This file provides backward compatibility with existing code that imports
 * from defaults.js. All configuration now comes from the SSOT config.
 *
 * MIGRATION: This file wraps ssot-config.ts for backward compatibility.
 * New code should import directly from '@/config/ssot-config'.
 *
 * Issue: #603 - SSOT Phase 3: Frontend Migration
 * Related: #599 - SSOT Configuration System Epic
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { getConfig } from './ssot-config';

// Get the singleton config instance
const config = getConfig();

/**
 * DEFAULT_CONFIG - Backward-compatible configuration object
 *
 * This object mirrors the old structure but derives all values from SSOT config.
 * This ensures a single source of truth while maintaining backward compatibility.
 */
export const DEFAULT_CONFIG = {
  // Network Infrastructure - AutoBot VM Layout
  network: {
    // Backend VM - Main API server
    backend: {
      host: config.vm.main,
      port: String(config.port.backend),
      protocol: config.httpProtocol
    },

    // Frontend VM - Vue.js development server
    frontend: {
      host: config.vm.frontend,
      port: String(config.port.frontend),
      protocol: config.httpProtocol
    },

    // NPU Worker VM - AI processing
    npu_worker: {
      host: config.vm.npu,
      port: String(config.port.npu),
      protocol: config.httpProtocol
    },

    // Redis VM - Database server
    redis: {
      host: config.vm.redis,
      port: String(config.port.redis),
      protocol: 'redis'
    },

    // AI Stack VM - LLM services
    ai_stack: {
      host: config.vm.aistack,
      port: String(config.port.aistack),
      protocol: config.httpProtocol
    },

    // Browser Service VM - Playwright automation
    browser: {
      host: config.vm.browser,
      port: String(config.port.browser),
      protocol: config.httpProtocol
    },

    // Ollama LLM service (runs on main machine)
    ollama: {
      host: config.vm.ollama,
      port: String(config.port.ollama),
      protocol: config.httpProtocol
    }
  },

  // VNC Service Configuration
  vnc: {
    desktop: {
      host: config.vnc.desktop.host,
      port: String(config.vnc.desktop.port),
      protocol: config.httpProtocol,
      password: config.vnc.desktop.password
    },
    terminal: {
      host: config.vnc.terminal.host,
      port: String(config.vnc.terminal.port),
      protocol: config.httpProtocol,
      password: config.vnc.terminal.password
    },
    playwright: {
      host: config.vnc.playwright.host,
      port: String(config.vnc.playwright.port),
      protocol: config.httpProtocol,
      password: config.vnc.playwright.password
    }
  },

  // API Configuration
  api: {
    timeout: config.timeout.api,
    knowledgeTimeout: config.timeout.knowledge,
    retryAttempts: config.timeout.retryAttempts,
    retryDelay: config.timeout.retryDelay,
    enableDebug: config.feature.debug,
    enableRum: config.feature.rum,
    disableCache: config.feature.cacheDisabled
  },

  // Feature Flags
  features: {
    enableWebSockets: true,
    enableVncDesktop: true,
    enableNpuWorker: true,
    enableRum: config.feature.rum,
    enableDebug: config.feature.debug
  },

  // Development Settings
  development: {
    hotReload: true,
    devTools: true,
    sourceMaps: true,
    mockApi: false
  }
};

/**
 * Get default configuration for a specific service
 * @param {string} serviceName - Name of the service (backend, frontend, etc.)
 * @returns {object} Service configuration with host, port, protocol
 */
export function getServiceDefaults(serviceName) {
  const service = DEFAULT_CONFIG.network[serviceName];
  if (!service) {
    throw new Error(`Unknown service: ${serviceName}. Available services: ${Object.keys(DEFAULT_CONFIG.network).join(', ')}`);
  }
  return service;
}

/**
 * Get default VNC configuration for a specific type
 * @param {string} vncType - Type of VNC service (desktop, terminal, playwright)
 * @returns {object} VNC configuration with host, port, protocol, password
 */
export function getVncDefaults(vncType) {
  const vnc = DEFAULT_CONFIG.vnc[vncType];
  if (!vnc) {
    throw new Error(`Unknown VNC type: ${vncType}. Available types: ${Object.keys(DEFAULT_CONFIG.vnc).join(', ')}`);
  }
  return vnc;
}

/**
 * Build service URL using defaults if environment variables not available
 * @param {string} serviceName - Name of the service
 * @param {object} options - Override options
 * @returns {string} Complete service URL
 */
export function buildDefaultServiceUrl(serviceName, options = {}) {
  const defaults = getServiceDefaults(serviceName);
  const host = options.host || defaults.host;
  const port = options.port || defaults.port;
  const protocol = options.protocol || defaults.protocol;

  return `${protocol}://${host}:${port}`;
}

/**
 * Build VNC URL with default parameters
 * @param {string} vncType - Type of VNC service
 * @param {object} options - Override options and VNC parameters
 * @returns {string} Complete VNC URL with parameters
 */
export function buildDefaultVncUrl(vncType, options = {}) {
  const defaults = getVncDefaults(vncType);
  const host = options.host || defaults.host;
  const port = options.port || defaults.port;
  const protocol = options.protocol || defaults.protocol;
  const password = options.password || defaults.password;

  const baseUrl = `${protocol}://${host}:${port}`;
  const params = new URLSearchParams({
    autoconnect: options.autoconnect !== false ? 'true' : 'false',
    password: password,
    resize: options.resize || 'remote',
    reconnect: options.reconnect !== false ? 'true' : 'false',
    quality: options.quality || '9',
    compression: options.compression || '9'
  });

  return `${baseUrl}/vnc.html?${params.toString()}`;
}

/**
 * Get all default service URLs for debugging
 * @returns {object} Object with all service URLs
 */
export function getAllDefaultServiceUrls() {
  const services = {};
  for (const serviceName of Object.keys(DEFAULT_CONFIG.network)) {
    services[serviceName] = buildDefaultServiceUrl(serviceName);
  }

  const vnc = {};
  for (const vncType of Object.keys(DEFAULT_CONFIG.vnc)) {
    vnc[vncType] = buildDefaultVncUrl(vncType);
  }

  return { services, vnc };
}

export default DEFAULT_CONFIG;
