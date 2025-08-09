<template>
  <div class="terminal-window-standalone">
    <div class="window-header">
      <div class="window-title">
        <span class="terminal-icon">⬛</span>
        <span>Terminal - {{ sessionTitle }}</span>
      </div>
      <div class="window-controls">
        <button
          class="control-button"
          @click="reconnect"
          :disabled="connecting"
          title="Reconnect"
        >
          {{ connecting ? '⟳' : '🔄' }}
        </button>
        <button
          class="control-button"
          @click="clearTerminal"
          title="Clear"
        >
          🗑️
        </button>
        <button
          class="control-button danger"
          @click="closeWindow"
          title="Close Window"
        >
          ✕
        </button>
      </div>
    </div>

    <div class="terminal-status-bar">
      <div class="status-left">
        <div class="connection-status" :class="connectionStatus">
          <div class="status-dot"></div>
          <span>{{ connectionStatusText }}</span>
        </div>
        <div class="session-info">
          <span>Session: {{ sessionId?.slice(0, 8) }}...</span>
        </div>
      </div>
      <div class="status-right">
        <div class="terminal-stats">
          Lines: {{ outputLines.length }}
        </div>
      </div>
    </div>

    <div class="terminal-main" ref="terminalMain">
      <div
        class="terminal-output"
        ref="terminalOutput"
        @click="focusInput"
      >
        <div
          v-for="(line, index) in outputLines"
          :key="index"
          class="terminal-line"
          :class="getLineClass(line)"
          v-html="formatTerminalLine(line)"
        ></div>

        <div class="terminal-input-line">
          <span class="prompt" v-html="currentPrompt"></span>
          <input
            ref="terminalInput"
            v-model="currentInput"
            @keydown="handleKeydown"
            @keyup.enter="sendCommand"
            class="terminal-input"
            :disabled="!canInput"
            autocomplete="off"
            spellcheck="false"
            autofocus
          />
          <span class="cursor" :class="{ 'blink': showCursor }">█</span>
        </div>
      </div>
    </div>

    <div class="terminal-footer">
      <div class="footer-info">
        <span>Press Ctrl+C to interrupt, Ctrl+D to exit, Tab for completion</span>
      </div>
      <div class="footer-actions">
        <button
          class="footer-button"
          @click="downloadLog"
          title="Download Session Log"
        >
          💾 Save Log
        </button>
        <button
          class="footer-button"
          @click="shareSession"
          title="Share Session"
        >
          🔗 Share
        </button>
      </div>
    </div>

    <!-- Connection Lost Modal -->
    <div v-if="showReconnectModal" class="modal-overlay" @click="hideReconnectModal">
      <div class="modal-content" @click.stop>
        <h3>Connection Lost</h3>
        <p>The terminal connection was lost. Would you like to reconnect?</p>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="hideReconnectModal">
            Cancel
          </button>
          <button class="btn btn-primary" @click="reconnect">
            Reconnect
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { useTerminalService } from '@/services/TerminalService.js';
import { useRoute, useRouter } from 'vue-router';

