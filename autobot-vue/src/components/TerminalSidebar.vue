<template>
  <div class="terminal-sidebar" :class="{ 'collapsed': collapsed }">
    <button class="toggle-sidebar" @click="toggleSidebar" aria-label="{{ collapsed ? '◀' : '▶' }}">
      {{ collapsed ? '◀' : '▶' }}
    </button>
    <div class="sidebar-content" v-if="!collapsed">
      <div class="terminal-header">
        <h3>Terminal</h3>
        <div class="terminal-actions">
          <button
            class="action-button"
            @click="openInNewTab"
            title="Open in New Tab"
            :disabled="!hasActiveSession"
          >
            🗗
          </button>
          <button
            class="action-button"
            @click="newTerminalSession"
            title="New Terminal Session"
          >
            ➕
          </button>
          <button
            class="action-button danger"
            @click="closeActiveSession"
            title="Close Active Session"
            :disabled="!hasActiveSession"
          >
            ✕
          </button>
        </div>
      </div>

      <div class="session-tabs" v-if="sessions.length > 0">
        <div
          v-for="session in sessions"
          :key="session.id"
          class="session-tab"
          :class="{ 'active': activeSessionId === session.id }"
          @click="switchSession(session.id)"
         tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
          <span class="tab-title">{{ session.title }}</span>
          <button
            class="close-tab"
            @click.stop="closeSession(session.id)"
           aria-label="Action button">
            ×
          </button>
        </div>
      </div>

      <div class="terminal-container">
        <div
          v-if="!hasActiveSession"
          class="no-session-message"
        >
          <p>No active terminal session</p>
          <button class="start-button" @click="newTerminalSession" aria-label="Start terminal">
            Start Terminal
          </button>
        </div>

        <div
          v-else
          class="terminal-window"
          :class="{ 'fullscreen': isFullscreen }"
          ref="terminalWindow"
        >
          <div class="terminal-toolbar">
            <div class="session-info">
              <span class="session-title">{{ activeSession?.title }}</span>
              <span class="session-status" :class="activeSession?.status">
                {{ activeSession?.status }}
              </span>
            </div>
            <div class="terminal-controls">
              <button
                class="control-btn"
                @click="toggleFullscreen"
                title="Toggle Fullscreen"
              >
                {{ isFullscreen ? '🗗' : '🗖' }}
              </button>
              <button
                class="control-btn"
                @click="clearTerminal"
                title="Clear Terminal"
              >
                🗑️
              </button>
            </div>
          </div>

          <div
            class="terminal-output"
            ref="terminalOutput"
            @click="focusInput"
           tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
            <div
              v-for="(line, index) in activeSession?.output || []"
              :key="index"
              class="terminal-line"
              v-html="formatTerminalLine(line)"
            ></div>
            <div class="terminal-prompt">
              <span class="prompt-text">{{ currentPrompt }}</span>
              <input
                ref="terminalInput"
                v-model="currentInput"
                @keydown="handleKeydown"
                @keyup.enter="sendCommand"
                class="terminal-input"
                :disabled="!canInput"
                autocomplete="off"
                spellcheck="false"
              />
              <span class="cursor" :class="{ 'blink': showCursor }">█</span>
            </div>
          </div>
        </div>
      </div>

      <div class="terminal-status">
        <div class="connection-status" :class="connectionStatus">
          <div class="status-indicator"></div>
          <span>{{ connectionStatusText }}</span>
        </div>
        <div class="session-count">
          {{ sessions.length }} session{{ sessions.length !== 1 ? 's' : '' }}
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue';
import { useTerminalService } from '@/services/TerminalService.js';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('TerminalSidebar');

