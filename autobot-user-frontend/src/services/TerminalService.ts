/**
 * Terminal Service for WebSocket-based terminal communication
 * Provides interface for terminal sessions, command execution, and real-time I/O
 *
 * TypeScript migration of TerminalService.js
 * Preserves identical public API: class TerminalService, useTerminalService, singleton
 */

import { reactive, ref, type Ref } from 'vue'
import appConfig from '@/config/AppConfig.js'
import apiClient from '@/utils/ApiClient'
import { NetworkConstants } from '@/constants/network'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('TerminalService')

// ---------------------------------------------------------------------------
// Types & Interfaces
// ---------------------------------------------------------------------------

type ConnectionState =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'ready'
  | 'error'
  | 'reconnecting'

const CONNECTION_STATES: Readonly<Record<string, ConnectionState>> = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  READY: 'ready',
  ERROR: 'error',
  RECONNECTING: 'reconnecting',
} as const

interface OutputData {
  content: string
  stream: string
}

interface TabCompletionData {
  completions: string[]
  prefix: string
  common_prefix: string
}

interface HistoryData {
  commands: string[]
}

interface HistorySearchData {
  matches: string[]
  query: string
}

/** Callback type union for triggerCallback dispatch */
type CallbackDataMap = {
  onOutput: OutputData
  onPromptChange: string
  onStatusChange: ConnectionState
  onError: string
  onTabCompletion: TabCompletionData
  onHistory: HistoryData
  onHistorySearch: HistorySearchData
}

interface TerminalCallbacks {
  onOutput?: (data: OutputData) => void
  onPromptChange?: (prompt: string) => void
  onStatusChange?: (status: ConnectionState) => void
  onError?: (error: string) => void
  onTabCompletion?: (data: TabCompletionData) => void
  onHistory?: (data: HistoryData) => void
  onHistorySearch?: (data: HistorySearchData) => void
}

interface SessionInfo {
  id: string
  status: string
  connected: boolean
}

interface ExecuteOptions {
  timeout?: number
  cwd?: string
  env?: Record<string, string>
}

interface CreateSessionConfig {
  user_id?: string
  security_level?: string
  enable_logging?: boolean
  enable_workflow_control?: boolean
  initial_directory?: string | null
}

/**
 * Incoming WebSocket message shape.
 *
 * `any` is used for `metadata` because the backend sends heterogeneous
 * metadata blobs whose shape varies per message type.
 */
interface WsMessage {
  type: string
  content?: string
  data?: string
  stream?: string
  prompt?: string
  status?: string
  error?: string
  code?: number
  completions?: string[]
  prefix?: string
  common_prefix?: string
  commands?: string[]
  matches?: string[]
  query?: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  metadata?: Record<string, any>
}

interface TabCompletionRequest {
  type: 'tab_completion'
  text: string
  cursor: number
  cwd?: string
}

// ---------------------------------------------------------------------------
// Composable return type
// ---------------------------------------------------------------------------

interface UseTerminalServiceReturn {
  sendInput: (sessionId: string, input: string) => boolean
  sendStdin: (
    sessionId: string,
    content: string,
    isPassword?: boolean,
    commandId?: string | null,
  ) => boolean
  sendTabCompletion: (
    sessionId: string,
    text: string,
    cursor: number,
    cwd?: string | null,
  ) => boolean
  sendHistoryGet: (sessionId: string, limit?: number) => boolean
  sendHistorySearch: (
    sessionId: string,
    query: string,
    limit?: number,
  ) => boolean
  sendSignal: (sessionId: string, signal: string) => boolean
  resize: (sessionId: string, rows: number, cols: number) => boolean
  isConnected: (sessionId: string) => boolean
  sessions: Map<string, SessionInfo>
  connectionStatus: Ref<ConnectionState>
  createSession: () => Promise<string>
  connect: (
    sessionId: string,
    callbacks?: TerminalCallbacks,
  ) => Promise<void>
  disconnect: (sessionId: string) => void
  closeSession: (sessionId: string) => Promise<void>
}

