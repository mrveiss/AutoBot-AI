/**
 * Type definitions for Terminal Service
 */

import { Ref } from 'vue';

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'ready' | 'error' | 'reconnecting';

export interface TerminalCallbacks {
  onOutput?: (data: { content: string; stream: string }) => void;
  onPromptChange?: (prompt: string) => void;
  onStatusChange?: (status: ConnectionState) => void;
  onError?: (error: string) => void;
}

export interface SessionCreateOptions {
  user_id?: string;
  security_level?: string;
  enable_logging?: boolean;
  enable_workflow_control?: boolean;
  initial_directory?: string;
}

export interface CommandExecuteOptions {
  timeout?: number;
  cwd?: string;
  env?: Record<string, string>;
}

export interface SessionInfo {
  session_id: string;
  status: string;
  connected: boolean;
  [key: string]: any;
}

export interface TerminalMessage {
  type: 'output' | 'prompt_change' | 'status' | 'error' | 'exit' | 'connection' | 'connected' | 'pong';
  content?: string;
  data?: string;
  stream?: string;
  prompt?: string;
  status?: string;
  error?: string;
  code?: number;
  metadata?: {
    stream?: string;
    [key: string]: any;
  };
}

declare class TerminalService {
  connections: Map<string, WebSocket>;
  callbacks: Map<string, TerminalCallbacks>;
  connectionStates: Map<string, ConnectionState>;
  reconnectAttempts: Map<string, number>;
  healthCheckIntervals: Map<string, number>;
  baseUrl: string;
  maxReconnectAttempts: number;
  reconnectDelay: number;

  initializeWebSocketUrl(): Promise<void>;
  setConnectionState(sessionId: string, state: ConnectionState): void;
  getConnectionState(sessionId: string): ConnectionState;
  startHealthCheck(sessionId: string): void;
  stopHealthCheck(sessionId: string): void;
  sendPing(sessionId: string): void;
  createSession(options?: SessionCreateOptions): Promise<string>;
  connect(sessionId: string, callbacks?: TerminalCallbacks): Promise<void>;
  attemptReconnect(sessionId: string, callbacks: TerminalCallbacks): Promise<void>;
  cleanupSession(sessionId: string): void;
  handleMessage(sessionId: string, data: string): void;
  sendInput(sessionId: string, input: string): boolean;
  sendSignal(sessionId: string, signal: string): boolean;
  resize(sessionId: string, rows: number, cols: number): boolean;
  disconnect(sessionId: string): void;
  closeSession(sessionId: string): Promise<void>;
  getSessions(): Promise<SessionInfo[]>;
  executeCommand(command: string, options?: CommandExecuteOptions): Promise<any>;
  getSessionInfo(sessionId: string): Promise<SessionInfo>;
  triggerCallback(sessionId: string, callbackName: keyof TerminalCallbacks, data: any): void;
  isConnected(sessionId: string): boolean;
  cleanup(): void;
}

export interface ReactiveSession {
  id: string;
  status: string;
  connected: boolean;
}

export interface UseTerminalServiceReturn {
  // Service instance methods
  sendInput: (sessionId: string, input: string) => boolean;
  sendSignal: (sessionId: string, signal: string) => boolean;
  resize: (sessionId: string, rows: number, cols: number) => boolean;
  connect: (sessionId: string, callbacks?: TerminalCallbacks) => Promise<void>;
  disconnect: (sessionId: string) => void;
  closeSession: (sessionId: string) => Promise<void>;
  isConnected: (sessionId: string) => boolean;

  // Reactive state
  sessions: Map<string, ReactiveSession>;
  connectionStatus: Ref<ConnectionState>;

  // Enhanced methods
  createSession: () => Promise<string>;
}

export function useTerminalService(): UseTerminalServiceReturn;

export { TerminalService };

declare const terminalService: TerminalService;
export default terminalService;
