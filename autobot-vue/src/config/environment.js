// Centralized Environment Configuration
// Single source of truth for all API and service URLs
// 
// IMPORTANT: These are bootstrap values only! The actual configuration should be
// loaded from the backend via the /api/config/frontend endpoint.
// Only the BASE_URL needs to be known at startup to connect to the backend.

export const API_CONFIG = {
  // Bootstrap URL - Use Vite proxy in development, direct URL in production
  BASE_URL: (() => {
    const viteApiBaseUrl = import.meta.env.VITE_API_BASE_URL;
    const viteApiUrl = import.meta.env.VITE_API_URL;
    
    if (viteApiBaseUrl) {
      console.log('[AutoBot] Using VITE_API_BASE_URL:', viteApiBaseUrl);
      return viteApiBaseUrl;
    }
    
    if (viteApiUrl) {
      console.log('[AutoBot] Using VITE_API_URL:', viteApiUrl);
      return viteApiUrl;
    }
    
    // In development mode (port 5173), use relative URLs to go through Vite proxy
    if (window.location.port === '5173') {
      console.log('[AutoBot] Using Vite dev proxy for API calls');
      return ''; // Empty string means relative URLs will use same origin
    }
    
    // In production, construct backend URL dynamically
    // Handle WSL/Docker scenarios intelligently
    const protocol = window.location.protocol;
    let hostname = window.location.hostname;
    const port = '8001'; // Backend always on 8001
    
    // If accessing from localhost but backend is in WSL, localhost should work
    // due to WSL2 automatic port forwarding
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      // Keep localhost - WSL2 will forward automatically
      hostname = 'localhost';
    }
    
    const dynamicUrl = `${protocol}//${hostname}:${port}`;
    console.log('[AutoBot] Using dynamic URL:', dynamicUrl);
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
    
    // In development mode (port 5173), use WebSocket proxy through Vite
    if (window.location.port === '5173') {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws`;
      console.log('[AutoBot] Using Vite WebSocket proxy:', wsUrl);
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

// Helper function to get full URL
export function getApiUrl(endpoint = '') {
  return `${API_CONFIG.BASE_URL}${endpoint}`;
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

// Validation function to check if API is available
export async function validateApiConnection() {
  try {
    const response = await fetch(getApiUrl(ENDPOINTS.HEALTH), {
      method: 'GET',
      timeout: 5000,
    });
    return response.ok;
  } catch (error) {
    console.error('API connection validation failed:', error);
    return false;
  }
}

export default {
  API_CONFIG,
  ENDPOINTS,
  getApiUrl,
  getWsUrl,
  validateApiConnection,
};