export default {
  name: 'TerminalSidebar',
  props: {
    collapsed: {
      type: Boolean,
      default: false
    }
  },
  emits: ['update:collapsed', 'open-new-tab'],
  setup(props, { emit }) {
    // Terminal service
    const terminalService = useTerminalService();

    // Reactive data
    const sessions = ref([]);
    const activeSessionId = ref(null);
    const currentInput = ref('');
    const currentPrompt = ref('$ ');
    const isFullscreen = ref(false);
    const showCursor = ref(true);
    const connectionStatus = ref('disconnected');

    // Refs
    const terminalWindow = ref(null);
    const terminalOutput = ref(null);
    const terminalInput = ref(null);

    // Computed properties
    const hasActiveSession = computed(() => sessions.value.length > 0 && activeSessionId.value);
    const activeSession = computed(() =>
      sessions.value.find(s => s.id === activeSessionId.value)
    );
    const canInput = computed(() =>
      hasActiveSession.value && activeSession.value?.status === 'connected'
    );
    const connectionStatusText = computed(() => {
      switch (connectionStatus.value) {
        case 'connected': return 'Connected';
        case 'connecting': return 'Connecting...';
        case 'disconnected': return 'Disconnected';
        case 'error': return 'Connection Error';
        default: return 'Unknown';
      }
    });

    // Methods
    const toggleSidebar = () => {
      emit('update:collapsed', !props.collapsed);
    };

    const newTerminalSession = async () => {
      try {
        const sessionId = await terminalService.createSession();
        const newSession = {
          id: sessionId,
          title: `Terminal ${sessions.value.length + 1}`,
          status: 'connecting',
          output: [],
          history: [],
          historyIndex: -1
        };

        sessions.value.push(newSession);
        activeSessionId.value = sessionId;
        connectionStatus.value = 'connecting';

        // Connect to WebSocket
        await terminalService.connect(sessionId, {
          onOutput: handleTerminalOutput,
          onPromptChange: handlePromptChange,
          onStatusChange: handleStatusChange,
          onError: handleError
        });

      } catch (error) {
        logger.error('Failed to create terminal session:', error);
        handleError(error.message);
      }
    };

    const switchSession = (sessionId) => {
      if (activeSessionId.value === sessionId) return;

      // Disconnect from current session
      if (activeSessionId.value) {
        terminalService.disconnect(activeSessionId.value);
      }

      activeSessionId.value = sessionId;

      // Connect to new session
      terminalService.connect(sessionId, {
        onOutput: handleTerminalOutput,
        onPromptChange: handlePromptChange,
        onStatusChange: handleStatusChange,
        onError: handleError
      });
    };

    const closeSession = async (sessionId) => {
      try {
        await terminalService.closeSession(sessionId);

        // Remove from sessions list
        sessions.value = sessions.value.filter(s => s.id !== sessionId);

        // If this was the active session, switch to another or clear
        if (activeSessionId.value === sessionId) {
          if (sessions.value.length > 0) {
            activeSessionId.value = sessions.value[0].id;
            switchSession(sessions.value[0].id);
          } else {
            activeSessionId.value = null;
            connectionStatus.value = 'disconnected';
          }
        }
      } catch (error) {
        logger.error('Failed to close session:', error);
      }
    };

    const closeActiveSession = () => {
      if (hasActiveSession.value) {
        closeSession(activeSessionId.value);
      }
    };

    const openInNewTab = () => {
      if (hasActiveSession.value) {
        emit('open-new-tab', {
          sessionId: activeSessionId.value,
          session: activeSession.value
        });
      }
    };

    const sendCommand = () => {
      if (!currentInput.value.trim() || !canInput.value) return;

      const command = currentInput.value.trim();

      // Add to session history
      if (activeSession.value) {
        activeSession.value.history.push(command);
        activeSession.value.historyIndex = activeSession.value.history.length;
      }

      // Send to terminal service
      terminalService.sendInput(activeSessionId.value, command);

      // Clear input
      currentInput.value = '';
    };

    const handleKeydown = (event) => {
      if (!activeSession.value) return;

      const session = activeSession.value;

      switch (event.key) {
        case 'ArrowUp':
          event.preventDefault();
          if (session.historyIndex > 0) {
            session.historyIndex--;
            currentInput.value = session.history[session.historyIndex];
          }
          break;

        case 'ArrowDown':
          event.preventDefault();
          if (session.historyIndex < session.history.length - 1) {
            session.historyIndex++;
            currentInput.value = session.history[session.historyIndex];
          } else if (session.historyIndex === session.history.length - 1) {
            session.historyIndex = session.history.length;
            currentInput.value = '';
          }
          break;

        case 'Tab':
          event.preventDefault();
          // TODO: Implement tab completion
          break;

        case 'c':
          if (event.ctrlKey) {
            event.preventDefault();
            terminalService.sendSignal(activeSessionId.value, 'SIGINT');
          }
          break;
      }
    };

    const clearTerminal = () => {
      if (activeSession.value) {
        activeSession.value.output = [];
      }
    };

    const toggleFullscreen = () => {
      isFullscreen.value = !isFullscreen.value;
    };

    const focusInput = () => {
      if (terminalInput.value && canInput.value) {
        terminalInput.value.focus();
      }
    };

    // Terminal event handlers
    const handleTerminalOutput = (data) => {
      if (activeSession.value) {
        activeSession.value.output.push({
          type: 'output',
          content: data.content,
          timestamp: new Date()
        });

        nextTick(() => {
          if (terminalOutput.value) {
            terminalOutput.value.scrollTop = terminalOutput.value.scrollHeight;
          }
        });
      }
    };

    const handlePromptChange = (prompt) => {
      currentPrompt.value = prompt;
    };

    const handleStatusChange = (status) => {
      if (activeSession.value) {
        activeSession.value.status = status;
      }
      connectionStatus.value = status;
    };

    const handleError = (error) => {
      logger.error('Terminal error:', error);
      connectionStatus.value = 'error';

      if (activeSession.value) {
        activeSession.value.output.push({
          type: 'error',
          content: `Error: ${error}`,
          timestamp: new Date()
        });
      }
    };

    const formatTerminalLine = (line) => {
      if (!line) return '';

      let content = line.content || line;

      // Basic ANSI escape sequence handling
      content = content
        .replace(/\x1b\[([0-9]{1,2}(;[0-9]{1,2})?)?[mGK]/g, '') // Remove color codes
        .replace(/\r\n/g, '\n')
        .replace(/\r/g, '\n');

      // Handle different line types
      if (line.type === 'error') {
        return `<span class="error-text">${content}</span>`;
      } else if (line.type === 'warning') {
        return `<span class="warning-text">${content}</span>`;
      } else if (line.type === 'success') {
        return `<span class="success-text">${content}</span>`;
      }

      return content;
    };

    // Cursor blinking
    const startCursorBlink = () => {
      setInterval(() => {
        showCursor.value = !showCursor.value;
      }, 500);
    };

    // Lifecycle
    onMounted(() => {
      startCursorBlink();
    });

    onUnmounted(() => {
      // Clean up all sessions
      sessions.value.forEach(session => {
        terminalService.disconnect(session.id);
      });
    });

    return {
      // Data
      sessions,
      activeSessionId,
      currentInput,
      currentPrompt,
      isFullscreen,
      showCursor,
      connectionStatus,

      // Refs
      terminalWindow,
      terminalOutput,
      terminalInput,

      // Computed
      hasActiveSession,
      activeSession,
      canInput,
      connectionStatusText,

      // Methods
      toggleSidebar,
      newTerminalSession,
      switchSession,
      closeSession,
      closeActiveSession,
      openInNewTab,
      sendCommand,
      handleKeydown,
      clearTerminal,
      toggleFullscreen,
      focusInput,
      formatTerminalLine
    };
  }
};
</script>

<style scoped>
.terminal-sidebar {
  width: clamp(300px, 25vw, 400px);
  background-color: #1e1e1e;
  color: #ffffff;
  border-left: 1px solid #333;
  transition: width 0.3s ease;
  position: relative;
  display: flex;
  flex-direction: column;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
}

.terminal-sidebar.collapsed {
  width: 40px;
}

.toggle-sidebar {
  position: absolute;
  top: 10px;
  left: -20px;
  width: 20px;
  height: 30px;
  background-color: #6c757d;
  color: white;
  border: none;
  border-radius: 4px 0 0 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 5;
}

.toggle-sidebar:hover {
  background-color: #5a6268;
}

.sidebar-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 15px;
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
  border-bottom: 1px solid #333;
  padding-bottom: 10px;
}

