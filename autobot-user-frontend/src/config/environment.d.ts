// TypeScript declarations for environment.js
export interface ApiConfig {
  BASE_URL: string;
  WS_BASE_URL: string;
  DESKTOP_VNC_URL: string;
  TERMINAL_VNC_URL: string;
  PLAYWRIGHT_VNC_URL: string;
  PLAYWRIGHT_API_URL: string;
  OLLAMA_URL: string;
  CHROME_DEBUG_URL: string;
  LMSTUDIO_URL: string;
  TIMEOUT: number;
  KNOWLEDGE_BASE_TIMEOUT: number;
  RETRY_ATTEMPTS: number;
  RETRY_DELAY: number;
  ENABLE_DEBUG: boolean;
  ENABLE_RUM: boolean;
  DEV_MODE: boolean;
  PROD_MODE: boolean;
  CACHE_BUST_VERSION: string;
  DISABLE_CACHE: boolean;
}

export interface Endpoints {
  HEALTH: string;
  INFO: string;
  METRICS: string;
  CHAT: string;
  CHATS: string;
  CHAT_NEW: string;
  KNOWLEDGE_SEARCH: string;
  KNOWLEDGE_STATS: string;
  KNOWLEDGE_ENTRIES: string;
  KNOWLEDGE_ADD_TEXT: string;
  KNOWLEDGE_ADD_URL: string;
  KNOWLEDGE_ADD_FILE: string;
  KNOWLEDGE_EXPORT: string;
  KNOWLEDGE_CLEANUP: string;
  SETTINGS: string;
  SETTINGS_BACKEND: string;
  FILES_LIST: string;
  FILES_UPLOAD: string;
  FILES_DOWNLOAD: string;
  FILES_DELETE: string;
  TERMINAL_EXECUTE: string;
  TERMINAL_SESSIONS: string;
  WS_CHAT: string;
  WS_TERMINAL: string;
  WS_LOGS: string;
  WS_MONITORING: string;
}

export interface FetchOptions extends RequestInit {
  cacheBust?: boolean;
}

export declare const API_CONFIG: ApiConfig;
export declare const ENDPOINTS: Endpoints;

export declare function getApiUrl(endpoint?: string, options?: FetchOptions): string;
export declare function getWsUrl(endpoint?: string): string;
export declare function fetchApi(endpoint: string, options?: FetchOptions): Promise<Response>;
export declare function validateApiConnection(): Promise<boolean>;
export declare function invalidateApiCache(): void;

declare const _default: {
  API_CONFIG: ApiConfig;
  ENDPOINTS: Endpoints;
  getApiUrl: typeof getApiUrl;
  getWsUrl: typeof getWsUrl;
  fetchApi: typeof fetchApi;
  validateApiConnection: typeof validateApiConnection;
  invalidateApiCache: typeof invalidateApiCache;
};

export default _default;
