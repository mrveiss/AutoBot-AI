// DEPRECATED: This file is being replaced by AppConfig.js
// Centralized Environment Configuration using new AppConfigService
// 
// MIGRATION: All components should now use AppConfig.js instead of this file
// This file is maintained for backward compatibility during migration

import appConfig from './AppConfig.js';
import { buildDefaultServiceUrl } from './defaults.js';

// Legacy API_CONFIG for backward compatibility
export const API_CONFIG = {
  // Dynamic URLs - these now use AppConfig service
  get BASE_URL() {
    // Synchronous fallback - components should use appConfig.getServiceUrl('backend') instead
    const backendHost = import.meta.env.VITE_BACKEND_HOST;
    const backendPort = import.meta.env.VITE_BACKEND_PORT || '8001';
    const protocol = import.meta.env.VITE_HTTP_PROTOCOL || 'http';
    
    if (backendHost) {
      return `${protocol}://${backendHost}:${backendPort}`;
    }
    
    // Fallback to backend VM using centralized defaults
    return buildDefaultServiceUrl('backend');
  },
  
  get WS_BASE_URL() {
    // Synchronous fallback - components should use appConfig.getWebSocketUrl() instead
    const backendHost = import.meta.env.VITE_BACKEND_HOST;
    const backendPort = import.meta.env.VITE_BACKEND_PORT || '8001';
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    
    if (backendHost) {
      return `${wsProtocol}//${backendHost}:${backendPort}/ws`;
    }
    
    return `${wsProtocol}//localhost:${backendPort}/ws`;
  },

  get DESKTOP_VNC_URL() {
    // Synchronous fallback - components should use appConfig.getVncUrl('desktop') instead
    const envUrl = import.meta.env.VITE_DESKTOP_VNC_URL;
    if (envUrl) return envUrl;
    
    const vncHost = import.meta.env.VITE_DESKTOP_VNC_HOST || '172.16.168.20';
    return `http://${vncHost}:6080/vnc.html?autoconnect=true&password=autobot&resize=remote&reconnect=true&quality=9&compression=9`;
  },

  get TERMINAL_VNC_URL() {
    // Synchronous fallback - components should use appConfig.getVncUrl('terminal') instead
    const envUrl = import.meta.env.VITE_TERMINAL_VNC_URL;
    if (envUrl) return envUrl;
    
    const vncHost = import.meta.env.VITE_TERMINAL_VNC_HOST || '172.16.168.20';
    return `http://${vncHost}:6080/vnc.html?autoconnect=true&password=autobot&resize=remote&reconnect=true&quality=9&compression=9`;
  },

  get PLAYWRIGHT_VNC_URL() {
    // Synchronous fallback - components should use appConfig.getVncUrl('playwright') instead
    const envUrl = import.meta.env.VITE_PLAYWRIGHT_VNC_URL;
    if (envUrl) return envUrl;
    
    const vncHost = import.meta.env.VITE_PLAYWRIGHT_VNC_HOST || 'localhost';
    return `http://${vncHost}:6081/vnc.html?autoconnect=true&password=playwright&resize=remote&reconnect=true&quality=9&compression=9`;
  },

  PLAYWRIGHT_API_URL: import.meta.env.VITE_PLAYWRIGHT_API_URL || '/api/playwright',
  OLLAMA_URL: import.meta.env.VITE_OLLAMA_URL || '',
  CHROME_DEBUG_URL: import.meta.env.VITE_CHROME_DEBUG_URL || '',
  LMSTUDIO_URL: import.meta.env.VITE_LMSTUDIO_URL || '',

  // Static configuration - improved timeouts based on MCP analysis
  TIMEOUT: parseInt(import.meta.env.VITE_API_TIMEOUT || '60000'),  // Increased from 30s to 60s
  KNOWLEDGE_BASE_TIMEOUT: parseInt(import.meta.env.VITE_KNOWLEDGE_TIMEOUT || '300000'),
  RETRY_ATTEMPTS: parseInt(import.meta.env.VITE_API_RETRY_ATTEMPTS || '5'),  // Increased retries
  RETRY_DELAY: parseInt(import.meta.env.VITE_API_RETRY_DELAY || '2000'),     // 2s delay between retries
  ENABLE_DEBUG: import.meta.env.VITE_ENABLE_DEBUG === 'true',
  ENABLE_RUM: import.meta.env.VITE_ENABLE_RUM !== 'false',
  DEV_MODE: import.meta.env.DEV,
  PROD_MODE: import.meta.env.PROD,
  CACHE_BUST_VERSION: import.meta.env.VITE_APP_VERSION || Date.now().toString(),
  DISABLE_CACHE: import.meta.env.VITE_DISABLE_CACHE === 'true',
};