export default {
  name: 'TerminalWindow',
  setup() {
    const route = useRoute();
    const router = useRouter();
    const terminalService = useTerminalService();

    // Reactive data
    const sessionId = ref(route.params.sessionId || route.query.sessionId);
    const sessionTitle = ref(route.query.title || 'Terminal');
    const outputLines = ref([]);
    const currentInput = ref('');
    const currentPrompt = ref('$ ');
    const connectionStatus = ref('disconnected');
    const connecting = ref(false);
    const showCursor = ref(true);
    const showReconnectModal = ref(false);
    const commandHistory = ref([]);
    const historyIndex = ref(-1);

    // Refs
    const terminalMain = ref(null);
    const terminalOutput = ref(null);
    const terminalInput = ref(null);

    // Computed properties
    const canInput = computed(() => connectionStatus.value === 'connected');
    const connectionStatusText = computed(() => {
      switch (connectionStatus.value) {
        case 'connected': return 'Connected';
        case 'connecting': return 'Connecting...';
        case 'disconnected': return 'Disconnected';
        case 'error': return 'Error';
        default: return 'Unknown';
      }
    });

    // Methods
    const connect = async () => {
      if (!sessionId.value) {
        console.error('No session ID provided');
        return;
      }

      connecting.value = true;
      connectionStatus.value = 'connecting';

      try {
        await terminalService.connect(sessionId.value, {
          onOutput: handleOutput,
          onPromptChange: handlePromptChange,
          onStatusChange: handleStatusChange,
          onError: handleError
        });
      } catch (error) {
        console.error('Failed to connect:', error);
        handleError(error.message);
      } finally {
        connecting.value = false;
      }
    };

    const reconnect = async () => {
      hideReconnectModal();

      // Disconnect first if connected
      if (terminalService.isConnected(sessionId.value)) {
        terminalService.disconnect(sessionId.value);
      }

      // Clear output and reset state
      outputLines.value = [];
      currentPrompt.value = '$ ';

      // Attempt to reconnect
      await connect();
    };

    const sendCommand = () => {
      if (!currentInput.value.trim() || !canInput.value) return;

      const command = currentInput.value.trim();

      // Add to command history
      if (command && (!commandHistory.value.length || commandHistory.value[commandHistory.value.length - 1] !== command)) {
        commandHistory.value.push(command);
        if (commandHistory.value.length > 100) {
          commandHistory.value = commandHistory.value.slice(-100);
        }
      }
      historyIndex.value = commandHistory.value.length;

      // Send to terminal
      terminalService.sendInput(sessionId.value, command);

      // Clear input
      currentInput.value = '';

      // Add command to output for immediate feedback
      addOutputLine({
        content: `${currentPrompt.value}${command}`,
        type: 'command',
        timestamp: new Date()
      });
    };

    const handleKeydown = (event) => {
      switch (event.key) {
        case 'ArrowUp':
          event.preventDefault();
          if (historyIndex.value > 0) {
            historyIndex.value--;
            currentInput.value = commandHistory.value[historyIndex.value];
          }
          break;

        case 'ArrowDown':
          event.preventDefault();
          if (historyIndex.value < commandHistory.value.length - 1) {
            historyIndex.value++;
            currentInput.value = commandHistory.value[historyIndex.value];
          } else if (historyIndex.value === commandHistory.value.length - 1) {
            historyIndex.value = commandHistory.value.length;
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
            terminalService.sendSignal(sessionId.value, 'SIGINT');
          }
          break;

        case 'd':
          if (event.ctrlKey && !currentInput.value) {
            event.preventDefault();
            terminalService.sendInput(sessionId.value, 'exit');
          }
          break;

        case 'l':
          if (event.ctrlKey) {
            event.preventDefault();
            clearTerminal();
          }
          break;
      }
    };

    const clearTerminal = () => {
      outputLines.value = [];
    };

    const focusInput = () => {
      if (terminalInput.value && canInput.value) {
        terminalInput.value.focus();
      }
    };

    const closeWindow = () => {
      if (confirm('Are you sure you want to close this terminal window?')) {
        if (terminalService.isConnected(sessionId.value)) {
          terminalService.disconnect(sessionId.value);
        }
        window.close();
      }
    };

    const downloadLog = () => {
      const logContent = outputLines.value
        .map(line => {
          const timestamp = line.timestamp ? `[${line.timestamp.toLocaleString()}] ` : '';
          return `${timestamp}${line.content || line}`;
        })
        .join('\n');

      const blob = new Blob([logContent], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `terminal-${sessionId.value}-${new Date().toISOString().split('T')[0]}.log`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    };

    const shareSession = async () => {
      const url = `${window.location.origin}/terminal/${sessionId.value}?title=${encodeURIComponent(sessionTitle.value)}`;

      if (navigator.share) {
        try {
          await navigator.share({
            title: `Terminal Session - ${sessionTitle.value}`,
            url: url
          });
        } catch (error) {
          console.log('Share cancelled or failed:', error);
        }
      } else {
        // Fallback: copy to clipboard
        try {
          await navigator.clipboard.writeText(url);
          alert('Terminal URL copied to clipboard!');
        } catch (error) {
          prompt('Copy this URL:', url);
        }
      }
    };

    const hideReconnectModal = () => {
      showReconnectModal.value = false;
    };

    // Terminal event handlers
    const handleOutput = (data) => {
      addOutputLine({
        content: data.content,
        type: data.stream || 'output',
        timestamp: new Date()
      });
    };

    const handlePromptChange = (prompt) => {
      currentPrompt.value = prompt;
    };

    const handleStatusChange = (status) => {
      connectionStatus.value = status;

      if (status === 'disconnected' && !connecting.value) {
        showReconnectModal.value = true;
      }
    };

    const handleError = (error) => {
      addOutputLine({
        content: `Error: ${error}`,
        type: 'error',
        timestamp: new Date()
      });
      connectionStatus.value = 'error';
    };

    const addOutputLine = (line) => {
      outputLines.value.push(line);

      // Limit output lines to prevent memory issues
      if (outputLines.value.length > 10000) {
        outputLines.value = outputLines.value.slice(-8000);
      }

      nextTick(() => {
        if (terminalOutput.value) {
          terminalOutput.value.scrollTop = terminalOutput.value.scrollHeight;
        }
      });
    };

    const formatTerminalLine = (line) => {
      let content = line.content || line;

      // Remove ANSI escape sequences
      content = content
        .replace(/\x1b\[([0-9]{1,2}(;[0-9]{1,2})?)?[mGK]/g, '')
        .replace(/\r\n/g, '\n')
        .replace(/\r/g, '\n')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

      return content;
    };

    const getLineClass = (line) => {
      const classes = ['terminal-line'];

      if (line.type) {
        classes.push(`line-${line.type}`);
      }

      return classes;
    };

    // Cursor blinking effect
    const startCursorBlink = () => {
      setInterval(() => {
        showCursor.value = !showCursor.value;
      }, 500);
    };

    // Handle window resize
    const handleResize = () => {
      if (terminalMain.value && terminalService.isConnected(sessionId.value)) {
        const rect = terminalMain.value.getBoundingClientRect();
        const charWidth = 8; // Approximate character width
        const charHeight = 16; // Approximate character height

        const cols = Math.floor((rect.width - 20) / charWidth);
        const rows = Math.floor((rect.height - 100) / charHeight);

        terminalService.resize(sessionId.value, rows, cols);
      }
    };

    // Handle window beforeunload
    const handleBeforeUnload = (event) => {
      if (terminalService.isConnected(sessionId.value)) {
        event.preventDefault();
        event.returnValue = 'You have an active terminal session. Are you sure you want to close?';
        return event.returnValue;
      }
    };

    // Lifecycle
    onMounted(async () => {
      startCursorBlink();

      // Set window title
      document.title = `Terminal - ${sessionTitle.value}`;

      // Connect to session
      await connect();

      // Add event listeners
      window.addEventListener('resize', handleResize);
      window.addEventListener('beforeunload', handleBeforeUnload);

      // Focus input
      nextTick(() => {
        focusInput();
      });
    });

    onUnmounted(() => {
      // Clean up
      if (terminalService.isConnected(sessionId.value)) {
        terminalService.disconnect(sessionId.value);
      }

      // Remove event listeners
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('beforeunload', handleBeforeUnload);
    });

    // Watch for route changes (if session ID changes)
    watch(() => route.params.sessionId, (newSessionId) => {
      if (newSessionId && newSessionId !== sessionId.value) {
        // Disconnect from old session
        if (sessionId.value && terminalService.isConnected(sessionId.value)) {
          terminalService.disconnect(sessionId.value);
        }

        // Connect to new session
        sessionId.value = newSessionId;
        outputLines.value = [];
        connect();
      }
    });

    return {
      // Data
      sessionId,
      sessionTitle,
      outputLines,
      currentInput,
      currentPrompt,
      connectionStatus,
      connecting,
      showCursor,
      showReconnectModal,

      // Refs
      terminalMain,
      terminalOutput,
      terminalInput,

      // Computed
      canInput,
      connectionStatusText,

      // Methods
      connect,
      reconnect,
      sendCommand,
      handleKeydown,
      clearTerminal,
      focusInput,
      closeWindow,
      downloadLog,
      shareSession,
      hideReconnectModal,
      formatTerminalLine,
      getLineClass
    };
  }
};
</script>

<style scoped>
.terminal-window-standalone {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background-color: #000;
  color: #ffffff;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  overflow: hidden;
}

.window-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #2d2d2d;
  padding: 8px 16px;
  border-bottom: 1px solid #333;
  user-select: none;
}

.window-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
}

