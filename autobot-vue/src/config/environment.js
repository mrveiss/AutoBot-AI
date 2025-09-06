// Centralized Environment Configuration
// Single source of truth for all API and service URLs
// 
// IMPORTANT: These are bootstrap values only! The actual configuration should be
// loaded from the backend via the /api/config/frontend endpoint.
// Only the BASE_URL needs to be known at startup to connect to the backend.

export const API_CONFIG = {
  // Bootstrap URL - Use Vite proxy in development, direct URL in production
  BASE_URL: (() => {
    // Check all possible environment variables that could override proxy behavior
    const viteApiBaseUrl = import.meta.env.VITE_API_BASE_URL;
    const viteApiUrl = import.meta.env.VITE_API_URL;
    const viteBackendHost = import.meta.env.VITE_BACKEND_HOST;
    const viteBackendPort = import.meta.env.VITE_BACKEND_PORT;
    
    console.log('[AutoBot] Environment variables check:');
    console.log('[AutoBot] - VITE_API_BASE_URL:', viteApiBaseUrl);
    console.log('[AutoBot] - VITE_API_URL:', viteApiUrl);
    console.log('[AutoBot] - VITE_BACKEND_HOST:', viteBackendHost);
    console.log('[AutoBot] - VITE_BACKEND_PORT:', viteBackendPort);
    console.log('[AutoBot] - window.location.port:', window.location.port);
    console.log('[AutoBot] - window.location.host:', window.location.host);
    
    // Explicit override for specific API base URL
    if (viteApiBaseUrl) {
      console.log('[AutoBot] Using VITE_API_BASE_URL:', viteApiBaseUrl);
      return viteApiBaseUrl;
    }
    
    if (viteApiUrl) {
      console.log('[AutoBot] Using VITE_API_URL:', viteApiUrl);
      return viteApiUrl;
    }
    
    // Check if running in development mode with Vite dev server (has vite process)
    // Only use proxy mode when actually running with Vite dev server
    if (window.location.port === '5173' && import.meta.env.DEV) {
      console.log('[AutoBot] DEV: Using Vite dev proxy for API calls (empty base URL)');
      console.log('[AutoBot] DEV: This will make all API calls relative and use proxy');
      
      // Check if environment variables would interfere
      if (viteBackendHost || viteBackendPort) {
        console.warn('[AutoBot] WARNING: VITE_BACKEND_HOST/PORT detected but ignoring for proxy mode');
        console.warn('[AutoBot] WARNING: Backend Host:', viteBackendHost, 'Backend Port:', viteBackendPort);
      }
      
      return ''; // Empty string means relative URLs will use same origin + proxy
    }
    
    // In production, construct backend URL dynamically
    // Handle WSL/Docker scenarios intelligently
    const protocol = window.location.protocol;
    let hostname = window.location.hostname;
    const port = viteBackendPort || '8001'; // Use env var if available, default to 8001
    
    // If VITE_BACKEND_HOST is provided and we're not in dev mode, use it
    if (viteBackendHost && viteBackendHost !== 'host.docker.internal') {
      hostname = viteBackendHost;
      console.log('[AutoBot] Using VITE_BACKEND_HOST for production:', hostname);
    } else {
      // If accessing from localhost but backend is in WSL, localhost should work
      // due to WSL2 automatic port forwarding
      if (hostname === 'localhost' || hostname === '127.0.0.1') {
        // Keep localhost - WSL2 will forward automatically
        hostname = 'localhost';
      }
    }
    
    const dynamicUrl = `${protocol}//${hostname}:${port}`;
    console.log('[AutoBot] Using dynamic production URL:', dynamicUrl);
    return dynamicUrl;
  })(),
  
  // WebSocket URL - use proxy in development, direct in production  
  WS_BASE_URL: (() => {
    // Use environment variable if available
    const envWsUrl = import.meta.env.VITE_WS_BASE_URL;
    
    // Use environment variable if available and not pointing to container localhost
    if (envWsUrl && !envWsUrl.includes('127.0.0.1') && !envWsUrl.includes('localhost')) {
      console.log('[AutoBot] Using environment WebSocket URL:', envWsUrl);
      return envWsUrl;
    }
    
    // If environment variable contains localhost addresses, log warning and fall back
    if (envWsUrl && (envWsUrl.includes('127.0.0.1') || envWsUrl.includes('localhost'))) {
      console.warn('[AutoBot] WebSocket environment variable contains localhost address:', envWsUrl, 'falling back to proxy/dynamic URL');
    }
    
    // In development mode (port 5173 with Vite dev server), use WebSocket proxy through Vite
    if (window.location.port === '5173' && import.meta.env.DEV) {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws`;
      console.log('[AutoBot] DEV: Using Vite WebSocket proxy:', wsUrl);
      return wsUrl;
    }
    
    // In production, construct WebSocket URL dynamically  
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const hostname = window.location.hostname;
    const port = '8001'; // Backend always on 8001
    const wsUrl = `${protocol}//${hostname}:${port}`;
    console.log('[AutoBot] Using dynamic WebSocket URL:', wsUrl);
    return wsUrl;
  })(),

  // VNC URL for desktop access - point to host machine where backend runs
  PLAYWRIGHT_VNC_URL: (() => {
    const envVncUrl = import.meta.env.VITE_PLAYWRIGHT_VNC_URL;
    if (envVncUrl) {
      return envVncUrl;
    }
    
    // Point to host machine where VNC server and backend run
    // Frontend runs in Docker, so use host.docker.internal or detected hostname
    const hostname = window.location.hostname === 'localhost' ? 'localhost' : window.location.hostname;
    return `http://${hostname}:6080/vnc.html?autoconnect=true&password=autobot&resize=remote&reconnect=true&quality=9&compression=9`;
  })(),
  PLAYWRIGHT_API_URL: import.meta.env.VITE_PLAYWRIGHT_API_URL || '/api/playwright',
  OLLAMA_URL: import.meta.env.VITE_OLLAMA_URL || '',
  CHROME_DEBUG_URL: import.meta.env.VITE_CHROME_DEBUG_URL || '',
  LMSTUDIO_URL: import.meta.env.VITE_LMSTUDIO_URL || '',

  // Timeouts and Limits
  TIMEOUT: parseInt(import.meta.env.VITE_API_TIMEOUT || '30000'),
  KNOWLEDGE_BASE_TIMEOUT: parseInt(import.meta.env.VITE_KNOWLEDGE_TIMEOUT || '300000'), // 5 minutes
  RETRY_ATTEMPTS: parseInt(import.meta.env.VITE_API_RETRY_ATTEMPTS || '3'),

  // Feature Flags
  ENABLE_DEBUG: import.meta.env.VITE_ENABLE_DEBUG === 'true',
  ENABLE_RUM: import.meta.env.VITE_ENABLE_RUM !== 'false', // enabled by default

  // Development Settings
  DEV_MODE: import.meta.env.DEV,
  PROD_MODE: import.meta.env.PROD,
  
  // Cache Management Settings
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