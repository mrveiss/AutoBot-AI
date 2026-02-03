// Settings Type Definitions for AutoBot Vue Frontend
// Centralized type definitions for all settings components

// Chat Settings Interface
export interface ChatSettings {
  auto_scroll: boolean;
  max_messages: number;
  message_retention_days: number;
}

// UI Settings Interface
export interface UISettings {
  theme: 'light' | 'dark' | 'auto';
  language: string;
  show_timestamps: boolean;
  show_status_bar: boolean;
  auto_refresh_interval: number;
}

// Logging Settings Interface
export interface LoggingSettings {
  level: string;
  log_levels: string[];
  console: boolean;
  file: boolean;
  max_file_size: number;
  log_requests: boolean;
  log_sql: boolean;
}

// Prompt Interface
export interface Prompt {
  id: string;
  name?: string;
  description?: string;
  content?: string;
}

// Prompts Settings Interface
export interface PromptsSettings {
  list: Prompt[];
  selectedPrompt: Prompt | null;
  editedContent: string;
}

// RUM Settings Interface
export interface RUMSettings {
  enabled: boolean;
  error_tracking: boolean;
  performance_monitoring: boolean;
  interaction_tracking: boolean;
  session_recording: boolean;
  sample_rate: number;
  max_events_per_session: number;
}

// Developer Settings Interface
export interface DeveloperSettings {
  enabled: boolean;
  enhanced_errors: boolean;
  endpoint_suggestions: boolean;
  debug_logging: boolean;
  rum: RUMSettings;
}

// Backend Settings Interface
export interface BackendSettings {
  [key: string]: any;
  llm?: {
    provider_type?: string;
    local?: {
      provider?: string;
      providers?: Record<string, any>;
    };
    cloud?: {
      provider?: string;
      providers?: Record<string, any>;
    };
  };
  memory?: Record<string, any>;
  agents?: Record<string, any>;
}

// Health Status Interface (updated to match BackendSettings component expectations)
export interface HealthStatus {
  status?: string;
  message?: string;
  basic_health?: any;
  detailed_available?: boolean;
  backend?: {
    llm_provider?: {
      status?: string;
      message?: string;
    };
    [key: string]: any;
  };
  [key: string]: any;
}

// Cache Activity Item Interface (updated to include required properties)
export interface CacheActivityItem {
  id: string;
  timestamp: string;
  operation: string;
  key: string;
  result: string;
  duration_ms: number;
  message: string;
  type: string;
}

// Alternative Cache Activity interface for backward compatibility
export interface CacheActivity {
  id: string;
  message: string;
  type: string;
  timestamp?: string;
  operation?: string;
  key?: string;
  result?: string;
  duration_ms?: number;
}

// Cache Stats Interface
export interface CacheStats {
  status?: string;
  message?: string;
  totalEntries?: number;
  validEntries?: number;
  expiredEntries?: number;
  estimatedSizeBytes?: number;
  strategies?: number;
}

// Cache Config Interface
export interface CacheConfig {
  enabled: boolean;
  defaultTTL: number;
  maxCacheSizeMB: number;
}

// Main Settings Structure Interface
export interface SettingsStructure {
  chat: ChatSettings | null;
  backend: BackendSettings | null;
  ui: UISettings | null;
  logging: LoggingSettings | null;
  prompts: PromptsSettings | null;
  developer: DeveloperSettings | null;
}

// Settings Tab Interface
export interface SettingsTab {
  id: string;
  label: string;
}

// Default Settings Factory Functions
export const createDefaultChatSettings = (): ChatSettings => ({
  auto_scroll: true,
  max_messages: 100,
  message_retention_days: 30
});

export const createDefaultUISettings = (): UISettings => ({
  theme: 'auto',
  language: 'en',
  show_timestamps: true,
  show_status_bar: true,
  auto_refresh_interval: 30
});

export const createDefaultLoggingSettings = (): LoggingSettings => ({
  level: 'info',
  log_levels: ['debug', 'info', 'warn', 'error'],
  console: true,
  file: false,
  max_file_size: 10,
  log_requests: false,
  log_sql: false
});

export const createDefaultRUMSettings = (): RUMSettings => ({
  enabled: false,
  error_tracking: true,
  performance_monitoring: true,
  interaction_tracking: false,
  session_recording: false,
  sample_rate: 100,
  max_events_per_session: 1000
});

export const createDefaultDeveloperSettings = (): DeveloperSettings => ({
  enabled: false,
  enhanced_errors: true,
  endpoint_suggestions: true,
  debug_logging: false,
  rum: createDefaultRUMSettings()
});

export const createDefaultPromptsSettings = (): PromptsSettings => ({
  list: [],
  selectedPrompt: null,
  editedContent: ''
});

export const createDefaultBackendSettings = (): BackendSettings => ({
  llm: {
    provider_type: 'local',
    local: {
      provider: 'ollama',
      providers: {}
    },
    cloud: {
      provider: 'openai',
      providers: {}
    }
  },
  memory: {},
  agents: {}
});

export const createDefaultCacheConfig = (): CacheConfig => ({
  enabled: true,
  defaultTTL: 300,
  maxCacheSizeMB: 100
});

// Helper function to create CacheActivity items with required fields
export const createCacheActivityItem = (data: Partial<CacheActivityItem>): CacheActivityItem => ({
  id: data.id || Math.random().toString(36).substr(2, 9),
  timestamp: data.timestamp || new Date().toISOString(),
  operation: data.operation || 'unknown',
  key: data.key || '',
  result: data.result || 'success',
  duration_ms: data.duration_ms || 0,
  message: data.message || `${data.operation || 'Operation'} completed`,
  type: data.type || 'cache_operation'
});

// Default Settings Structure Factory
export const createDefaultSettings = (): SettingsStructure => ({
  chat: null,
  backend: null,
  ui: null,
  logging: null,
  prompts: null,
  developer: null
});