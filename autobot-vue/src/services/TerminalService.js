/**
 * Terminal Service for WebSocket-based terminal communication
 * Provides interface for terminal sessions, command execution, and real-time I/O
 */

import { reactive, ref } from 'vue';
import appConfig from '@/config/AppConfig.js';
import apiClient from '@/utils/ApiClient.js';
import { NetworkConstants } from '@/constants/network';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('TerminalService');

// Use singleton ApiClient instance for terminal operations

// Connection states for state machine
const CONNECTION_STATES = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  READY: 'ready',        // Connected AND input ready
  ERROR: 'error',
  RECONNECTING: 'reconnecting'
};

class TerminalService {
  constructor() {
    this.connections = new Map(); // sessionId -> WebSocket connection
    this.callbacks = new Map(); // sessionId -> event callbacks
    this.connectionStates = new Map(); // sessionId -> connection state
    this.reconnectAttempts = new Map(); // sessionId -> attempt count
    this.healthCheckIntervals = new Map(); // sessionId -> interval ID
    this.baseUrl = ''; // Will be loaded async
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000; // Start with 1 second
    this.initializeWebSocketUrl();
  }

  async initializeWebSocketUrl() {
    try {
      const wsUrl = await appConfig.getWebSocketUrl();
      logger.debug(`[TerminalService] Raw WebSocket URL from appConfig: ${wsUrl}`);

      // CRITICAL FIX: Check if we got a relative URL (proxy mode)
      // WebSockets CANNOT use relative URLs for cross-origin connections
      if (!wsUrl.startsWith('ws://') && !wsUrl.startsWith('wss://')) {
        logger.warn('[TerminalService] Got relative WebSocket URL, falling back to absolute URL');
        // Use NetworkConstants for absolute URL - backend is always on main machine
        this.baseUrl = `ws://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}/api/terminal/ws`;
        logger.debug(`[TerminalService] Absolute fallback baseUrl: ${this.baseUrl}`);
      } else {
        // WebSocket URL format: ws://host:port/ws
        // We need: ws://host:port/api/terminal/ws
        this.baseUrl = `${wsUrl.replace('/ws', '')}/api/terminal/ws`;
        logger.debug(`[TerminalService] Constructed baseUrl: ${this.baseUrl}`);
      }
    } catch (error) {
      logger.warn('[TerminalService] Using fallback WebSocket URL, error:', error);
      this.baseUrl = `ws://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}/api/terminal/ws`;
      logger.debug(`[TerminalService] Fallback baseUrl: ${this.baseUrl}`);
    }
  }

  /**
   * Set connection state and trigger callbacks
   * @param {string} sessionId - Session ID
   * @param {string} state - New connection state
   */
  setConnectionState(sessionId, state) {
    const _oldState = this.connectionStates.get(sessionId); // Track for potential future logging
    this.connectionStates.set(sessionId, state);

    // Terminal state change

    // Trigger state change callback
    this.triggerCallback(sessionId, 'onStatusChange', state);

    // Handle state-specific logic
    switch (state) {
      case CONNECTION_STATES.CONNECTED:
        // Start health check
        this.startHealthCheck(sessionId);
        break;

      case CONNECTION_STATES.READY:
        // Reset reconnection attempts on successful ready state
        this.reconnectAttempts.set(sessionId, 0);
        break;

      case CONNECTION_STATES.DISCONNECTED:
      case CONNECTION_STATES.ERROR:
        // Stop health check
        this.stopHealthCheck(sessionId);
        break;
    }
  }

  /**
   * Get current connection state
   * @param {string} sessionId - Session ID
   * @returns {string} Connection state
   */
  getConnectionState(sessionId) {
    return this.connectionStates.get(sessionId) || CONNECTION_STATES.DISCONNECTED;
  }

