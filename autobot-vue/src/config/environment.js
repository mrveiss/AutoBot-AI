// Centralized Environment Configuration
// Single source of truth for all API and service URLs
// 
// IMPORTANT: These are bootstrap values only! The actual configuration should be
// loaded from the backend via the /api/config/frontend endpoint.
// Only the BASE_URL needs to be known at startup to connect to the backend.

export const API_CONFIG = {
  // Bootstrap URL - Only this needs to be configured, everything else comes from backend
  BASE_URL: import.meta.env.VITE_API_BASE_URL || (() => {
    // Dynamic detection of backend URL based on current location
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    // If running on a non-standard frontend port, assume backend is on standard port 8001
    const port = window.location.port === '5173' ? '8001' : window.location.port || '8001';
    return `${protocol}//${hostname}:${port}`;
  })(),
  
  // WebSocket URL derived from BASE_URL
  WS_BASE_URL: import.meta.env.VITE_WS_BASE_URL || (() => {
    const baseUrl = import.meta.env.VITE_API_BASE_URL || `${window.location.protocol}//${window.location.hostname}:8001`;
    return baseUrl.replace(/^http/, 'ws') + '/ws';
  })(),

  // VNC URL for browser takeover - point to noVNC web interface with remote scaling
  PLAYWRIGHT_VNC_URL: import.meta.env.VITE_PLAYWRIGHT_VNC_URL || 'http://localhost:6080/vnc.html?autoconnect=true&resize=remote&reconnect=true&quality=9&compression=9',
  PLAYWRIGHT_API_URL: import.meta.env.VITE_PLAYWRIGHT_API_URL || '/api/playwright',
  OLLAMA_URL: import.meta.env.VITE_OLLAMA_URL || '',
  CHROME_DEBUG_URL: import.meta.env.VITE_CHROME_DEBUG_URL || '',
  LMSTUDIO_URL: import.meta.env.VITE_LMSTUDIO_URL || '',

  // Timeouts and Limits
  TIMEOUT: parseInt(import.meta.env.VITE_API_TIMEOUT || '30000'),
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
  CHAT: '/api/chat',
  CHATS: '/api/chats',
  CHAT_NEW: '/api/chats/new',

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
  return `${API_CONFIG.WS_BASE_URL}${endpoint}`;
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
