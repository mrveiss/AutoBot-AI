// TypeScript declarations for GlobalWebSocketService.js

export interface WebSocketMessage {
  id?: string
  type: string
  data?: any
  timestamp?: number
}

export interface WebSocketServiceOptions {
  url: string
  reconnectAttempts?: number
  reconnectInterval?: number
  pingInterval?: number
  debug?: boolean
}

export interface ConnectionState {
  isConnected: boolean
  isConnecting: boolean
  lastConnected: Date | null
  reconnectAttempts: number
  url: string | null
}

export declare class GlobalWebSocketService {
  constructor(options: WebSocketServiceOptions)

  connect(): Promise<void>
  disconnect(): void
  send(message: WebSocketMessage): boolean
  subscribe(messageType: string, callback: (data: any) => void): () => void
  unsubscribe(messageType: string, callback?: (data: any) => void): void
  getConnectionState(): ConnectionState

  // Event listeners
  onConnect(callback: () => void): () => void
  onDisconnect(callback: (event: CloseEvent) => void): () => void
  onError(callback: (error: Event) => void): () => void
  onMessage(callback: (message: WebSocketMessage) => void): () => void
}

declare const globalWebSocketService: GlobalWebSocketService
export default globalWebSocketService