  /**
   * Start health check for session
   * @param {string} sessionId - Session ID
   */
  startHealthCheck(sessionId) {
    // Clear any existing interval
    this.stopHealthCheck(sessionId);

    const interval = setInterval(() => {
      if (this.isConnected(sessionId)) {
        this.sendPing(sessionId);
      }
    }, 30000); // Every 30 seconds

    this.healthCheckIntervals.set(sessionId, interval);
  }

  /**
   * Stop health check for session
   * @param {string} sessionId - Session ID
   */
  stopHealthCheck(sessionId) {
    const interval = this.healthCheckIntervals.get(sessionId);
    if (interval) {
      clearInterval(interval);
      this.healthCheckIntervals.delete(sessionId);
    }
  }

  /**
   * Send ping to check connection health
   * @param {string} sessionId - Session ID
   */
  sendPing(sessionId) {
    const connection = this.connections.get(sessionId);
    if (connection && connection.readyState === WebSocket.OPEN) {
      try {
        connection.send(JSON.stringify({ type: 'ping' }));
      } catch (error) {
        logger.error('Failed to send ping:', error);
        this.setConnectionState(sessionId, CONNECTION_STATES.ERROR);
      }
    }
  }

  /**
   * Create a new terminal session
   * @returns {Promise<string>} Session ID
   */
  async createSession() {
    try {
      const result = await apiClient.createTerminalSession({
        user_id: 'default',
        security_level: 'standard',
        enable_logging: false,
        enable_workflow_control: true
        // initial_directory removed - let backend determine the initial directory
      });

      if (!result) {
        throw new Error('Failed to create session');
      }

      return result.session_id;
    } catch (error) {
      logger.error('Error creating terminal session:', error);
      throw error;
    }
  }

  /**
   * Connect to a terminal session via WebSocket with state management
   * @param {string} sessionId - The session ID to connect to
   * @param {Object} callbacks - Event callback functions
   * @param {Function} callbacks.onOutput - Called when terminal produces output
   * @param {Function} callbacks.onPromptChange - Called when prompt changes
   * @param {Function} callbacks.onStatusChange - Called when connection status changes
   * @param {Function} callbacks.onError - Called when an error occurs
   * @param {Function} callbacks.onTabCompletion - Called when tab completion results arrive (Issue #749)
   */
  async connect(sessionId, callbacks = {}) {
    if (this.connections.has(sessionId)) {
      logger.warn(`Already connected to session ${sessionId}`);
      return;
    }

    // Ensure WebSocket URL is initialized
    if (!this.baseUrl) {
      await this.initializeWebSocketUrl();
    }

    this.setConnectionState(sessionId, CONNECTION_STATES.CONNECTING);
    this.callbacks.set(sessionId, callbacks);

    // CRITICAL FIX: Return a Promise that resolves when WebSocket actually connects
    return new Promise((resolve, reject) => {
      try {
        const wsUrl = `${this.baseUrl}/${sessionId}`;
        logger.debug(`[TerminalService] Connecting to WebSocket: ${wsUrl}`);
        logger.debug(`[TerminalService] BaseURL: ${this.baseUrl}, SessionID: ${sessionId}`);

        // Verify URL is valid
        if (!wsUrl.startsWith('ws://') && !wsUrl.startsWith('wss://')) {
          const error = new Error(`Invalid WebSocket URL: ${wsUrl}`);
          logger.error('[TerminalService]', error);
          reject(error);
          return;
        }

        const ws = new WebSocket(wsUrl);

        this.connections.set(sessionId, ws);

        // Set a connection timeout
        const connectionTimeout = setTimeout(() => {
          if (ws.readyState !== WebSocket.OPEN) {
            logger.error(`WebSocket connection timeout for session ${sessionId}`);
            ws.close();
            this.setConnectionState(sessionId, CONNECTION_STATES.ERROR);
            this.triggerCallback(sessionId, 'onError', 'Connection timeout');
            reject(new Error('WebSocket connection timeout'));
          }
        }, 10000); // 10 second timeout

        ws.onopen = () => {
          // WebSocket opened for session
          clearTimeout(connectionTimeout);
          this.setConnectionState(sessionId, CONNECTION_STATES.CONNECTED);

          // Send initial ready check with improved timing
          setTimeout(() => {
            if (this.getConnectionState(sessionId) === CONNECTION_STATES.CONNECTED) {
              // Terminal auto-setting to READY after connection
              this.setConnectionState(sessionId, CONNECTION_STATES.READY);
            }
          }, 300); // Optimized delay for backend readiness

          resolve(); // Connection successful
        };

        ws.onmessage = (event) => {
          this.handleMessage(sessionId, event.data);
        };

        ws.onclose = (event) => {
          // WebSocket closed for session
          clearTimeout(connectionTimeout);
          this.cleanupSession(sessionId);

          // Attempt reconnection if not intentional
          if (event.code !== 1000 && this.reconnectAttempts.get(sessionId, 0) < this.maxReconnectAttempts) {
            this.attemptReconnect(sessionId, callbacks);
          } else {
            this.setConnectionState(sessionId, CONNECTION_STATES.DISCONNECTED);
          }

          // Reject if not yet resolved
          reject(new Error(`WebSocket closed with code ${event.code}`));
        };

        ws.onerror = (error) => {
          clearTimeout(connectionTimeout);
          logger.error(`Terminal session ${sessionId} error:`, error);
          this.setConnectionState(sessionId, CONNECTION_STATES.ERROR);
          this.triggerCallback(sessionId, 'onError', 'WebSocket connection error');
          reject(new Error('WebSocket connection error'));
        };

      } catch (error) {
        logger.error(`Failed to connect to terminal session ${sessionId}:`, error);
        this.setConnectionState(sessionId, CONNECTION_STATES.ERROR);
        this.triggerCallback(sessionId, 'onError', error.message);
        reject(error);
      }
    });
  }

