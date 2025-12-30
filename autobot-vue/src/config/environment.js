// COMPATIBILITY SHIM: This file provides backward compatibility during migration to AppConfig.js
// NEW COMPONENTS: Use AppConfig.js directly for better functionality
// EXISTING COMPONENTS: This shim redirects to AppConfig for seamless migration

import appConfig from './AppConfig.js';
import { buildDefaultServiceUrl } from './defaults.js';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for environment config
const logger = createLogger('EnvConfig');

// Legacy API_CONFIG with AppConfig.js integration
export const API_CONFIG = {
  // Dynamic URLs - now redirect to AppConfig service
  get BASE_URL() {
    // CRITICAL FIX: Detect proxy mode properly
    const backendHost = import.meta.env.VITE_BACKEND_HOST;
    const backendPort = import.meta.env.VITE_BACKEND_PORT;
    const protocol = import.meta.env.VITE_HTTP_PROTOCOL;

    // PROXY MODE: When running on Vite dev server (port 5173), use empty baseUrl for proxy
    const isViteDevServer = window.location.port === '5173';

    if (isViteDevServer && import.meta.env.DEV) {
      logger.debug('PROXY MODE: Using Vite proxy (empty baseUrl)');
      return ''; // Empty string forces relative URLs which go through Vite proxy
    }

    // DIRECT MODE: Use actual backend IP for production or non-proxy environments
    if (backendHost && backendPort && protocol) {
      const directUrl = `${protocol}://${backendHost}:${backendPort}`;
      logger.debug('DIRECT MODE: Using backend URL:', directUrl);
      return directUrl;
    }

    // Fallback to centralized configuration service
    return buildDefaultServiceUrl('backend');
  },

  get WS_BASE_URL() {
    const backendHost = import.meta.env.VITE_BACKEND_HOST;
    const backendPort = import.meta.env.VITE_BACKEND_PORT;
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

    // Direct WebSocket connection to backend
    if (backendHost && backendPort) {
      return `${wsProtocol}//${backendHost}:${backendPort}/ws`;
    }

    // Development proxy mode: use current host with /ws endpoint
    if (import.meta.env.DEV && window.location.port === '5173') {
      return `${wsProtocol}//${window.location.host}/ws`;
    }

    // Fallback to environment variable if available
    const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL;
    if (wsBaseUrl) {
      return wsBaseUrl;
    }

    // Last resort: use default backend configuration
    return buildDefaultServiceUrl('backend').replace('http', 'ws') + '/ws';
  },

  // VNC URLs - delegate to AppConfig for consistency
  get DESKTOP_VNC_URL() {
    // Try to use AppConfig if available, fallback to direct construction
    try {
      return appConfig.getVncUrl('desktop').catch(() => {
        const envUrl = import.meta.env.VITE_DESKTOP_VNC_URL;
        if (envUrl) return envUrl;

        const vncHost = import.meta.env.VITE_DESKTOP_VNC_HOST;
        const vncPort = import.meta.env.VITE_DESKTOP_VNC_PORT;
        const vncPassword = import.meta.env.VITE_DESKTOP_VNC_PASSWORD;

        if (!vncHost || !vncPort || !vncPassword) {
          throw new Error('Desktop VNC configuration missing: VITE_DESKTOP_VNC_HOST, VITE_DESKTOP_VNC_PORT, and VITE_DESKTOP_VNC_PASSWORD must be set');
        }

        return `http://${vncHost}:${vncPort}/vnc.html?autoconnect=true&password=${vncPassword}&resize=remote&reconnect=true&quality=9&compression=9`;
      });
    } catch (_error) {
      // Synchronous fallback for legacy compatibility
      const envUrl = import.meta.env.VITE_DESKTOP_VNC_URL;
      if (envUrl) return envUrl;

      const vncHost = import.meta.env.VITE_DESKTOP_VNC_HOST;
      const vncPort = import.meta.env.VITE_DESKTOP_VNC_PORT;
      const vncPassword = import.meta.env.VITE_DESKTOP_VNC_PASSWORD;

      if (!vncHost || !vncPort || !vncPassword) {
        throw new Error('Desktop VNC configuration missing: VITE_DESKTOP_VNC_HOST, VITE_DESKTOP_VNC_PORT, and VITE_DESKTOP_VNC_PASSWORD must be set');
      }

      return `http://${vncHost}:${vncPort}/vnc.html?autoconnect=true&password=${vncPassword}&resize=remote&reconnect=true&quality=9&compression=9`;
    }
  },

  get TERMINAL_VNC_URL() {
    const envUrl = import.meta.env.VITE_TERMINAL_VNC_URL;
    if (envUrl) return envUrl;

    const vncHost = import.meta.env.VITE_TERMINAL_VNC_HOST;
    const vncPort = import.meta.env.VITE_TERMINAL_VNC_PORT;
    const vncPassword = import.meta.env.VITE_TERMINAL_VNC_PASSWORD;

    if (!vncHost || !vncPort || !vncPassword) {
      throw new Error('Terminal VNC configuration missing: VITE_TERMINAL_VNC_HOST, VITE_TERMINAL_VNC_PORT, and VITE_TERMINAL_VNC_PASSWORD must be set');
    }

    return `http://${vncHost}:${vncPort}/vnc.html?autoconnect=true&password=${vncPassword}&resize=remote&reconnect=true&quality=9&compression=9`;
  },

  get PLAYWRIGHT_VNC_URL() {
    const envUrl = import.meta.env.VITE_PLAYWRIGHT_VNC_URL;
    if (envUrl) return envUrl;

    const vncHost = import.meta.env.VITE_PLAYWRIGHT_VNC_HOST;
    const vncPort = import.meta.env.VITE_PLAYWRIGHT_VNC_PORT;
    const vncPassword = import.meta.env.VITE_PLAYWRIGHT_VNC_PASSWORD;

    if (!vncHost || !vncPort || !vncPassword) {
      throw new Error('Playwright VNC configuration missing: VITE_PLAYWRIGHT_VNC_HOST, VITE_PLAYWRIGHT_VNC_PORT, and VITE_PLAYWRIGHT_VNC_PASSWORD must be set');
    }

    return `http://${vncHost}:${vncPort}/vnc.html?autoconnect=true&password=${vncPassword}&resize=remote&reconnect=true&quality=9&compression=9`;
  },

  PLAYWRIGHT_API_URL: import.meta.env.VITE_PLAYWRIGHT_API_URL || '/api/playwright',
  OLLAMA_URL: import.meta.env.VITE_OLLAMA_URL || '',
  CHROME_DEBUG_URL: import.meta.env.VITE_CHROME_DEBUG_URL || '',
  LMSTUDIO_URL: import.meta.env.VITE_LMSTUDIO_URL || '',

  // Issue #598: Use AppConfig as SINGLE SOURCE OF TRUTH for timeouts
  // Legacy getters maintained for backward compatibility
  get TIMEOUT() {
    return appConfig.getTimeout('default');
  },
  get KNOWLEDGE_BASE_TIMEOUT() {
    return appConfig.getTimeout('knowledge');
  },
  RETRY_ATTEMPTS: parseInt(import.meta.env.VITE_API_RETRY_ATTEMPTS || '3'),
  RETRY_DELAY: parseInt(import.meta.env.VITE_API_RETRY_DELAY || '1000'),
  ENABLE_DEBUG: import.meta.env.VITE_ENABLE_DEBUG === 'true',
  ENABLE_RUM: import.meta.env.VITE_ENABLE_RUM !== 'false',
  DEV_MODE: import.meta.env.DEV,
  PROD_MODE: import.meta.env.PROD,
  CACHE_BUST_VERSION: import.meta.env.VITE_APP_VERSION || Date.now().toString(),
  DISABLE_CACHE: import.meta.env.VITE_DISABLE_CACHE === 'true',
};