// ---------------------------------------------------------------------------
// TerminalService class
// ---------------------------------------------------------------------------

class TerminalService {
  private connections: Map<string, WebSocket>
  private callbacks: Map<string, TerminalCallbacks>
  private connectionStates: Map<string, ConnectionState>
  private reconnectAttempts: Map<string, number>
  private healthCheckIntervals: Map<string, ReturnType<typeof setInterval>>
  private baseUrl: string
  private maxReconnectAttempts: number
  private reconnectDelay: number

  constructor() {
    this.connections = new Map()
    this.callbacks = new Map()
    this.connectionStates = new Map()
    this.reconnectAttempts = new Map()
    this.healthCheckIntervals = new Map()
    this.baseUrl = ''
    this.maxReconnectAttempts = 5
    this.reconnectDelay = 1000
    this.initializeWebSocketUrl()
  }

  // -----------------------------------------------------------------------
  // WebSocket URL initialisation
  // -----------------------------------------------------------------------

  async initializeWebSocketUrl(): Promise<void> {
    try {
      const wsUrl: string = await appConfig.getWebSocketUrl()
      logger.debug(`Raw WebSocket URL from appConfig: ${wsUrl}`)
      this.baseUrl = this._resolveWsBaseUrl(wsUrl)
    } catch (error) {
      logger.warn('Using fallback WebSocket URL, error:', error)
      this.baseUrl = this._buildFallbackWsUrl()
      logger.debug(`Fallback baseUrl: ${this.baseUrl}`)
    }
  }

  /** Resolve the base WebSocket URL from an appConfig-provided value. */
  private _resolveWsBaseUrl(wsUrl: string): string {
    if (!wsUrl.startsWith('ws://') && !wsUrl.startsWith('wss://')) {
      logger.warn('Got relative WebSocket URL, falling back to absolute URL')
      const url = this._buildFallbackWsUrl()
      logger.debug(`Absolute fallback baseUrl: ${url}`)
      return url
    }
    const url = `${wsUrl.replace('/ws', '')}/api/terminal/ws`
    logger.debug(`Constructed baseUrl: ${url}`)
    return url
  }

  /** Build a deterministic fallback WebSocket URL from NetworkConstants. */
  private _buildFallbackWsUrl(): string {
    return `ws://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}/api/terminal/ws`
  }

  // -----------------------------------------------------------------------
  // Connection state machine
  // -----------------------------------------------------------------------

  /** Set connection state and trigger associated side-effects. */
  setConnectionState(sessionId: string, state: ConnectionState): void {
    this.connectionStates.set(sessionId, state)
    this.triggerCallback(sessionId, 'onStatusChange', state)
    this._applyStateTransitionEffects(sessionId, state)
  }

  /** Apply side-effects for a state transition (health-check management). */
  private _applyStateTransitionEffects(
    sessionId: string,
    state: ConnectionState,
  ): void {
    switch (state) {
      case CONNECTION_STATES.CONNECTED:
        this.startHealthCheck(sessionId)
        break
      case CONNECTION_STATES.READY:
        this.reconnectAttempts.set(sessionId, 0)
        break
      case CONNECTION_STATES.DISCONNECTED:
      case CONNECTION_STATES.ERROR:
        this.stopHealthCheck(sessionId)
        break
    }
  }

  /** Get current connection state for a session. */
  getConnectionState(sessionId: string): ConnectionState {
    return (
      this.connectionStates.get(sessionId) || CONNECTION_STATES.DISCONNECTED
    )
  }

  // -----------------------------------------------------------------------
  // Health check (ping / pong)
  // -----------------------------------------------------------------------

  /** Start periodic health-check pings for a session. */
  startHealthCheck(sessionId: string): void {
    this.stopHealthCheck(sessionId)
    const interval = setInterval(() => {
      if (this.isConnected(sessionId)) {
        this.sendPing(sessionId)
      }
    }, 30_000)
    this.healthCheckIntervals.set(sessionId, interval)
  }