.terminal-icon {
  font-size: 16px;
}

.window-controls {
  display: flex;
  gap: 8px;
}

.control-button {
  background-color: #444;
  border: 1px solid #666;
  color: #fff;
  padding: 4px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.control-button:hover:not(:disabled) {
  background-color: #555;
  transform: translateY(-1px);
}

.control-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.control-button.danger:hover:not(:disabled) {
  background-color: #dc3545;
}

.terminal-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #1e1e1e;
  padding: 4px 16px;
  border-bottom: 1px solid #333;
  font-size: 11px;
  color: #888;
}

.status-left, .status-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #dc3545;
}

.connection-status.connected .status-dot {
  background-color: #28a745;
}

.connection-status.connecting .status-dot {
  background-color: #ffc107;
  animation: pulse 1s infinite;
}

.connection-status.error .status-dot {
  background-color: #dc3545;
  animation: flash 0.5s infinite;
}

.terminal-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.terminal-output {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-all;
}

.terminal-line {
  margin: 0;
  padding: 0;
  min-height: 1.4em;
}

.line-error {
  color: #ff6b6b;
}

.line-warning {
  color: #ffc107;
}

.line-success {
  color: #28a745;
}

.line-command {
  color: #87ceeb;
}

.line-system {
  color: #9370db;
}

