/**
 * Centralized Default Configuration Values
 *
 * This file contains ALL fallback values used throughout the AutoBot frontend.
 * This ensures consistency and makes it easy to update network configurations.
 *
 * IMPORTANT: Uses NetworkConstants for all IP addresses - NO HARDCODED VALUES
 */

import { NetworkConstants } from '../constants/network.ts';

export const DEFAULT_CONFIG = {
  // Network Infrastructure - AutoBot VM Layout (Uses NetworkConstants)
  network: {
    // Backend VM - Main API server
    backend: {
      host: import.meta.env.VITE_BACKEND_HOST || NetworkConstants.MAIN_MACHINE_IP,
      port: import.meta.env.VITE_BACKEND_PORT || String(NetworkConstants.BACKEND_PORT),
      protocol: import.meta.env.VITE_HTTP_PROTOCOL || 'http'
    },

    // Frontend VM - Vue.js development server
    frontend: {
      host: import.meta.env.VITE_FRONTEND_HOST || NetworkConstants.FRONTEND_VM_IP,
      port: import.meta.env.VITE_FRONTEND_PORT || String(NetworkConstants.FRONTEND_PORT),
      protocol: import.meta.env.VITE_HTTP_PROTOCOL || 'http'
    },

    // NPU Worker VM - AI processing
    npu_worker: {
      host: import.meta.env.VITE_NPU_WORKER_HOST || NetworkConstants.NPU_WORKER_VM_IP,
      port: import.meta.env.VITE_NPU_WORKER_PORT || String(NetworkConstants.NPU_WORKER_PORT),
      protocol: import.meta.env.VITE_HTTP_PROTOCOL || 'http'
    },

    // Redis VM - Database server
    redis: {
      host: import.meta.env.VITE_REDIS_HOST || NetworkConstants.REDIS_VM_IP,
      port: import.meta.env.VITE_REDIS_PORT || String(NetworkConstants.REDIS_PORT),
      protocol: 'redis'
    },

    // AI Stack VM - LLM services
    ai_stack: {
      host: import.meta.env.VITE_AI_STACK_HOST || NetworkConstants.AI_STACK_VM_IP,
      port: import.meta.env.VITE_AI_STACK_PORT || String(NetworkConstants.AI_STACK_PORT),
      protocol: import.meta.env.VITE_HTTP_PROTOCOL || 'http'
    },

    // Browser Service VM - Playwright automation
    browser: {
      host: import.meta.env.VITE_BROWSER_HOST || NetworkConstants.BROWSER_VM_IP,
      port: import.meta.env.VITE_BROWSER_PORT || String(NetworkConstants.BROWSER_SERVICE_PORT),
      protocol: import.meta.env.VITE_HTTP_PROTOCOL || 'http'
    },

    // Ollama LLM service (runs on main machine)
    ollama: {
      host: import.meta.env.VITE_OLLAMA_HOST || NetworkConstants.MAIN_MACHINE_IP,
      port: import.meta.env.VITE_OLLAMA_PORT || String(NetworkConstants.OLLAMA_PORT),
      protocol: import.meta.env.VITE_HTTP_PROTOCOL || 'http'
    }
  },

  // VNC Service Configuration (Uses NetworkConstants)
  vnc: {
    desktop: {
      host: import.meta.env.VITE_DESKTOP_VNC_HOST || NetworkConstants.MAIN_MACHINE_IP,
      port: import.meta.env.VITE_DESKTOP_VNC_PORT || String(NetworkConstants.VNC_PORT),
      protocol: import.meta.env.VITE_HTTP_PROTOCOL || 'http',
      password: import.meta.env.VITE_DESKTOP_VNC_PASSWORD || 'autobot'
    },
    terminal: {
      host: import.meta.env.VITE_TERMINAL_VNC_HOST || NetworkConstants.MAIN_MACHINE_IP,
      port: import.meta.env.VITE_TERMINAL_VNC_PORT || String(NetworkConstants.VNC_PORT),
      protocol: import.meta.env.VITE_HTTP_PROTOCOL || 'http',
      password: import.meta.env.VITE_TERMINAL_VNC_PASSWORD || 'autobot'
    },
    playwright: {
      host: import.meta.env.VITE_PLAYWRIGHT_VNC_HOST || NetworkConstants.BROWSER_VM_IP,
      port: import.meta.env.VITE_PLAYWRIGHT_VNC_PORT || '5900',
      protocol: import.meta.env.VITE_HTTP_PROTOCOL || 'http',
      password: import.meta.env.VITE_PLAYWRIGHT_VNC_PASSWORD || 'autobot'
    }
  },

  // API Configuration
  api: {
    timeout: 30000,           // 30 seconds default timeout
    knowledgeTimeout: 300000, // 5 minutes for knowledge operations
    retryAttempts: 3,
    retryDelay: 1000,
    enableDebug: false,
    enableRum: true,
    disableCache: false
  },

  // Feature Flags
  features: {
    enableWebSockets: true,
    enableVncDesktop: true,
    enableNpuWorker: true,
    enableRum: true,
    enableDebug: false
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