  /** Stop the health-check interval for a session. */
  stopHealthCheck(sessionId: string): void {
    const interval = this.healthCheckIntervals.get(sessionId)
    if (interval) {
      clearInterval(interval)
      this.healthCheckIntervals.delete(sessionId)
    }
  }

  /** Send a single ping message over the WebSocket. */
  sendPing(sessionId: string): void {
    const connection = this.connections.get(sessionId)
    if (connection && connection.readyState === WebSocket.OPEN) {
      try {
        connection.send(JSON.stringify({ type: 'ping' }))
      } catch (error) {
        logger.error('Failed to send ping:', error)
        this.setConnectionState(sessionId, CONNECTION_STATES.ERROR)
      }
    }
  }

  // -----------------------------------------------------------------------
  // Session lifecycle
  // -----------------------------------------------------------------------

  /** Create a new terminal session via the REST API. */
  async createSession(): Promise<string> {
    try {
      const result = await apiClient.createTerminalSession({
        user_id: 'default',
        security_level: 'standard',
        enable_logging: false,
        enable_workflow_control: true,
      } satisfies CreateSessionConfig)

      if (!result) {
        throw new Error('Failed to create session')
      }
      return result.session_id as string
    } catch (error) {
      logger.error('Error creating terminal session:', error)
      throw error
    }
  }

  // -----------------------------------------------------------------------
  // WebSocket connect (split into setup helper to keep under 50 lines)
  // -----------------------------------------------------------------------

  /**
   * Connect to a terminal session via WebSocket with state management.
   *
   * Returns a Promise that resolves when the WebSocket opens successfully,
   * or rejects on timeout / error.
   */
  async connect(
    sessionId: string,
    callbacks: TerminalCallbacks = {},
  ): Promise<void> {
    if (this.connections.has(sessionId)) {
      logger.warn(`Already connected to session ${sessionId}`)
      return
    }

    if (!this.baseUrl) {
      await this.initializeWebSocketUrl()
    }

    this.setConnectionState(sessionId, CONNECTION_STATES.CONNECTING)
    this.callbacks.set(sessionId, callbacks)

    const wsUrl = `${this.baseUrl}/${sessionId}`
    logger.debug(`Connecting to WebSocket: ${wsUrl}`)

    this._validateWsUrl(wsUrl)

    return new Promise<void>((resolve, reject) => {
      try {
        const ws = new WebSocket(wsUrl)
        this.connections.set(sessionId, ws)
        const timeout = this._createConnectionTimeout(sessionId, ws, reject)
        this._attachWsHandlers(sessionId, ws, callbacks, resolve, reject, timeout)
      } catch (error) {
        this._handleConnectCatchError(sessionId, error, reject)
      }
    })
  }

  /** Throw if the URL is not a valid WebSocket URL. */
  private _validateWsUrl(wsUrl: string): void {
    if (!wsUrl.startsWith('ws://') && !wsUrl.startsWith('wss://')) {
      throw new Error(`Invalid WebSocket URL: ${wsUrl}`)
    }
  }

  /** Create and return a connection-timeout timer. */
  private _createConnectionTimeout(
    sessionId: string,
    ws: WebSocket,
    reject: (reason: Error) => void,
  ): ReturnType<typeof setTimeout> {
    return setTimeout(() => {
      if (ws.readyState !== WebSocket.OPEN) {
        logger.error(`WebSocket connection timeout for session ${sessionId}`)
        ws.close()
        this.setConnectionState(sessionId, CONNECTION_STATES.ERROR)
        this.triggerCallback(sessionId, 'onError', 'Connection timeout')
        reject(new Error('WebSocket connection timeout'))
      }
    }, 10_000)
  }