export const ENDPOINTS = {
  // System
  HEALTH: '/api/health',
  INFO: '/api/system/info',
  METRICS: '/api/system/metrics',

  // Chat
  CHAT: '/api/chats',
  CHATS: '/api/chats',
  CHAT_NEW: '/api/chats/new',

  // Knowledge Base
  KNOWLEDGE_SEARCH: '/api/knowledge_base/search',
  KNOWLEDGE_STATS: '/api/knowledge_base/stats',
  KNOWLEDGE_ENTRIES: '/api/knowledge_base/entries',
  KNOWLEDGE_ADD_TEXT: '/api/knowledge_base/add_text',
  // Issue #552: Fixed paths - backend uses add_document for URL/file
  KNOWLEDGE_ADD_URL: '/api/knowledge_base/url',
  KNOWLEDGE_ADD_FILE: '/api/knowledge_base/upload',
  // Issue #552: Fixed paths - backend uses /api/knowledge-maintenance/* for these
  KNOWLEDGE_EXPORT: '/api/knowledge-maintenance/export',
  KNOWLEDGE_CLEANUP: '/api/knowledge-maintenance/cleanup',

  // Settings
  // Issue #552: Use trailing slash to match backend endpoint
  SETTINGS: '/api/settings/',
  SETTINGS_BACKEND: '/api/settings/backend',

  // Files
  FILES_LIST: '/api/files/list',
  FILES_UPLOAD: '/api/files/upload',
  FILES_DOWNLOAD: '/api/files/download',
  FILES_DELETE: '/api/files/delete',

  // Terminal
  // Issue #552: Fixed paths - backend uses /api/agent-terminal/*
  TERMINAL_EXECUTE: '/api/agent-terminal/execute',
  TERMINAL_SESSIONS: '/api/agent-terminal/sessions',

  // WebSocket endpoints
  WS_CHAT: '/ws/chat',
  WS_TERMINAL: '/ws/terminal',
  WS_LOGS: '/ws/logs',
  WS_MONITORING: '/ws/monitoring',
};