  /**
   * Attempt automatic reconnection with exponential backoff
   * @param {string} sessionId - Session ID
   * @param {Object} callbacks - Original callbacks
   */
  async attemptReconnect(sessionId, callbacks) {
    const attempts = this.reconnectAttempts.get(sessionId) || 0;
    this.reconnectAttempts.set(sessionId, attempts + 1);

    const delay = this.reconnectDelay * Math.pow(2, attempts); // Exponential backoff

    // Attempting reconnection

    this.setConnectionState(sessionId, CONNECTION_STATES.RECONNECTING);

    setTimeout(async () => {
      try {
        await this.connect(sessionId, callbacks);
      } catch (error) {
        logger.error(`Reconnection attempt ${attempts + 1} failed:`, error);
        if (attempts + 1 >= this.maxReconnectAttempts) {
          this.setConnectionState(sessionId, CONNECTION_STATES.ERROR);
        }
      }
    }, delay);
  }

  /**
   * Clean up session resources
   * @param {string} sessionId - Session ID
   */
  cleanupSession(sessionId) {
    this.connections.delete(sessionId);
    this.stopHealthCheck(sessionId);
    // Keep callbacks for potential reconnection
  }

  /**
   * Handle incoming WebSocket message
   * @param {string} sessionId - Session ID
   * @param {string} data - Raw message data
   */
  handleMessage(sessionId, data) {
    try {
      const message = JSON.parse(data);

      switch (message.type) {
        case 'output':
          this.triggerCallback(sessionId, 'onOutput', {
            content: message.content || message.data, // Support both formats
            stream: message.stream || message.metadata?.stream || 'stdout'
          });
          break;

        case 'prompt_change':
          this.triggerCallback(sessionId, 'onPromptChange', message.prompt);
          break;

        case 'status':
          // Update connection state based on status messages
          const status = message.status;
          if (status) {
            this.setConnectionState(sessionId, status);
          }
          break;

        case 'error':
          this.setConnectionState(sessionId, CONNECTION_STATES.ERROR);
          this.triggerCallback(sessionId, 'onError', message.error || message.content);
          break;

        case 'exit':
          this.triggerCallback(sessionId, 'onOutput', {
            content: `Process exited with code ${message.code}`,
            stream: 'system'
          });
          break;

        case 'connection':
          // Handle connection status messages - update state
          const connectionStatus = message.status || 'connected';
          if (connectionStatus === 'connected') {
            this.setConnectionState(sessionId, CONNECTION_STATES.CONNECTED);
            // Transition to ready after brief delay to ensure backend is ready
            setTimeout(() => {
              if (this.getConnectionState(sessionId) === CONNECTION_STATES.CONNECTED) {
                // Terminal setting to READY state
                this.setConnectionState(sessionId, CONNECTION_STATES.READY);
              }
            }, 200); // Increased delay for better reliability
          } else {
            this.setConnectionState(sessionId, connectionStatus);
          }
          break;

        case 'connected':
          // Backend confirmation that terminal is connected
          logger.debug('[TerminalService] Terminal connected:', message.content);
          this.setConnectionState(sessionId, CONNECTION_STATES.CONNECTED);
          // Set to READY immediately since backend confirms it's ready
          this.setConnectionState(sessionId, CONNECTION_STATES.READY);
          this.triggerCallback(sessionId, 'onOutput', {
            content: message.content || 'Terminal connected',
            stream: 'system'
          });
          break;

        case 'pong':
          // Health check response - connection is healthy
          // Health check pong received
          if (this.getConnectionState(sessionId) !== CONNECTION_STATES.READY) {
            this.setConnectionState(sessionId, CONNECTION_STATES.READY);
          }
          break;

        // Issue #749: Handle tab completion response from backend
        case 'tab_completion':
          this.triggerCallback(sessionId, 'onTabCompletion', {
            completions: message.completions || [],
            prefix: message.prefix || '',
            common_prefix: message.common_prefix || ''
          });
          break;

        default:
          logger.warn(`Unknown message type: ${message.type}`, message);
      }
    } catch (error) {
      logger.error('Failed to parse terminal message:', error, data);
      // Treat as raw output
      this.triggerCallback(sessionId, 'onOutput', {
        content: data,
        stream: 'stdout'
      });
    }
  }