  /** Attach onopen / onmessage / onclose / onerror handlers to the WebSocket. */
  private _attachWsHandlers(
    sessionId: string,
    ws: WebSocket,
    callbacks: TerminalCallbacks,
    resolve: () => void,
    reject: (reason: Error) => void,
    connectionTimeout: ReturnType<typeof setTimeout>,
  ): void {
    ws.onopen = () => {
      clearTimeout(connectionTimeout)
      this.setConnectionState(sessionId, CONNECTION_STATES.CONNECTED)
      setTimeout(() => {
        if (this.getConnectionState(sessionId) === CONNECTION_STATES.CONNECTED) {
          this.setConnectionState(sessionId, CONNECTION_STATES.READY)
        }
      }, 300)
      resolve()
    }

    ws.onmessage = (event: MessageEvent) => {
      this.handleMessage(sessionId, event.data as string)
    }

    ws.onclose = (event: CloseEvent) => {
      clearTimeout(connectionTimeout)
      this._handleWsClose(sessionId, event, callbacks, reject)
    }

    ws.onerror = () => {
      clearTimeout(connectionTimeout)
      logger.error(`Terminal session ${sessionId} error`)
      this.setConnectionState(sessionId, CONNECTION_STATES.ERROR)
      this.triggerCallback(sessionId, 'onError', 'WebSocket connection error')
      reject(new Error('WebSocket connection error'))
    }
  }

  /** Handle WebSocket close: cleanup + optional reconnect. */
  private _handleWsClose(
    sessionId: string,
    event: CloseEvent,
    callbacks: TerminalCallbacks,
    reject: (reason: Error) => void,
  ): void {
    this.cleanupSession(sessionId)
    const attempts = this.reconnectAttempts.get(sessionId) ?? 0

    if (event.code !== 1000 && attempts < this.maxReconnectAttempts) {
      this.attemptReconnect(sessionId, callbacks)
    } else {
      this.setConnectionState(sessionId, CONNECTION_STATES.DISCONNECTED)
    }
    reject(new Error(`WebSocket closed with code ${event.code}`))
  }

  /** Handle a catch-level error during connect(). */
  private _handleConnectCatchError(
    sessionId: string,
    error: unknown,
    reject: (reason: Error) => void,
  ): void {
    const err = error instanceof Error ? error : new Error(String(error))
    logger.error(`Failed to connect to terminal session ${sessionId}:`, err)
    this.setConnectionState(sessionId, CONNECTION_STATES.ERROR)
    this.triggerCallback(sessionId, 'onError', err.message)
    reject(err)
  }

  // -----------------------------------------------------------------------
  // Reconnection
  // -----------------------------------------------------------------------

  /** Attempt automatic reconnection with exponential backoff. */
  async attemptReconnect(
    sessionId: string,
    callbacks: TerminalCallbacks,
  ): Promise<void> {
    const attempts = this.reconnectAttempts.get(sessionId) || 0
    this.reconnectAttempts.set(sessionId, attempts + 1)

    const delay = this.reconnectDelay * Math.pow(2, attempts)
    this.setConnectionState(sessionId, CONNECTION_STATES.RECONNECTING)

    setTimeout(async () => {
      try {
        await this.connect(sessionId, callbacks)
      } catch (error) {
        logger.error(`Reconnection attempt ${attempts + 1} failed:`, error)
        if (attempts + 1 >= this.maxReconnectAttempts) {
          this.setConnectionState(sessionId, CONNECTION_STATES.ERROR)
        }
      }
    }, delay)
  }

  /** Remove the WebSocket reference and stop its health-check. */
  cleanupSession(sessionId: string): void {
    this.connections.delete(sessionId)
    this.stopHealthCheck(sessionId)
  }

  // -----------------------------------------------------------------------
  // handleMessage - split into per-type handlers (each under 50 lines)
  // -----------------------------------------------------------------------

  /** Route an incoming WebSocket message to the correct handler. */
  handleMessage(sessionId: string, data: string): void {
    try {
      const message: WsMessage = JSON.parse(data)
      this._dispatchMessage(sessionId, message)
    } catch (error) {
      logger.error('Failed to parse terminal message:', error)
      this.triggerCallback(sessionId, 'onOutput', {
        content: data,
        stream: 'stdout',
      })
    }
  }

