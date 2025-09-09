/**
 * Centralized Default Configuration Values
 * 
 * This file contains ALL fallback values used throughout the AutoBot frontend.
 * This ensures consistency and makes it easy to update network configurations.
 * 
 * IMPORTANT: Update these values when deploying to different network environments
 */

export const DEFAULT_CONFIG = {
  // Network Infrastructure - AutoBot VM Layout
  network: {
    // Backend VM - Main API server
    backend: {
      host: '172.16.168.20',
      port: '8001',
      protocol: 'http'
    },
    
    // Frontend VM - Vue.js development server
    frontend: {
      host: '172.16.168.21', 
      port: '5173',
      protocol: 'http'
    },
    
    // NPU Worker VM - AI processing
    npu_worker: {
      host: '172.16.168.22',
      port: '8081',
      protocol: 'http'
    },
    
    // Redis VM - Database server
    redis: {
      host: '172.16.168.23',
      port: '6379',
      protocol: 'redis'
    },
    
    // AI Stack VM - LLM services
    ai_stack: {
      host: '172.16.168.24',
      port: '8080',
      protocol: 'http'
    },
    
    // Browser Service VM - Playwright automation
    browser: {
      host: '172.16.168.25',
      port: '3000',
      protocol: 'http'
    }
  },

  // VNC Service Configuration
  vnc: {
    desktop: {
      host: '172.16.168.20', // Usually same as backend
      port: '6080',
      protocol: 'http',
      password: 'autobot'
    },
    terminal: {
      host: '172.16.168.20', // Usually same as backend
      port: '6080',
      protocol: 'http',
      password: 'autobot'
    },
    playwright: {
      host: '172.16.168.25', // Browser service VM
      port: '6081', 
      protocol: 'http',
      password: 'playwright'
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