  /**
   * Send input to terminal session
   * @param {string} sessionId - Session ID
   * @param {string} input - Input text to send
   */
  sendInput(sessionId, input) {
    const connection = this.connections.get(sessionId);
    if (!connection || connection.readyState !== WebSocket.OPEN) {
      logger.error(`No active connection for session ${sessionId}`);
      return false;
    }

    try {
      const message = JSON.stringify({
        type: 'input',
        text: input  // Send raw input - don't add newline (Enter key sends \r itself)
      });

      connection.send(message);

      // Don't echo locally - let the backend handle it
      return true;
    } catch (error) {
      logger.error('Failed to send input:', error);
      this.triggerCallback(sessionId, 'onError', 'Failed to send input');
      return false;
    }
  }

  /**
   * Send stdin to interactive command (Issue #33)
   * @param {string} sessionId - Session ID
   * @param {string} content - Stdin content to send
   * @param {boolean} isPassword - Whether this is password input (disables echo)
   * @param {string} commandId - Optional command ID for tracking
   */
  sendStdin(sessionId, content, isPassword = false, commandId = null) {
    const connection = this.connections.get(sessionId);
    if (!connection || connection.readyState !== WebSocket.OPEN) {
      logger.error(`[STDIN] No active connection for session ${sessionId}`);
      return false;
    }

    try {
      const message = JSON.stringify({
        type: 'terminal_stdin',
        content: content,
        is_password: isPassword,
        command_id: commandId
      });

      connection.send(message);
      logger.debug(`[STDIN] Sent ${content.length} bytes to PTY (password: ${isPassword}, command: ${commandId})`);
      return true;
    } catch (error) {
      logger.error('[STDIN] Failed to send stdin:', error);
      this.triggerCallback(sessionId, 'onError', 'Failed to send stdin');
      return false;
    }
  }