  /** Dispatch a parsed message to the correct typed handler. */
  private _dispatchMessage(sessionId: string, message: WsMessage): void {
    switch (message.type) {
      case 'output':
        this._handleOutputMessage(sessionId, message)
        break
      case 'prompt_change':
        this._handlePromptChange(sessionId, message)
        break
      case 'status':
        this._handleStatusMessage(sessionId, message)
        break
      case 'error':
        this._handleErrorMessage(sessionId, message)
        break
      case 'exit':
        this._handleExitMessage(sessionId, message)
        break
      case 'connection':
        this._handleConnectionMessage(sessionId, message)
        break
      case 'connected':
        this._handleConnectedMessage(sessionId, message)
        break
      case 'pong':
        this._handlePongMessage(sessionId)
        break
      case 'tab_completion':
        this._handleTabCompletion(sessionId, message)
        break
      case 'history':
        this._handleHistoryMessage(sessionId, message)
        break
      case 'history_search':
        this._handleHistorySearch(sessionId, message)
        break
      default:
        logger.warn(`Unknown message type: ${message.type}`, message)
    }
  }

  /** Handle terminal output data. */
  private _handleOutputMessage(sessionId: string, msg: WsMessage): void {
    this.triggerCallback(sessionId, 'onOutput', {
      content: msg.content || msg.data || '',
      stream: msg.stream || msg.metadata?.stream || 'stdout',
    })
  }

  /** Handle prompt-change notification. */
  private _handlePromptChange(sessionId: string, msg: WsMessage): void {
    this.triggerCallback(sessionId, 'onPromptChange', msg.prompt || '')
  }

  /** Handle status update from backend. */
  private _handleStatusMessage(sessionId: string, msg: WsMessage): void {
    if (msg.status) {
      this.setConnectionState(sessionId, msg.status as ConnectionState)
    }
  }

  /** Handle error message from backend. */
  private _handleErrorMessage(sessionId: string, msg: WsMessage): void {
    this.setConnectionState(sessionId, CONNECTION_STATES.ERROR)
    this.triggerCallback(sessionId, 'onError', msg.error || msg.content || '')
  }

  /** Handle process exit notification. */
  private _handleExitMessage(sessionId: string, msg: WsMessage): void {
    this.triggerCallback(sessionId, 'onOutput', {
      content: `Process exited with code ${msg.code}`,
      stream: 'system',
    })
  }

  /** Handle connection-status messages and transition to ready after delay. */
  private _handleConnectionMessage(sessionId: string, msg: WsMessage): void {
    const connectionStatus = msg.status || 'connected'
    if (connectionStatus === 'connected') {
      this.setConnectionState(sessionId, CONNECTION_STATES.CONNECTED)
      setTimeout(() => {
        if (this.getConnectionState(sessionId) === CONNECTION_STATES.CONNECTED) {
          this.setConnectionState(sessionId, CONNECTION_STATES.READY)
        }
      }, 200)
    } else {
      this.setConnectionState(sessionId, connectionStatus as ConnectionState)
    }
  }

  /** Handle explicit "connected" confirmation from the backend. */
  private _handleConnectedMessage(sessionId: string, msg: WsMessage): void {
    logger.debug('Terminal connected:', msg.content)
    this.setConnectionState(sessionId, CONNECTION_STATES.CONNECTED)
    this.setConnectionState(sessionId, CONNECTION_STATES.READY)
    this.triggerCallback(sessionId, 'onOutput', {
      content: msg.content || 'Terminal connected',
      stream: 'system',
    })
  }

  /** Handle pong (health-check reply). */
  private _handlePongMessage(sessionId: string): void {
    if (this.getConnectionState(sessionId) !== CONNECTION_STATES.READY) {
      this.setConnectionState(sessionId, CONNECTION_STATES.READY)
    }
  }

  /** Handle tab-completion response (Issue #749). */
  private _handleTabCompletion(sessionId: string, msg: WsMessage): void {
    this.triggerCallback(sessionId, 'onTabCompletion', {
      completions: msg.completions || [],
      prefix: msg.prefix || '',
      common_prefix: msg.common_prefix || '',
    })
  }

