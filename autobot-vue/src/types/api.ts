// API Types - TypeScript definitions for backend API integration
export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  message?: string;
  error?: string;
  status?: string;
}

// Chat API Types
export interface ChatMessage {
  id: string;
  content: string;
  sender: 'user' | 'assistant' | 'system';
  timestamp: string;
  messageType?: string;
  type?: string;
  attachments?: FileAttachment[];
  metadata?: Record<string, any>;
}

export interface ChatSession {
  id: string;
  chatId: string;
  name?: string;
  title?: string;
  messages: ChatMessage[];
  lastMessage?: string;
  timestamp: Date | string;
  createdAt?: Date | string;
  updatedAt?: Date | string;
}

export interface FileAttachment {
  id: string;
  name: string;
  type: string;
  size: number;
  url: string;
}

// File Upload Response
export interface FileUploadResponse {
  path: string;
  filename: string;
  size: number;
  success: boolean;
  message?: string;
}

// WebSocket Types
export interface WebSocketMessage {
  type: string;
  payload?: any;
  timestamp?: string;
}

export interface LLMResponse {
  response: string;
  sender?: string;
  content?: string;
  message_type?: string;
  sources?: any[];
}

// System Health Types
export interface ServiceStatus {
  name: string;
  version?: string;
  status: 'online' | 'warning' | 'error' | 'offline';
  statusText: string;
  responseTime?: number;
  lastCheck?: number;
  consecutiveFailures?: number;
  error?: string;
  timestamp?: number;
  details?: Record<string, any>;
}

export interface SystemAlert {
  id: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  message: string;
  visible: boolean;
  statusDetails?: ServiceStatus;
  timestamp: number;
  type?: string;
}

// Workflow Types
export interface WorkflowApproval {
  workflowId: string;
  stepId: string;
  approved: boolean;
  comment?: string;
}

export interface WorkflowStep {
  id: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: any;
}

export interface Workflow {
  id: string;
  steps: WorkflowStep[];
  status: 'pending' | 'running' | 'completed' | 'failed';
  createdAt: Date;
  updatedAt: Date;
}

// Browser/Research Types
export interface BrowserTestResult {
  results?: TestResult[];
  passed?: number;
  total?: number;
  tests?: TestResult[];
  steps?: TestStep[];
}

export interface TestResult {
  name: string;
  status: 'passed' | 'failed' | 'skipped';
  duration?: number;
  error?: string;
}

export interface TestStep {
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: any;
}

// Knowledge Base Types
export interface KnowledgeBaseStats {
  totalItems: number;
  categories: number;
  documentCount: number;
  categoryCount: number;
}

export interface KnowledgeBaseStatus {
  status: 'loading' | 'ready' | 'error' | 'empty';
  message: string;
  progress: number;
  current_operation: string | null;
  documents_processed: number;
  documents_total: number;
  last_updated: string | null;
}

// Terminal Types
export interface TerminalSession {
  id: string;
  sessionId: string;
  isActive: boolean;
  lastActivity: Date;
}

// Settings Types
export interface AppSettings {
  message_display: {
    show_json: boolean;
    show_planning: boolean;
    show_debug: boolean;
    show_thoughts: boolean;
    show_utility: boolean;
    show_sources: boolean;
  };
  browser_integration: {
    enabled: boolean;
    auto_search: boolean;
    auto_screenshot: boolean;
    show_browser_actions: boolean;
  };
  chat: {
    auto_scroll: boolean;
  };
}

// Error Types
export interface ApiError {
  message: string;
  code?: string;
  status?: number;
  details?: any;
}

// Environment Configuration
export interface EnvironmentConfig {
  API_BASE_URL: string;
  WS_BASE_URL: string;
  VNC_URL?: string;
  NODE_ENV: string;
}