  /**
   * Send tab completion request to backend (Issue #749)
   * @param {string} sessionId - Session ID
   * @param {string} text - Current command line text
   * @param {number} cursor - Cursor position in the text
   * @param {string} cwd - Current working directory (optional)
   * @returns {boolean} Whether the request was sent successfully
   */
  sendTabCompletion(sessionId, text, cursor, cwd = null) {
    const connection = this.connections.get(sessionId);
    if (!connection || connection.readyState !== WebSocket.OPEN) {
      logger.debug(`[TAB] No active connection for session ${sessionId}`);
      return false;
    }

    try {
      const message = {
        type: 'tab_completion',
        text: text,
        cursor: cursor
      };

      // Only include cwd if provided
      if (cwd) {
        message.cwd = cwd;
      }

      connection.send(JSON.stringify(message));
      logger.debug(`[TAB] Sent tab completion request: text="${text}", cursor=${cursor}`);
      return true;
    } catch (error) {
      logger.error('[TAB] Failed to send tab completion:', error);
      return false;
    }
  }

  /**
   * Send a signal to the terminal process
   * @param {string} sessionId - Session ID
   * @param {string} signal - Signal name (e.g., 'SIGINT', 'SIGTERM')
   */
  sendSignal(sessionId, signal) {
    const connection = this.connections.get(sessionId);
    if (!connection || connection.readyState !== WebSocket.OPEN) {
      logger.error(`No active connection for session ${sessionId}`);
      return false;
    }

    try {
      const message = JSON.stringify({
        type: 'signal',
        signal: signal
      });

      connection.send(message);
      return true;
    } catch (error) {
      logger.error('Failed to send signal:', error);
      return false;
    }
  }

  /**
   * Resize terminal window
   * @param {string} sessionId - Session ID
   * @param {number} rows - Number of rows
   * @param {number} cols - Number of columns
   */
  resize(sessionId, rows, cols) {
    const connection = this.connections.get(sessionId);
    if (!connection || connection.readyState !== WebSocket.OPEN) {
      return false;
    }

    try {
      const message = JSON.stringify({
        type: 'resize',
        rows: rows,
        cols: cols
      });

      connection.send(message);
      return true;
    } catch (error) {
      logger.error('Failed to resize terminal:', error);
      return false;
    }
  }

  /**
   * Disconnect from terminal session
   * @param {string} sessionId - Session ID
   */
  disconnect(sessionId) {
    const connection = this.connections.get(sessionId);
    if (connection) {
      try {
        connection.close(1000, 'Client disconnect');
      } catch (error) {
        logger.error('Error closing WebSocket:', error);
      }
      this.connections.delete(sessionId);
      this.callbacks.delete(sessionId);
    }
  }

  /**
   * Close terminal session and clean up
   * @param {string} sessionId - Session ID
   */
  async closeSession(sessionId) {
    // Disconnect WebSocket first
    this.disconnect(sessionId);

    // Then close the session on the server
    try {
      await apiClient.deleteTerminalSession(sessionId);
    } catch (error) {
      logger.warn('Failed to close session on server:', error.message);
    } finally {
      // Continue cleanup regardless of server response
    }
  }

  /**
   * Get list of active sessions
   * @returns {Promise<Array>} List of session objects
   */
  async getSessions() {
    try {
      const result = await apiClient.getTerminalSessions();
      return result || [];
    } catch (error) {
      logger.error('Error getting sessions:', error);
      return [];
    }
  }

  /**
   * Execute a single command and return result
   * @param {string} command - Command to execute
   * @param {Object} options - Execution options
   * @returns {Promise<Object>} Command result
   */
  async executeCommand(command, options = {}) {
    try {
      const result = await apiClient.executeTerminalCommand(command, {
        timeout: options.timeout || 30000,
        cwd: options.cwd,
        env: options.env || {}
      });

      return result;
    } catch (error) {
      logger.error('Error executing command:', error);
      throw error;
    }
  }