  /** Handle history response (Issue #749). */
  private _handleHistoryMessage(sessionId: string, msg: WsMessage): void {
    this.triggerCallback(sessionId, 'onHistory', {
      commands: msg.commands || [],
    })
  }

  /** Handle history-search response (Issue #749). */
  private _handleHistorySearch(sessionId: string, msg: WsMessage): void {
    this.triggerCallback(sessionId, 'onHistorySearch', {
      matches: msg.matches || [],
      query: msg.query || '',
    })
  }

  // -----------------------------------------------------------------------
  // Input & interaction methods
  // -----------------------------------------------------------------------

  /** Send input text to a terminal session. */
  sendInput(sessionId: string, input: string): boolean {
    const connection = this.connections.get(sessionId)
    if (!connection || connection.readyState !== WebSocket.OPEN) {
      logger.error(`No active connection for session ${sessionId}`)
      return false
    }

    try {
      connection.send(JSON.stringify({ type: 'input', text: input }))
      return true
    } catch (error) {
      logger.error('Failed to send input:', error)
      this.triggerCallback(sessionId, 'onError', 'Failed to send input')
      return false
    }
  }

  /**
   * Send stdin to an interactive command (Issue #33).
   * @param isPassword - disables echo when true
   * @param commandId - optional command ID for tracking
   */
  sendStdin(
    sessionId: string,
    content: string,
    isPassword: boolean = false,
    commandId: string | null = null,
  ): boolean {
    const connection = this.connections.get(sessionId)
    if (!connection || connection.readyState !== WebSocket.OPEN) {
      logger.error(`[STDIN] No active connection for session ${sessionId}`)
      return false
    }

    try {
      const message = JSON.stringify({
        type: 'terminal_stdin',
        content,
        is_password: isPassword,
        command_id: commandId,
      })
      connection.send(message)
      logger.debug(
        `[STDIN] Sent ${content.length} bytes to PTY (password: ${isPassword}, command: ${commandId})`,
      )
      return true
    } catch (error) {
      logger.error('[STDIN] Failed to send stdin:', error)
      this.triggerCallback(sessionId, 'onError', 'Failed to send stdin')
      return false
    }
  }

  /**
   * Send tab-completion request to backend (Issue #749).
   * @param cwd - current working directory (optional)
   */
  sendTabCompletion(
    sessionId: string,
    text: string,
    cursor: number,
    cwd: string | null = null,
  ): boolean {
    const connection = this.connections.get(sessionId)
    if (!connection || connection.readyState !== WebSocket.OPEN) {
      logger.debug(`[TAB] No active connection for session ${sessionId}`)
      return false
    }

    try {
      const message: TabCompletionRequest = {
        type: 'tab_completion',
        text,
        cursor,
      }
      if (cwd) {
        message.cwd = cwd
      }
      connection.send(JSON.stringify(message))
      logger.debug(`[TAB] Sent tab completion request: text="${text}", cursor=${cursor}`)
      return true
    } catch (error) {
      logger.error('[TAB] Failed to send tab completion:', error)
      return false
    }
  }

  /**
   * Request command history from backend (Issue #749).
   * @param limit - maximum number of history entries to retrieve
   */
  sendHistoryGet(sessionId: string, limit: number = 100): boolean {
    const connection = this.connections.get(sessionId)
    if (!connection || connection.readyState !== WebSocket.OPEN) {
      logger.debug(`[HISTORY] No active connection for session ${sessionId}`)
      return false
    }

    try {
      connection.send(JSON.stringify({ type: 'history_get', limit }))
      logger.debug(`[HISTORY] Sent history get request: limit=${limit}`)
      return true
    } catch (error) {
      logger.error('[HISTORY] Failed to send history get:', error)
      return false
    }
  }