.terminal-header h3 {
  margin: 0;
  color: #00ff00;
  font-size: 14px;
  font-weight: 600;
}

.terminal-actions {
  display: flex;
  gap: 5px;
}

.action-button {
  background-color: #333;
  border: 1px solid #555;
  color: #fff;
  padding: 4px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
  transition: background-color 0.2s;
}

.action-button:hover:not(:disabled) {
  background-color: #555;
}

.action-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-button.danger:hover:not(:disabled) {
  background-color: #dc3545;
}

.session-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  margin-bottom: 10px;
}

.session-tab {
  display: flex;
  align-items: center;
  background-color: #333;
  border: 1px solid #555;
  border-radius: 3px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 11px;
  transition: background-color 0.2s;
  max-width: 120px;
}

.session-tab:hover {
  background-color: #555;
}

.session-tab.active {
  background-color: #007acc;
  border-color: #007acc;
}

.tab-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 5px;
}

.close-tab {
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  padding: 0;
  margin: 0;
  font-size: 14px;
  line-height: 1;
}

.close-tab:hover {
  color: #ff6b6b;
}

.terminal-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.no-session-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  text-align: center;
  color: #888;
}

.start-button {
  background-color: #007acc;
  border: none;
  color: white;
  padding: 10px 20px;
  border-radius: 5px;
  cursor: pointer;
  margin-top: 10px;
  transition: background-color 0.2s;
}