export const ENDPOINTS = {
  // System
  HEALTH: '/api/system/health',
  INFO: '/api/system/info',
  METRICS: '/api/system/metrics',

  // Chat
  CHAT: '/api/chat/chats',
  CHATS: '/api/chat/chats',
  CHAT_NEW: '/api/chat/chats/new',

  // Knowledge Base
  KNOWLEDGE_SEARCH: '/api/knowledge_base/search',
  KNOWLEDGE_STATS: '/api/knowledge_base/stats',
  KNOWLEDGE_ENTRIES: '/api/knowledge_base/entries',
  KNOWLEDGE_ADD_TEXT: '/api/knowledge_base/add_text',
  KNOWLEDGE_ADD_URL: '/api/knowledge_base/add_url',
  KNOWLEDGE_ADD_FILE: '/api/knowledge_base/add_file',
  KNOWLEDGE_EXPORT: '/api/knowledge_base/export',
  KNOWLEDGE_CLEANUP: '/api/knowledge_base/cleanup',

  // Settings
  SETTINGS: '/api/settings',
  SETTINGS_BACKEND: '/api/settings/backend',

  // Files
  FILES_LIST: '/api/files/list',
  FILES_UPLOAD: '/api/files/upload',
  FILES_DOWNLOAD: '/api/files/download',
  FILES_DELETE: '/api/files/delete',

  // Terminal
  TERMINAL_EXECUTE: '/api/terminal/execute',
  TERMINAL_SESSIONS: '/api/terminal/sessions',

  // WebSocket endpoints
  WS_CHAT: '/ws/chat',
  WS_TERMINAL: '/ws/terminal',
  WS_LOGS: '/ws/logs',
  WS_MONITORING: '/ws/monitoring',
};

// Helper function to get full URL with cache-busting
export function getApiUrl(endpoint = '', options = {}) {
  let fullUrl = `${API_CONFIG.BASE_URL}${endpoint}`;
  
  // Add cache-busting parameters if not disabled
  if (!API_CONFIG.DISABLE_CACHE && (options.cacheBust !== false)) {
    const separator = fullUrl.includes('?') ? '&' : '?';
    const cacheBustParam = `_cb=${API_CONFIG.CACHE_BUST_VERSION}`;
    const timestampParam = `_t=${Date.now()}`;
    fullUrl = `${fullUrl}${separator}${cacheBustParam}&${timestampParam}`;
  }
  
  // Log API URL construction for debugging
  if (API_CONFIG.ENABLE_DEBUG || window.location.port === '5173') {
    console.log('[AutoBot] getApiUrl:', {
      baseUrl: API_CONFIG.BASE_URL,
      endpoint: endpoint,
      fullUrl: fullUrl,
      isRelative: !API_CONFIG.BASE_URL,
      cacheBusted: !API_CONFIG.DISABLE_CACHE && (options.cacheBust !== false)
    });
  }
  
  return fullUrl;
}

// Helper function to get WebSocket URL
export function getWsUrl(endpoint = '') {
  const baseUrl = API_CONFIG.WS_BASE_URL;
  // If base URL already includes /ws or is empty (proxy case), don't add endpoint
  if (baseUrl.includes('/ws') || !baseUrl) {
    return baseUrl;
  }
  return `${baseUrl}${endpoint}`;
}

// Enhanced API fetch with cache-busting headers
export async function fetchApi(endpoint, options = {}) {
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
      console.log('[AutoBot] API Response:', {
        url,
        status: response.status,
        headers: Object.fromEntries(response.headers.entries())
      });
    }
    
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    console.error('[AutoBot] API fetch failed:', error);
    throw error;
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
    console.error('API connection validation failed:', error);
    return false;
  }
}

// Cache invalidation function
export function invalidateApiCache() {
  console.log('[AutoBot] Invalidating API cache...');
  
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
  
  console.log('[AutoBot] API cache invalidated');
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