  /**
   * Search command history on backend (Issue #749).
   * @param query - search query string
   * @param limit - maximum number of results
   */
  sendHistorySearch(
    sessionId: string,
    query: string,
    limit: number = 50,
  ): boolean {
    const connection = this.connections.get(sessionId)
    if (!connection || connection.readyState !== WebSocket.OPEN) {
      logger.debug(`[HISTORY] No active connection for session ${sessionId}`)
      return false
    }

    try {
      connection.send(JSON.stringify({ type: 'history_search', query, limit }))
      logger.debug(
        `[HISTORY] Sent history search request: query="${query}", limit=${limit}`,
      )
      return true
    } catch (error) {
      logger.error('[HISTORY] Failed to send history search:', error)
      return false
    }
  }

  /** Send a signal to the terminal process (e.g., 'SIGINT', 'SIGTERM'). */
  sendSignal(sessionId: string, signal: string): boolean {
    const connection = this.connections.get(sessionId)
    if (!connection || connection.readyState !== WebSocket.OPEN) {
      logger.error(`No active connection for session ${sessionId}`)
      return false
    }

    try {
      connection.send(JSON.stringify({ type: 'signal', signal }))
      return true
    } catch (error) {
      logger.error('Failed to send signal:', error)
      return false
    }
  }

  /** Resize terminal window dimensions. */
  resize(sessionId: string, rows: number, cols: number): boolean {
    const connection = this.connections.get(sessionId)
    if (!connection || connection.readyState !== WebSocket.OPEN) {
      return false
    }

    try {
      connection.send(JSON.stringify({ type: 'resize', rows, cols }))
      return true
    } catch (error) {
      logger.error('Failed to resize terminal:', error)
      return false
    }
  }

  // -----------------------------------------------------------------------
  // Disconnect & cleanup
  // -----------------------------------------------------------------------

  /** Disconnect the WebSocket for a session. */
  disconnect(sessionId: string): void {
    const connection = this.connections.get(sessionId)
    if (connection) {
      try {
        connection.close(1000, 'Client disconnect')
      } catch (error) {
        logger.error('Error closing WebSocket:', error)
      }
      this.connections.delete(sessionId)
      this.callbacks.delete(sessionId)
    }
  }

  /** Close terminal session on server and clean up locally. */
  async closeSession(sessionId: string): Promise<void> {
    this.disconnect(sessionId)
    try {
      await apiClient.deleteTerminalSession(sessionId)
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      logger.warn('Failed to close session on server:', msg)
    }
  }

  // -----------------------------------------------------------------------
  // Query methods
  // -----------------------------------------------------------------------

  /** Get list of active sessions from the backend. */
  async getSessions(): Promise<SessionInfo[]> {
    try {
      const result = await apiClient.getTerminalSessions()
      return (result || []) as SessionInfo[]
    } catch (error) {
      logger.error('Error getting sessions:', error)
      return []
    }
  }

  /**
   * Execute a single command via the REST API and return the result.
   *
   * `any` is used for the return type because the backend returns
   * heterogeneous command results (stdout, stderr, exit_code, etc.)
   * whose shape depends on the command executed.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async executeCommand(command: string, options: ExecuteOptions = {}): Promise<any> {
    try {
      return await apiClient.executeTerminalCommand(command, {
        timeout: options.timeout || 30_000,
        cwd: options.cwd,
        env: options.env || {},
      })
    } catch (error) {
      logger.error('Error executing command:', error)
      throw error
    }
  }

  /**
   * Get session information from the backend.
   *
   * `any` return: backend session info shape varies
   * (fields depend on session state).
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getSessionInfo(sessionId: string): Promise<any> {
    try {
      return await apiClient.getTerminalSessionInfo(sessionId)
    } catch (error) {
      logger.error('Error getting session info:', error)
      throw error
    }
  }

  // -----------------------------------------------------------------------
  // Internal helpers
  // -----------------------------------------------------------------------

  /**
   * Trigger a callback function if it exists for a given session.
   *
   * Uses a generic constrained to CallbackDataMap so that the data type
   * is checked against the callback name at the call-site.
   */
  triggerCallback<K extends keyof CallbackDataMap>(
    sessionId: string,
    callbackName: K,
    data: CallbackDataMap[K],
  ): void {
    const cbs = this.callbacks.get(sessionId)
    if (cbs) {
      const fn = cbs[callbackName] as ((arg: CallbackDataMap[K]) => void) | undefined
      if (typeof fn === 'function') {
        try {
          fn(data)
        } catch (error) {
          logger.error(`Error in ${callbackName} callback:`, error)
        }
      }
    }
  }