// Enhanced helper function to get full URL with cache-busting and proper proxy detection
export function getApiUrl(endpoint = '', options = {}) {
  const baseUrl = API_CONFIG.BASE_URL;
  let fullUrl;

  // CRITICAL FIX: Handle proxy mode properly
  if (!baseUrl) {
    // Proxy mode - use relative URL
    fullUrl = endpoint;
  } else {
    // Direct mode - construct full URL
    fullUrl = `${baseUrl}${endpoint}`;
  }

  // Add cache-busting parameters if not disabled
  if (!API_CONFIG.DISABLE_CACHE && (options.cacheBust !== false)) {
    const separator = fullUrl.includes('?') ? '&' : '?';
    const cacheBustParam = `_cb=${API_CONFIG.CACHE_BUST_VERSION}`;
    const timestampParam = `_t=${Date.now()}`;
    fullUrl = `${fullUrl}${separator}${cacheBustParam}&${timestampParam}`;
  }

  // Enhanced logging for debugging
  if (API_CONFIG.ENABLE_DEBUG || window.location.port === '5173') {
    logger.debug('getApiUrl:', {
      baseUrl: baseUrl,
      endpoint: endpoint,
      fullUrl: fullUrl,
      isProxyMode: !baseUrl,
      cacheBusted: !API_CONFIG.DISABLE_CACHE && (options.cacheBust !== false),
      viteDevServer: window.location.port === '5173'
    });
  }

  return fullUrl;
}

// Helper function to get WebSocket URL with proxy detection
export function getWsUrl(endpoint = '') {
  const baseUrl = API_CONFIG.WS_BASE_URL;
  // If base URL already includes /ws or is empty (proxy case), don't add endpoint
  if (baseUrl.includes('/ws') || !baseUrl) {
    return baseUrl;
  }
  return `${baseUrl}${endpoint}`;
}

// Enhanced API fetch with AppConfig integration
export async function fetchApi(endpoint, options = {}) {
  // Try to use AppConfig if available for better functionality
  try {
    return await appConfig.fetchApi(endpoint, options);
  } catch (appConfigError) {
    logger.warn('AppConfig.fetchApi failed, using legacy implementation:', appConfigError.message);

    // Fallback to legacy implementation
    const url = getApiUrl(endpoint, options);

    const defaultHeaders = {
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Pragma': 'no-cache',
      'Expires': '0',
      'X-Cache-Bust': API_CONFIG.CACHE_BUST_VERSION,
      'X-Request-Time': Date.now().toString(),
    };

    // Merge headers
    const headers = {
      ...defaultHeaders,
      ...options.headers
    };

    const fetchOptions = {
      ...options,
      headers,
      cache: 'no-store' // Force no caching at fetch level
    };

    // Add timeout handling
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.TIMEOUT);
    fetchOptions.signal = controller.signal;

    try {
      const response = await fetch(url, fetchOptions);
      clearTimeout(timeoutId);

      // Log response for debugging
      if (API_CONFIG.ENABLE_DEBUG) {
        logger.debug('API Response:', {
          url,
          status: response.status,
          headers: Object.fromEntries(response.headers.entries())
        });
      }

      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      logger.error('API fetch failed:', error);
      throw error;
    }
  }
}

// Validation function to check if API is available
export async function validateApiConnection() {
  try {
    const response = await fetchApi(ENDPOINTS.HEALTH, {
      method: 'GET',
      cacheBust: true // Force cache-busting for health check
    });
    return response.ok;
  } catch (error) {
    logger.error('API connection validation failed:', error);
    return false;
  }
}

// Cache invalidation function - delegate to AppConfig if available
export function invalidateApiCache() {
  logger.info('Invalidating API cache...');

  // Try to use AppConfig invalidation first
  try {
    appConfig.invalidateCache();
  } catch (error) {
    logger.warn('AppConfig cache invalidation failed, using legacy:', error.message);
  }

  // Update cache bust version
  API_CONFIG.CACHE_BUST_VERSION = Date.now().toString();

  // Clear localStorage API caches
  const keys = Object.keys(localStorage);
  keys.forEach(key => {
    if (key.startsWith('autobot_api_') || key.startsWith('autobot_config_')) {
      localStorage.removeItem(key);
    }
  });

  // Clear sessionStorage API caches
  const sessionKeys = Object.keys(sessionStorage);
  sessionKeys.forEach(key => {
    if (key.startsWith('autobot_api_') || key.startsWith('autobot_config_')) {
      sessionStorage.removeItem(key);
    }
  });

  logger.info('API cache invalidated');
}

export default {
  API_CONFIG,
  ENDPOINTS,
  getApiUrl,
  getWsUrl,
  fetchApi,
  validateApiConnection,
  invalidateApiCache,
};