  /**
   * Get session information
   * @param {string} sessionId - Session ID
   * @returns {Promise<Object>} Session info
   */
  async getSessionInfo(sessionId) {
    try {
      const result = await apiClient.getTerminalSessionInfo(sessionId);
      return result;
    } catch (error) {
      logger.error('Error getting session info:', error);
      throw error;
    }
  }

  /**
   * Trigger callback function if it exists
   * @param {string} sessionId - Session ID
   * @param {string} callbackName - Name of callback function
   * @param {*} data - Data to pass to callback
   */
  triggerCallback(sessionId, callbackName, data) {
    const callbacks = this.callbacks.get(sessionId);
    if (callbacks && typeof callbacks[callbackName] === 'function') {
      try {
        callbacks[callbackName](data);
      } catch (error) {
        logger.error(`Error in ${callbackName} callback:`, error);
      }
    }
  }

  /**
   * Check if session is connected
   * @param {string} sessionId - Session ID
   * @returns {boolean} Connection status
   */
  isConnected(sessionId) {
    const connection = this.connections.get(sessionId);
    return connection && connection.readyState === WebSocket.OPEN;
  }

  /**
   * Clean up all connections
   */
  cleanup() {
    for (const [sessionId, connection] of this.connections.entries()) {
      try {
        connection.close(1000, 'Service cleanup');
      } catch (error) {
        logger.error(`Error closing connection ${sessionId}:`, error);
      }
    }
    this.connections.clear();
    this.callbacks.clear();
  }
}

// Create singleton instance
const terminalService = new TerminalService();

/**
 * Vue composable for terminal service
 * @returns {Object} Terminal service instance and reactive state
 */
export function useTerminalService() {
  const isConnected = ref(false);
  const sessions = reactive(new Map());
  const connectionStatus = ref('disconnected');

  return {
    // Service instance methods
    sendInput: terminalService.sendInput.bind(terminalService),
    sendStdin: terminalService.sendStdin.bind(terminalService),  // Issue #33
    sendTabCompletion: terminalService.sendTabCompletion.bind(terminalService),  // Issue #749
    sendSignal: terminalService.sendSignal.bind(terminalService),
    resize: terminalService.resize.bind(terminalService),
    // Note: connect, disconnect, closeSession are defined below with reactive updates
    isConnected: terminalService.isConnected.bind(terminalService),

    // Reactive state
    sessions,
    connectionStatus,

    // Enhanced methods with reactive updates
    async createSession() {
      const sessionId = await terminalService.createSession();
      sessions.set(sessionId, {
        id: sessionId,
        status: 'created',
        connected: false
      });
      return sessionId;
    },

    async connect(sessionId, callbacks = {}) {
      // Wrap callbacks to update reactive state
      const wrappedCallbacks = {
        ...callbacks,
        onStatusChange: (status) => {
          connectionStatus.value = status;
          const session = sessions.get(sessionId);
          if (session) {
            session.status = status;
            session.connected = status === 'connected';
          }
          if (callbacks.onStatusChange) {
            callbacks.onStatusChange(status);
          }
        }
      };

      await terminalService.connect(sessionId, wrappedCallbacks);
      isConnected.value = true;
    },

    disconnect(sessionId) {
      terminalService.disconnect(sessionId);
      const session = sessions.get(sessionId);
      if (session) {
        session.connected = false;
        session.status = 'disconnected';
      }

      // Update global connection status if no sessions are connected
      const hasConnectedSessions = Array.from(sessions.values()).some(s => s.connected);
      if (!hasConnectedSessions) {
        isConnected.value = false;
        connectionStatus.value = 'disconnected';
      }
    },

    async closeSession(sessionId) {
      await terminalService.closeSession(sessionId);
      sessions.delete(sessionId);

      // Update global connection status
      if (sessions.size === 0) {
        isConnected.value = false;
        connectionStatus.value = 'disconnected';
      }
    }
  };
}

// Export both the service class and instance
export { TerminalService };
export default terminalService;