.terminal-input-line {
  display: flex;
  align-items: center;
  padding: 0 16px 16px 16px;
  background-color: #000;
}

.prompt {
  color: #00ff00;
  margin-right: 8px;
  flex-shrink: 0;
}

.terminal-input {
  background: none;
  border: none;
  color: #fff;
  font-family: inherit;
  font-size: inherit;
  outline: none;
  flex: 1;
  min-width: 0;
}

.cursor {
  color: #00ff00;
  font-weight: bold;
  margin-left: 2px;
}

.cursor.blink {
  animation: blink 1s infinite;
}

.terminal-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #2d2d2d;
  padding: 6px 16px;
  border-top: 1px solid #333;
  font-size: 11px;
}

.footer-info {
  color: #888;
}

.footer-actions {
  display: flex;
  gap: 8px;
}

.footer-button {
  background-color: #444;
  border: 1px solid #666;
  color: #ccc;
  padding: 3px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 10px;
  transition: background-color 0.2s;
}

.footer-button:hover {
  background-color: #555;
}

/* Modal styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background-color: #2d2d2d;
  color: #fff;
  padding: 24px;
  border-radius: 8px;
  max-width: 400px;
  width: 90%;
  text-align: center;
}

.modal-content h3 {
  margin-top: 0;
  color: #ffc107;
}

.modal-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 20px;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.2s;
}

.btn-primary {
  background-color: #007acc;
  color: white;
}

.btn-primary:hover {
  background-color: #005999;
}

.btn-secondary {
  background-color: #6c757d;
  color: white;
}

.btn-secondary:hover {
  background-color: #5a6268;
}

/* Animations */
@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@keyframes flash {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* Scrollbar styling */
.terminal-output::-webkit-scrollbar {
  width: 8px;
}

.terminal-output::-webkit-scrollbar-track {
  background: #1e1e1e;
}

.terminal-output::-webkit-scrollbar-thumb {
  background: #555;
  border-radius: 4px;
}

.terminal-output::-webkit-scrollbar-thumb:hover {
  background: #777;
}

/* Responsive */
@media (max-width: 768px) {
  .window-header {
    padding: 6px 12px;
  }

  .terminal-status-bar {
    padding: 3px 12px;
  }

  .terminal-output {
    padding: 12px;
    font-size: 12px;
  }

  .terminal-input-line {
    padding: 0 12px 12px 12px;
  }

  .footer-info {
    display: none; /* Hide on mobile */
  }
}
</style>
