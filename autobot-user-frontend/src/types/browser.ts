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
