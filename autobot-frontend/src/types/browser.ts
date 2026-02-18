// Browser Component Types
export interface SearchResult {
  title: string;
  url: string;
  snippet: string;
}

export interface SearchData {
  results?: SearchResult[];
  query?: string;
  search_engine?: string;
}

export interface TestResult {
  status: 'PASS' | 'FAIL' | 'SKIP';
  name: string;
  duration?: number;
  error?: string;
}

export interface TestData {
  tests?: TestResult[];
  passed?: number;
  total?: number;
  duration?: number;
}

export interface TestStep {
  status: 'SUCCESS' | 'FAILED' | 'PENDING';
  description: string;
  result?: any;
}

export interface MessageData {
  steps?: TestStep[];
  message?: string;
  status?: string;
}

export interface AutomationResults {
  lastSearch: SearchData | null;
  lastTest: TestData | null;
  lastMessage: MessageData | null;
}

export interface ConsoleLogEntry {
  level: 'info' | 'warn' | 'error' | 'debug';
  message: string;
  timestamp: Date;
}

export interface BrowserConfig {
  enableAutomation: boolean;
  showDevTools: boolean;
  allowPopups: boolean;
  enableNotifications: boolean;
}

export type BrowserMode = 'vnc' | 'api' | 'native' | 'remote';
export type BrowserStatus = 'connecting' | 'connected' | 'error' | 'disconnected';

// Automation Task Types
export type TaskStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type TaskType = 'navigate' | 'screenshot' | 'search' | 'test' | 'script';

export interface AutomationTask {
  id: string;
  type: TaskType;
  status: TaskStatus;
  name: string;
  description?: string;
  params: Record<string, any>;
  result?: any;
  error?: string;
  createdAt: Date;
  startedAt?: Date;
  completedAt?: Date;
  progress?: number;
}

// Media Gallery Types
export type MediaType = 'screenshot' | 'recording';

export interface MediaItem {
  id: string;
  type: MediaType;
  url: string;
  thumbnail?: string;
  filename: string;
  size: number;
  width?: number;
  height?: number;
  duration?: number;
  capturedAt: Date;
  pageUrl?: string;
  pageTitle?: string;
}

// Automation Recording Types
export type RecordingActionType = 'navigate' | 'click' | 'type' | 'scroll' | 'wait' | 'screenshot';

export interface RecordingAction {
  id: string;
  type: RecordingActionType;
  selector?: string;
  value?: string;
  url?: string;
  timestamp: number;
  description: string;
}

export interface AutomationRecording {
  id: string;
  name: string;
  description?: string;
  actions: RecordingAction[];
  createdAt: Date;
  updatedAt: Date;
  duration: number;
}

// Browser Session Types
export type SessionStatus = 'active' | 'idle' | 'error';

export interface BrowserSession {
  id: string;
  url: string;
  title: string;
  status: SessionStatus;
  created_at: string;
  last_activity: string;
  viewport: { width: number; height: number };
}