  /** Check if a session's WebSocket is currently open. */
  isConnected(sessionId: string): boolean {
    const connection = this.connections.get(sessionId)
    return !!connection && connection.readyState === WebSocket.OPEN
  }

  /** Close all connections and clear internal state. */
  cleanup(): void {
    for (const [sessionId, connection] of this.connections.entries()) {
      try {
        connection.close(1000, 'Service cleanup')
      } catch (error) {
        logger.error(`Error closing connection ${sessionId}:`, error)
      }
    }
    this.connections.clear()
    this.callbacks.clear()
  }
}

// ---------------------------------------------------------------------------
// Singleton instance
// ---------------------------------------------------------------------------

const terminalService = new TerminalService()

// ---------------------------------------------------------------------------
// Vue composable
// ---------------------------------------------------------------------------

/**
 * Vue composable for terminal service.
 * Wraps the singleton with reactive state for sessions and connection status.
 */
export function useTerminalService(): UseTerminalServiceReturn {
  const isConnectedRef = ref(false)
  const sessions: Map<string, SessionInfo> = reactive(new Map())
  const connectionStatus: Ref<ConnectionState> = ref('disconnected')

  return {
    // Bound service methods (pass-through)
    sendInput: terminalService.sendInput.bind(terminalService),
    sendStdin: terminalService.sendStdin.bind(terminalService),
    sendTabCompletion: terminalService.sendTabCompletion.bind(terminalService),
    sendHistoryGet: terminalService.sendHistoryGet.bind(terminalService),
    sendHistorySearch: terminalService.sendHistorySearch.bind(terminalService),
    sendSignal: terminalService.sendSignal.bind(terminalService),
    resize: terminalService.resize.bind(terminalService),
    isConnected: terminalService.isConnected.bind(terminalService),

    // Reactive state
    sessions,
    connectionStatus,

    // Enhanced methods with reactive updates
    async createSession(): Promise<string> {
      const sessionId = await terminalService.createSession()
      sessions.set(sessionId, {
        id: sessionId,
        status: 'created',
        connected: false,
      })
      return sessionId
    },

    async connect(
      sessionId: string,
      callbacks: TerminalCallbacks = {},
    ): Promise<void> {
      const wrappedCallbacks: TerminalCallbacks = {
        ...callbacks,
        onStatusChange: (status: ConnectionState) => {
          connectionStatus.value = status
          const session = sessions.get(sessionId)
          if (session) {
            session.status = status
            session.connected = status === 'connected'
          }
          if (callbacks.onStatusChange) {
            callbacks.onStatusChange(status)
          }
        },
      }
      await terminalService.connect(sessionId, wrappedCallbacks)
      isConnectedRef.value = true
    },

    disconnect(sessionId: string): void {
      terminalService.disconnect(sessionId)
      const session = sessions.get(sessionId)
      if (session) {
        session.connected = false
        session.status = 'disconnected'
      }

      const hasConnected = Array.from(sessions.values()).some((s) => s.connected)
      if (!hasConnected) {
        isConnectedRef.value = false
        connectionStatus.value = 'disconnected'
      }
    },

    async closeSession(sessionId: string): Promise<void> {
      await terminalService.closeSession(sessionId)
      sessions.delete(sessionId)

      if (sessions.size === 0) {
        isConnectedRef.value = false
        connectionStatus.value = 'disconnected'
      }
    },
  }
}

// ---------------------------------------------------------------------------
// Exports - maintain same public API as .js version
// ---------------------------------------------------------------------------

export { TerminalService }
export type {
  ConnectionState,
  TerminalCallbacks,
  OutputData,
  TabCompletionData,
  HistoryData,
  HistorySearchData,
  SessionInfo,
  ExecuteOptions,
  UseTerminalServiceReturn,
}
export default terminalService
