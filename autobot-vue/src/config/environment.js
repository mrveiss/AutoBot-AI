// Centralized Environment Configuration
// Single source of truth for all API and service URLs

export const API_CONFIG = {
  // API Base URLs
  BASE_URL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001',
  WS_BASE_URL: import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8001/ws',
  
  // External Service URLs
  PLAYWRIGHT_VNC_URL: import.meta.env.VITE_PLAYWRIGHT_VNC_URL || 'http://localhost:6080/vnc.html',
  PLAYWRIGHT_API_URL: import.meta.env.VITE_PLAYWRIGHT_API_URL || 'http://localhost:3000',

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
