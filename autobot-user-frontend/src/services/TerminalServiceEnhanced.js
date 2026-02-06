/**
 * Enhanced Terminal Service with Multi-Host Support
 * Extends TerminalService with host-specific WebSocket connections
 */

import { reactive, ref } from 'vue';
import terminalService from '@/services/TerminalService.js';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for TerminalServiceEnhanced
const logger = createLogger('TerminalServiceEnhanced');

// Host-specific WebSocket URL generation
export function getHostWebSocketUrl(host, sessionId) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${host.ip}:${host.port}/api/terminal/ws/${sessionId}`;
  return wsUrl;
}

/**
 * Enhanced terminal service class with multi-host support
 */
class TerminalServiceEnhanced {
  constructor() {
    // Delegate to base terminal service
    this.baseService = terminalService;

    // Host-specific connections tracking
    this.hostConnections = new Map(); // sessionId -> { host, connection }
  }

  /**
   * Create terminal session with host specification
   * @param {Object} host - Host configuration
   * @returns {Promise<string>} Session ID
   */
  async createSessionForHost(host) {
    try {
      logger.debug(`Creating session for host: ${host.name}`);

      // Use base service to create session
      // Note: This creates session on default backend (main host)
      // For true multi-host, we'd need backend API on each host
      const sessionId = await this.baseService.createSession();

      // Track host association
      this.hostConnections.set(sessionId, { host });

      return sessionId;
    } catch (error) {
      logger.error(`Failed to create session for ${host.name}:`, error);
      throw error;
    }
  }

  /**
   * Connect to terminal with host-specific WebSocket URL
   * @param {string} sessionId - Session ID
   * @param {Object} host - Host configuration
   * @param {Object} callbacks - Event callbacks
   */
  async connectToHost(sessionId, host, callbacks = {}) {
    try {
      logger.debug(`Connecting to ${host.name} (${host.ip})`);

      // For now, all connections go through main backend
      // The backend handles routing to appropriate hosts via SSH
      // Future enhancement: Direct WebSocket to each VM
      await this.baseService.connect(sessionId, callbacks);

      // Track host connection
      const connection = this.hostConnections.get(sessionId);
      if (connection) {
        connection.connectedAt = new Date();
      }

      logger.debug(`Successfully connected to ${host.name}`);
    } catch (error) {
      logger.error(`Failed to connect to ${host.name}:`, error);
      throw error;
    }
  }

  /**
   * Get host for session
   * @param {string} sessionId - Session ID
   * @returns {Object|null} Host configuration
   */
  getSessionHost(sessionId) {
    const connection = this.hostConnections.get(sessionId);
    return connection?.host || null;
  }

  /**
   * Disconnect from host-specific terminal
   * @param {string} sessionId - Session ID
   */
  disconnectFromHost(sessionId) {
    const host = this.getSessionHost(sessionId);
    if (host) {
      logger.debug(`Disconnecting from ${host.name}`);
    }

    this.baseService.disconnect(sessionId);
    this.hostConnections.delete(sessionId);
  }

  /**
   * Send input to host terminal
   * @param {string} sessionId - Session ID
   * @param {string} input - Input text
   */
  sendInput(sessionId, input) {
    return this.baseService.sendInput(sessionId, input);
  }

  /**
   * Send signal to host terminal
   * @param {string} sessionId - Session ID
   * @param {string} signal - Signal name
   */
  sendSignal(sessionId, signal) {
    return this.baseService.sendSignal(sessionId, signal);
  }

  /**
   * Resize host terminal
   * @param {string} sessionId - Session ID
   * @param {number} rows - Number of rows
   * @param {number} cols - Number of columns
   */
  resize(sessionId, rows, cols) {
    return this.baseService.resize(sessionId, rows, cols);
  }

  /**
   * Check if session is connected
   * @param {string} sessionId - Session ID
   * @returns {boolean} Connection status
   */
  isConnected(sessionId) {
    return this.baseService.isConnected(sessionId);
  }

  /**
   * Get connection state for session
   * @param {string} sessionId - Session ID
   * @returns {string} Connection state
   */
  getConnectionState(sessionId) {
    return this.baseService.getConnectionState(sessionId);
  }

  /**
   * Close session and cleanup
   * @param {string} sessionId - Session ID
   */
  async closeSession(sessionId) {
    await this.baseService.closeSession(sessionId);
    this.hostConnections.delete(sessionId);
  }

  /**
   * Execute command on specific host
   * @param {Object} host - Host configuration
   * @param {string} command - Command to execute
   * @param {Object} options - Execution options
   * @returns {Promise<Object>} Command result
   */
  async executeCommandOnHost(host, command, options = {}) {
    logger.debug(`Executing command on ${host.name}: ${command}`);

    // Use base service for command execution
    // Backend will handle host-specific execution
    return this.baseService.executeCommand(command, options);
  }

  /**
   * Get all active host connections
   * @returns {Array} Array of {sessionId, host, connectedAt}
   */
  getActiveHostConnections() {
    return Array.from(this.hostConnections.entries()).map(([sessionId, data]) => ({
      sessionId,
      ...data
    }));
  }

  /**
   * Cleanup all connections
   */
  cleanup() {
    this.hostConnections.clear();
    this.baseService.cleanup();
  }
}

// Create singleton instance
const terminalServiceEnhanced = new TerminalServiceEnhanced();

/**
 * Vue composable for enhanced terminal service
 * @returns {Object} Enhanced terminal service with multi-host support
 */
export function useTerminalServiceEnhanced() {
  const activeHosts = ref(new Map());
  const connectionStatus = reactive({});

  return {
    // Core methods
    createSessionForHost: terminalServiceEnhanced.createSessionForHost.bind(terminalServiceEnhanced),
    connectToHost: terminalServiceEnhanced.connectToHost.bind(terminalServiceEnhanced),
    disconnectFromHost: terminalServiceEnhanced.disconnectFromHost.bind(terminalServiceEnhanced),
    getSessionHost: terminalServiceEnhanced.getSessionHost.bind(terminalServiceEnhanced),

    // Input/Output
    sendInput: terminalServiceEnhanced.sendInput.bind(terminalServiceEnhanced),
    sendSignal: terminalServiceEnhanced.sendSignal.bind(terminalServiceEnhanced),
    resize: terminalServiceEnhanced.resize.bind(terminalServiceEnhanced),

    // State
    isConnected: terminalServiceEnhanced.isConnected.bind(terminalServiceEnhanced),
    getConnectionState: terminalServiceEnhanced.getConnectionState.bind(terminalServiceEnhanced),

    // Session management
    closeSession: terminalServiceEnhanced.closeSession.bind(terminalServiceEnhanced),
    executeCommandOnHost: terminalServiceEnhanced.executeCommandOnHost.bind(terminalServiceEnhanced),
    getActiveHostConnections: terminalServiceEnhanced.getActiveHostConnections.bind(terminalServiceEnhanced),
    cleanup: terminalServiceEnhanced.cleanup.bind(terminalServiceEnhanced),

    // Reactive state
    activeHosts,
    connectionStatus
  };
}

export { TerminalServiceEnhanced };
export default terminalServiceEnhanced;
