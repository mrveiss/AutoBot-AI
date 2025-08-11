/**
 * Terminal Service for WebSocket-based terminal communication
 * Provides interface for terminal sessions, command execution, and real-time I/O
 */

import { reactive, ref } from 'vue';

class TerminalService {
  constructor() {
    this.connections = new Map(); // sessionId -> WebSocket connection
    this.callbacks = new Map(); // sessionId -> event callbacks
    this.baseUrl = this.getWebSocketUrl();
  }

  getWebSocketUrl() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = import.meta.env.DEV ? 'localhost' : window.location.hostname;
    const port = import.meta.env.DEV ? '8001' : window.location.port;
    return `${protocol}//${host}:${port}/api/terminal/ws/simple`;
  }

  /**
   * Create a new terminal session
   * @returns {Promise<string>} Session ID
   */
  async createSession() {
    try {
      const baseUrl = import.meta.env.DEV ? 'http://localhost:8001' : '';
      const response = await fetch(`${baseUrl}/api/terminal/simple/sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          shell: '/bin/bash',
          environment: {},
          working_directory: '/home/user'
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to create session: ${response.statusText}`);
      }

      const data = await response.json();
      return data.session_id;
    } catch (error) {
      console.error('Error creating terminal session:', error);
      throw error;
    }
  }

  /**
   * Connect to a terminal session via WebSocket
   * @param {string} sessionId - The session ID to connect to
   * @param {Object} callbacks - Event callback functions
   * @param {Function} callbacks.onOutput - Called when terminal produces output
   * @param {Function} callbacks.onPromptChange - Called when prompt changes
   * @param {Function} callbacks.onStatusChange - Called when connection status changes
   * @param {Function} callbacks.onError - Called when an error occurs
   */
  async connect(sessionId, callbacks = {}) {
    if (this.connections.has(sessionId)) {
      console.warn(`Already connected to session ${sessionId}`);
      return;
    }

    try {
      const wsUrl = `${this.baseUrl}/${sessionId}`;
      const ws = new WebSocket(wsUrl);

      this.connections.set(sessionId, ws);
      this.callbacks.set(sessionId, callbacks);

      ws.onopen = () => {
        console.log(`Connected to terminal session ${sessionId}`);
        // Backend will automatically initialize the terminal session
        this.triggerCallback(sessionId, 'onStatusChange', 'connected');
      };

      ws.onmessage = (event) => {
        this.handleMessage(sessionId, event.data);
      };

      ws.onclose = (event) => {
        console.log(`Terminal session ${sessionId} disconnected:`, event.code, event.reason);
        this.connections.delete(sessionId);
        this.callbacks.delete(sessionId);
        this.triggerCallback(sessionId, 'onStatusChange', 'disconnected');
      };

      ws.onerror = (error) => {
        console.error(`Terminal session ${sessionId} error:`, error);
        this.triggerCallback(sessionId, 'onError', 'WebSocket connection error');
      };

    } catch (error) {
      console.error(`Failed to connect to terminal session ${sessionId}:`, error);
      this.triggerCallback(sessionId, 'onError', error.message);
      throw error;
    }
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
            content: message.content,
            stream: message.stream || 'stdout'
          });
          break;

        case 'prompt_change':
          this.triggerCallback(sessionId, 'onPromptChange', message.prompt);
          break;

        case 'status':
          this.triggerCallback(sessionId, 'onStatusChange', message.status);
          break;

        case 'error':
          this.triggerCallback(sessionId, 'onError', message.error);
          break;

        case 'exit':
          this.triggerCallback(sessionId, 'onOutput', {
            content: `Process exited with code ${message.code}`,
            stream: 'system'
          });
          break;

        case 'connection':
          // Handle connection status messages
          this.triggerCallback(sessionId, 'onStatusChange', message.status || 'connected');
          break;

        default:
          console.warn(`Unknown message type: ${message.type}`);
      }
    } catch (error) {
      console.error('Failed to parse terminal message:', error, data);
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
      console.error(`No active connection for session ${sessionId}`);
      return false;
    }

    try {
      const message = JSON.stringify({
        type: 'input',
        text: input + '\n'  // Backend expects 'text' not 'content'
      });

      connection.send(message);

      // Don't echo locally - let the backend handle it
      return true;
    } catch (error) {
      console.error('Failed to send input:', error);
      this.triggerCallback(sessionId, 'onError', 'Failed to send input');
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
      console.error(`No active connection for session ${sessionId}`);
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
      console.error('Failed to send signal:', error);
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
      console.error('Failed to resize terminal:', error);
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
        console.error('Error closing WebSocket:', error);
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
      const baseUrl = import.meta.env.DEV ? 'http://localhost:8001' : '';
      const response = await fetch(`${baseUrl}/api/terminal/sessions/${sessionId}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        console.warn(`Failed to close session on server: ${response.statusText}`);
      }
    } catch (error) {
      console.error('Error closing terminal session:', error);
    }
  }

  /**
   * Get list of active sessions
   * @returns {Promise<Array>} List of session objects
   */
  async getSessions() {
    try {
      const baseUrl = import.meta.env.DEV ? 'http://localhost:8001' : '';
      const response = await fetch(`${baseUrl}/api/terminal/simple/sessions`);
      if (!response.ok) {
        throw new Error(`Failed to get sessions: ${response.statusText}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error getting sessions:', error);
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
      const baseUrl = import.meta.env.DEV ? 'http://localhost:8001' : '';
      const response = await fetch(`${baseUrl}/api/terminal/command`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          command: command,
          timeout: options.timeout || 30000,
          working_directory: options.cwd,
          environment: options.env || {}
        }),
      });

      if (!response.ok) {
        throw new Error(`Command execution failed: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Error executing command:', error);
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
      const baseUrl = import.meta.env.DEV ? 'http://localhost:8001' : '';
      const response = await fetch(`${baseUrl}/api/terminal/sessions/${sessionId}`);
      if (!response.ok) {
        throw new Error(`Failed to get session info: ${response.statusText}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error getting session info:', error);
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
        console.error(`Error in ${callbackName} callback:`, error);
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
        console.error(`Error closing connection ${sessionId}:`, error);
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
    sendSignal: terminalService.sendSignal.bind(terminalService),
    resize: terminalService.resize.bind(terminalService),
    connect: terminalService.connect.bind(terminalService),
    disconnect: terminalService.disconnect.bind(terminalService),
    closeSession: terminalService.closeSession.bind(terminalService),
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