.start-button:hover {
  background-color: #005999;
}

.terminal-window {
  display: flex;
  flex-direction: column;
  flex: 1;
  background-color: #000;
  border: 1px solid #333;
  border-radius: 5px;
  overflow: hidden;
}

.terminal-window.fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
  border-radius: 0;
}

.terminal-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #2d2d2d;
  padding: 5px 10px;
  border-bottom: 1px solid #333;
  font-size: 11px;
}

.session-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.session-title {
  font-weight: 600;
}

.session-status {
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 10px;
  text-transform: uppercase;
  font-weight: 600;
}

.session-status.connected {
  background-color: #28a745;
  color: white;
}

.session-status.connecting {
  background-color: #ffc107;
  color: black;
}

.session-status.disconnected {
  background-color: #dc3545;
  color: white;
}

.terminal-controls {
  display: flex;
  gap: 5px;
}

.control-btn {
  background: none;
  border: 1px solid #555;
  color: #ccc;
  padding: 2px 6px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 10px;
}

.control-btn:hover {
  background-color: #444;
}

.terminal-output {
  flex: 1;
  padding: 10px;
  overflow-y: auto;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-all;
}

.terminal-line {
  margin: 0;
  padding: 0;
}

.terminal-prompt {
  display: flex;
  align-items: center;
  margin-top: 5px;
}

.prompt-text {
  color: #00ff00;
  margin-right: 5px;
}

.terminal-input {
  background: none;
  border: none;
  color: #fff;
  font-family: inherit;
  font-size: inherit;
  outline: none;
  flex: 1;
}

.cursor {
  color: #00ff00;
  font-weight: bold;
}

.cursor.blink {
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.terminal-status {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #333;
  font-size: 11px;
  color: #888;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 5px;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #dc3545;
}

.connection-status.connected .status-indicator {
  background-color: #28a745;
}

.connection-status.connecting .status-indicator {
  background-color: #ffc107;
  animation: pulse 1s infinite;
}

.connection-status.error .status-indicator {
  background-color: #dc3545;
  animation: flash 0.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@keyframes flash {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.error-text {
  color: #ff6b6b;
}

.warning-text {
  color: #ffc107;
}

.success-text {
  color: #28a745;
}

/* Scrollbar styling */
.terminal-output::-webkit-scrollbar {
  width: 6px;
}

.terminal-output::-webkit-scrollbar-track {
  background: #1e1e1e;
}

.terminal-output::-webkit-scrollbar-thumb {
  background: #555;
  border-radius: 3px;
}

.terminal-output::-webkit-scrollbar-thumb:hover {
  background: #777;
}
</style>
