<template>
  <div class="terminal-window-standalone">
    <div class="window-header">
      <div class="window-title">
        <span class="terminal-icon">⬛</span>
        <span>Terminal - {{ sessionTitle }}</span>
      </div>
      <div class="window-controls">
        <!-- Emergency Kill Button -->
        <button
          class="control-button emergency-kill"
          @click="emergencyKillAll"
          :disabled="!hasRunningProcesses"
          title="EMERGENCY KILL - Stop all running processes immediately"
        >
          🛑 KILL
        </button>

        <!-- Session Takeover / Pause Automation -->
        <button
          class="control-button takeover"
          @click="toggleAutomationPause"
          :class="{ 'active': automationPaused }"
          :disabled="!hasAutomatedWorkflow"
          :title="automationPaused ? 'Resume automated workflow' : 'Pause automation and take manual control'"
        >
          {{ automationPaused ? '▶️ RESUME' : '⏸️ PAUSE' }}
        </button>

        <!-- Interrupt Current Process -->
        <button
          class="control-button interrupt"
          @click="interruptProcess"
          :disabled="!hasActiveProcess"
          title="Send Ctrl+C to interrupt current process"
        >
          ⚡ INT
        </button>

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
       tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
        <div
          v-for="(line, index) in outputLines"
          :key="index"
          class="terminal-line"
          :class="getLineClass(line)"
          v-html="formatTerminalLine(line)"
        ></div>

        <div class="terminal-input-wrapper">
          <CompletionSuggestions
            :items="tabCompletion.suggestions.value"
            :selected-index="tabCompletion.selectedIndex.value"
            :visible="tabCompletion.isVisible.value"
            @select="handleCompletionSelect"
          />
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
    </div>

    <div class="terminal-footer">
      <div class="footer-info">
        <span>Press Ctrl+C to interrupt, Ctrl+D to exit</span>
      </div>
      <div class="footer-actions">
        <button
          class="footer-button workflow-test"
          @click="startExampleWorkflow"
          title="Start Example Automated Workflow (for testing)"
          v-if="!hasAutomatedWorkflow"
        >
          🤖 Test Workflow
        </button>
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
    <div v-if="showReconnectModal" class="modal-overlay" @click="hideReconnectModal" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
      <div class="modal-content" @click.stop tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
        <h3>Connection Lost</h3>
        <p>The terminal connection was lost. Would you like to reconnect?</p>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="hideReconnectModal" aria-label="Cancel">
            Cancel
          </button>
          <button class="btn btn-primary" @click="reconnect" aria-label="Reconnect">
            Reconnect
          </button>
        </div>
      </div>
    </div>

    <!-- Command Confirmation Modal -->
    <div v-if="showCommandConfirmation" class="confirmation-modal-overlay" @click="cancelCommand" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
      <div class="confirmation-modal" @click.stop tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
        <div class="modal-header">
          <h3 class="modal-title">⚠️ Potentially Destructive Command</h3>
        </div>
        <div class="modal-content">
          <div class="command-preview">
            <div class="command-label">Command to execute:</div>
            <div class="command-text">{{ pendingCommand }}</div>
          </div>

          <div class="risk-assessment">
            <div class="risk-level" :class="pendingCommandRisk">
              Risk Level: <strong>{{ pendingCommandRisk.toUpperCase() }}</strong>
            </div>
            <div class="risk-reasons">
              <div v-for="reason in pendingCommandReasons" :key="reason" class="risk-reason">
                • {{ reason }}
              </div>
            </div>
          </div>

          <div class="confirmation-message">
            <p><strong>This command may:</strong></p>
            <ul>
              <li>Delete files or directories permanently</li>
              <li>Modify system configurations</li>
              <li>Change file permissions or ownership</li>
              <li>Install or remove software packages</li>
            </ul>
            <p><strong>Are you sure you want to proceed?</strong></p>
          </div>
        </div>

        <div class="modal-actions">
          <button
            class="btn btn-danger"
            @click="executeConfirmedCommand"
           aria-label="⚡ execute command">
            ⚡ Execute Command
          </button>
          <button
            class="btn btn-secondary"
            @click="cancelCommand"
           aria-label="❌ cancel">
            ❌ Cancel
          </button>
        </div>
      </div>
    </div>

    <!-- Emergency Kill Confirmation Modal -->
    <div v-if="showKillConfirmation" class="confirmation-modal-overlay" @click="showKillConfirmation = false" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
      <div class="confirmation-modal emergency" @click.stop tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
        <div class="modal-header">
          <h3 class="modal-title">🛑 Emergency Kill All Processes</h3>
        </div>
        <div class="modal-content">
          <div class="emergency-warning">
            <p><strong>⚠️ WARNING: This will immediately terminate ALL running processes in this terminal session!</strong></p>
            <p>Running processes:</p>
            <ul>
              <li v-for="process in runningProcesses" :key="process.pid" class="process-item">
                PID {{ process.pid }}: {{ process.command }}
              </li>
            </ul>
            <p><strong>This action cannot be undone. Continue?</strong></p>
          </div>
        </div>

        <div class="modal-actions">
          <button
            class="btn btn-danger"
            @click="confirmEmergencyKill"
           aria-label="🛑 kill all processes">
            🛑 KILL ALL PROCESSES
          </button>
          <button
            class="btn btn-secondary"
            @click="showKillConfirmation = false"
           aria-label="❌ cancel">
            ❌ Cancel
          </button>
        </div>
      </div>
    </div>

    <!-- Advanced Step Confirmation Modal -->
    <AdvancedStepConfirmationModal
      :visible="showManualStepModal"
      :current-step="pendingWorkflowStep"
      :current-step-index="currentWorkflowStep"
      :workflow-steps="workflowSteps"
      :session-id="sessionId"
      @execute-step="executeConfirmedStep"
      @skip-step="skipCurrentStep"
      @take-manual-control="takeManualControl"
      @execute-all="executeAllRemainingSteps"
      @save-workflow="saveCustomWorkflow"
      @update-workflow="updateWorkflowSteps"
      @close="closeAdvancedModal"
    />

    <!-- Legacy Manual Step Confirmation Modal (fallback) -->
    <div v-if="showLegacyModal" class="confirmation-modal-overlay" @click="takeManualControl" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
      <div class="confirmation-modal workflow-step" @click.stop tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
        <div class="modal-header">
          <h3 class="modal-title">🤖 AI Workflow Step Confirmation</h3>
        </div>
        <div class="modal-content">
          <div class="workflow-step-info" v-if="pendingWorkflowStep">
            <div class="step-counter">
              Step {{ pendingWorkflowStep.stepNumber }} of {{ pendingWorkflowStep.totalSteps }}
            </div>

            <div class="step-description">
              <h4>{{ pendingWorkflowStep.description }}</h4>
              <p>{{ pendingWorkflowStep.explanation || 'The AI wants to execute the following command:' }}</p>
            </div>

            <div class="command-preview">
              <div class="command-label">Command to Execute:</div>
              <div class="command-text">{{ pendingWorkflowStep.command }}</div>
            </div>

            <div class="workflow-options">
              <div class="option-info">
                <p><strong>Choose your action:</strong></p>
                <ul>
                  <li><strong>Execute:</strong> Run this command and continue to next step</li>
                  <li><strong>Skip:</strong> Skip this command and continue to next step</li>
                  <li><strong>Take Control:</strong> Pause automation and perform manual steps</li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        <div class="modal-actions workflow-actions">
          <button
            class="btn btn-success"
            @click="confirmWorkflowStep"
           aria-label="✅ execute & continue">
            ✅ Execute & Continue
          </button>
          <button
            class="btn btn-warning"
            @click="skipWorkflowStep"
           aria-label="⏭️ skip this step">
            ⏭️ Skip This Step
          </button>
          <button
            class="btn btn-primary"
            @click="takeManualControl"
           aria-label="👤 take manual control">
            👤 Take Manual Control
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { useTerminalService } from '@/services/TerminalService';
import { useRoute, useRouter } from 'vue-router';
import AdvancedStepConfirmationModal from './AdvancedStepConfirmationModal.vue';
import CompletionSuggestions from './CompletionSuggestions.vue';
import { createLogger } from '@/utils/debugUtils';
import { useTabCompletion } from '@/composables/useTabCompletion';

const logger = createLogger('TerminalWindow');

export default {
  name: 'TerminalWindow',
  components: {
    AdvancedStepConfirmationModal,
    CompletionSuggestions
  },
  setup() {
    const route = useRoute();
    const router = useRouter();

    // Get the terminal service with all its methods
    const {
      sendInput,
      sendSignal,
      isConnected,
      resize,
      connect: connectToService,
      disconnect,
      createSession,
      closeSession
    } = useTerminalService();

    // Get current chat ID from parent or route params
    const getCurrentChatId = () => {
      // Try to get from route params first
      if (route?.params?.sessionId) {
        return route.params.sessionId;
      }
      if (route?.query?.sessionId) {
        return route.query.sessionId;
      }

      // Try to get current chat ID from localStorage or session storage
      const storedChatId = localStorage.getItem('currentChatId');
      if (storedChatId && storedChatId !== 'null') {
        return storedChatId;
      }

      // Generate a new chat-specific terminal session ID
      const timestamp = Date.now();
      const newChatId = `chat_${timestamp}`;
      localStorage.setItem('currentChatId', newChatId);
      return newChatId;
    };

    const sessionId = ref(getCurrentChatId());
    const sessionTitle = ref(route?.query?.title || 'Terminal');
    const outputLines = ref([]);
    const currentInput = ref('');
    const currentPrompt = ref('$ ');
    const connectionStatus = ref('disconnected');
    const connecting = ref(false);
    const showCursor = ref(true);
    const showReconnectModal = ref(false);
    const commandHistory = ref([]);
    const historyIndex = ref(-1);

    // Safety and control state
    const showCommandConfirmation = ref(false);
    const showKillConfirmation = ref(false);
    const pendingCommand = ref('');
    const pendingCommandRisk = ref('low');
    const pendingCommandReasons = ref([]);
    const runningProcesses = ref([]);
    const hasActiveProcess = ref(false);

    // Automation control state
    const automationPaused = ref(false);
    const hasAutomatedWorkflow = ref(false);
    const currentWorkflowStep = ref(0);
    const workflowSteps = ref([]);
    const showManualStepModal = ref(false);
    const showLegacyModal = ref(false);
    const pendingWorkflowStep = ref(null);
    const automationQueue = ref([]);
    const waitingForUserConfirmation = ref(false);

    // Advanced workflow management state
    const isAdvancedMode = ref(true); // Use advanced modal by default
    const workflowTemplates = ref([]);
    const passwordPromptActive = ref(false);
    const currentPasswordPrompt = ref(null);

    // Tab completion (Issue #503)
    const tabCompletion = useTabCompletion({ commandHistory });

    // Refs
    const terminalMain = ref(null);
    const terminalOutput = ref(null);
    const terminalInput = ref(null);

    // Computed properties
    const canInput = computed(() => {
      // Only allow input when connected AND terminal is ready AND not waiting for user input
      return connectionStatus.value === 'connected' &&
             !connecting.value &&
             !waitingForUserConfirmation.value;
    });
    const hasRunningProcesses = computed(() => runningProcesses.value.length > 0);
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
        logger.error('No session ID provided');
        return;
      }

      connecting.value = true;
      connectionStatus.value = 'connecting';

      try {
        await connectToService(sessionId.value, {
          onOutput: handleOutput,
          onPromptChange: handlePromptChange,
          onStatusChange: handleStatusChange,
          onError: handleError
        });
      } catch (error) {
        logger.error('Failed to connect:', error);
        handleError(error.message);
      } finally {
        connecting.value = false;
      }
    };

    const reconnect = async () => {
      hideReconnectModal();

      // Disconnect first if connected
      if (isConnected(sessionId.value)) {
        disconnect(sessionId.value);
      }

      // Clear output and reset state
      outputLines.value = [];
      currentPrompt.value = '$ ';

      // Attempt to reconnect
      await connect();
    };

    // Enhanced sendCommand with safety checks
    const sendCommand = () => {
      tabCompletion.dismiss();
      if (!currentInput.value.trim() || !canInput.value) return;

      const command = currentInput.value.trim();

      // Check if command is potentially destructive
      const riskAssessment = assessCommandRisk(command);

      if (riskAssessment.risk === 'high' || riskAssessment.risk === 'critical') {
        // Show confirmation modal for dangerous commands
        pendingCommand.value = command;
        pendingCommandRisk.value = riskAssessment.risk;
        pendingCommandReasons.value = riskAssessment.reasons;
        showCommandConfirmation.value = true;
        return;
      }

      // Execute safe commands immediately
      executeCommand(command);
    };

    // Execute command after safety checks
    const executeCommand = (command) => {
      // Add to command history
      if (command && (!commandHistory.value.length || commandHistory.value[commandHistory.value.length - 1] !== command)) {
        commandHistory.value.push(command);
        if (commandHistory.value.length > 100) {
          commandHistory.value = commandHistory.value.slice(-100);
        }
      }
      historyIndex.value = commandHistory.value.length;

      // Track process start
      if (isProcessStartCommand(command)) {
        hasActiveProcess.value = true;
        addRunningProcess(command);
      }

      // Send to terminal
      sendInput(sessionId.value, command);

      // Clear input
      currentInput.value = '';

      // Add command to output for immediate feedback
      addOutputLine({
        content: `${currentPrompt.value}${command}`,
        type: 'command',
        timestamp: new Date(),
        risk: pendingCommandRisk.value || 'low'
      });
    };

    // Command risk assessment
    const assessCommandRisk = (command) => {
      const lowerCmd = command.toLowerCase().trim();

      // Critical risk patterns (system destruction)
      const criticalPatterns = [
        /rm\s+-rf\s+\/($|\s)/,  // rm -rf /
        /dd\s+if=.*of=\/dev\/[sh]d/,  // dd to disk
        /mkfs\./,  // format filesystem
        /fdisk.*\/dev\/[sh]d/,  // disk partitioning
        />(\/etc\/passwd|\/etc\/shadow)/,  // overwrite critical files
      ];

      // High risk patterns (data loss, system changes)
      const highRiskPatterns = [
        /rm\s+-rf/,  // recursive force delete
        /chmod\s+777.*\/$/,  // chmod 777 on root
        /chown.*\/$/,  // chown on root
        /rm\s+.*\/etc\//,  // delete config files
        /sudo\s+rm/,  // sudo rm
        />\s*\/dev\/null.*&&.*rm/,  // redirect and delete
        /killall\s+-9/,  // kill all processes
        /reboot|shutdown\s+-h/,  // system restart/shutdown
        /iptables\s+-F/,  // flush firewall rules
        /userdel|groupdel/,  // delete users/groups
      ];

      // Moderate risk patterns (installations, configuration)
      const moderateRiskPatterns = [
        /sudo\s+(apt|yum|dnf|pacman).*install/,  // package installation
        /sudo\s+(apt|yum|dnf|pacman).*remove/,   // package removal
        /sudo\s+systemctl/,  // system service control
        /sudo\s+(service|systemd)/,  // service management
        /sudo\s+mount/,  // mount filesystems
        /chmod.*[4-7][0-7][0-7]/,  // permission changes with setuid
        /sudo.*>/,  // sudo with redirection
      ];

      let risk = 'low';
      let reasons = [];

      // Check for critical patterns
      for (const pattern of criticalPatterns) {
        if (pattern.test(lowerCmd)) {
          risk = 'critical';
          reasons.push('Command could cause irreversible system damage');
          break;
        }
      }

      // Check for high risk patterns
      if (risk === 'low') {
        for (const pattern of highRiskPatterns) {
          if (pattern.test(lowerCmd)) {
            risk = 'high';
            reasons.push('Command could delete data or modify system configuration');
            break;
          }
        }
      }

      // Check for moderate risk patterns
      if (risk === 'low') {
        for (const pattern of moderateRiskPatterns) {
          if (pattern.test(lowerCmd)) {
            risk = 'moderate';
            reasons.push('Command requires elevated privileges or modifies system');
            break;
          }
        }
      }

      // Additional risk factors
      if (lowerCmd.includes('sudo')) {
        reasons.push('Command uses sudo (elevated privileges)');
      }

      if (lowerCmd.includes('>>') || lowerCmd.includes('>')) {
        reasons.push('Command redirects output (potential file modification)');
      }

      return { risk, reasons };
    };

    // Safety control methods
    const executeConfirmedCommand = () => {
      executeCommand(pendingCommand.value);
      showCommandConfirmation.value = false;
      pendingCommand.value = '';
      pendingCommandRisk.value = 'low';
      pendingCommandReasons.value = [];
    };

    const cancelCommand = () => {
      showCommandConfirmation.value = false;
      pendingCommand.value = '';
      pendingCommandRisk.value = 'low';
      pendingCommandReasons.value = [];
      currentInput.value = ''; // Clear the input
    };

    const emergencyKillAll = () => {
      if (runningProcesses.value.length === 0) {
        return; // No processes to kill
      }
      showKillConfirmation.value = true;
    };

    const confirmEmergencyKill = async () => {
      try {
        // Send SIGKILL to all processes in the terminal session
        await sendInput(sessionId.value, '\u0003\u0003\u0003'); // Multiple Ctrl+C

        // Force kill all tracked processes
        for (const process of runningProcesses.value) {
          try {
            await sendSignal(sessionId.value, 'SIGKILL', process.pid);
          } catch (error) {
            logger.warn(`Failed to kill process ${process.pid}:`, error);
          }
        }

        // Clear all process tracking
        runningProcesses.value = [];
        hasActiveProcess.value = false;

        // Add emergency kill message to terminal
        addOutputLine({
          content: '🛑 EMERGENCY KILL: All processes terminated by user',
          type: 'system_message',
          timestamp: new Date()
        });

        showKillConfirmation.value = false;

      } catch (error) {
        logger.error('Emergency kill failed:', error);
        addOutputLine({
          content: '❌ Emergency kill failed: ' + error.message,
          type: 'error',
          timestamp: new Date()
        });
      }
    };

    const interruptProcess = () => {
      if (!hasActiveProcess.value) return;

      // Send Ctrl+C (SIGINT) to interrupt current process
      sendInput(sessionId.value, '\u0003');

      addOutputLine({
        content: '^C (Process interrupted by user)',
        type: 'system_message',
        timestamp: new Date()
      });
    };

    // Process tracking helpers
    const isProcessStartCommand = (command) => {
      const processStartPatterns = [
        /^(vim|nano|emacs|less|more|top|htop|tail\s+-f)/,  // interactive programs
        /&\s*$/,  // background processes
        /^(python|node|java|go)/,  // program execution
        /^(ssh|scp|rsync)/,  // network operations
        /^(find|grep|sort).*\|/,  // long-running pipes
      ];

      return processStartPatterns.some(pattern => pattern.test(command.toLowerCase()));
    };

    const addRunningProcess = (command) => {
      const process = {
        pid: Date.now(), // Simplified PID (in real implementation, get actual PID)
        command: command,
        startTime: new Date()
      };

      runningProcesses.value.push(process);
    };

    // Automation Control Methods
    const toggleAutomationPause = () => {
      automationPaused.value = !automationPaused.value;

      if (automationPaused.value) {
        // Pause automation - user takes control
        addOutputLine({
          content: '⏸️ AUTOMATION PAUSED - Manual control activated. Type commands freely.',
          type: 'system_message',
          timestamp: new Date()
        });

        // Notify backend about pause
        sendAutomationControl('pause');

      } else {
        // Resume automation
        addOutputLine({
          content: '▶️ AUTOMATION RESUMED - Continuing workflow execution.',
          type: 'system_message',
          timestamp: new Date()
        });

        // Resume any pending automation steps
        sendAutomationControl('resume');

        // Continue with next step if available
        if (automationQueue.value.length > 0) {
          processNextAutomationStep();
        }
      }
    };

    const sendAutomationControl = async (action) => {
      try {
        // Send automation control signal to backend
        const controlMessage = {
          type: 'automation_control',
          action: action,
          sessionId: sessionId.value,
          timestamp: new Date().toISOString()
        };

        await sendInput(sessionId.value, JSON.stringify(controlMessage));

      } catch (error) {
        logger.error('Failed to send automation control:', error);
      }
    };

    const requestManualStepConfirmation = (stepInfo) => {
      pendingWorkflowStep.value = stepInfo;
      showManualStepModal.value = true;
      waitingForUserConfirmation.value = true;

      addOutputLine({
        content: `🤖 AI WORKFLOW: About to execute "${stepInfo.command}"`,
        type: 'system_message',
        timestamp: new Date()
      });

      addOutputLine({
        content: `📋 Step ${stepInfo.stepNumber}/${stepInfo.totalSteps}: ${stepInfo.description}`,
        type: 'workflow_info',
        timestamp: new Date()
      });
    };

    const confirmWorkflowStep = () => {
      if (pendingWorkflowStep.value) {
        // Execute the pending step
        executeAutomatedCommand(pendingWorkflowStep.value.command);

        // Close modal and continue
        showManualStepModal.value = false;
        waitingForUserConfirmation.value = false;
        pendingWorkflowStep.value = null;

        // Schedule next step
        scheduleNextAutomationStep();
      }
    };

    const skipWorkflowStep = () => {
      if (pendingWorkflowStep.value) {
        addOutputLine({
          content: `⏭️ SKIPPED: ${pendingWorkflowStep.value.command}`,
          type: 'system_message',
          timestamp: new Date()
        });

        // Close modal
        showManualStepModal.value = false;
        waitingForUserConfirmation.value = false;
        pendingWorkflowStep.value = null;

        // Continue with next step
        scheduleNextAutomationStep();
      }
    };

    const takeManualControl = () => {
      // User wants to do manual steps before continuing
      automationPaused.value = true;
      showManualStepModal.value = false;
      waitingForUserConfirmation.value = false;

      addOutputLine({
        content: '👤 MANUAL CONTROL TAKEN - Complete your manual steps, then click RESUME to continue workflow.',
        type: 'system_message',
        timestamp: new Date()
      });

      // Keep the pending step for later
      if (pendingWorkflowStep.value) {
        automationQueue.value.unshift(pendingWorkflowStep.value);
        pendingWorkflowStep.value = null;
      }
    };

    const executeAutomatedCommand = (command) => {
      // Mark as automated execution
      addOutputLine({
        content: `🤖 AUTOMATED: ${command}`,
        type: 'automated_command',
        timestamp: new Date()
      });

      // Execute the command
      sendInput(sessionId.value, command);

      // Track the automated process
      hasActiveProcess.value = true;
      addRunningProcess(`[AUTO] ${command}`);
    };

    const processNextAutomationStep = () => {
      if (automationQueue.value.length > 0 && !automationPaused.value) {
        const nextStep = automationQueue.value.shift();

        // Small delay between steps for readability
        setTimeout(() => {
          requestManualStepConfirmation(nextStep);
        }, 1000);
      }
    };

    const scheduleNextAutomationStep = () => {
      currentWorkflowStep.value++;

      // Small delay before next step
      setTimeout(() => {
        processNextAutomationStep();
      }, 2000);
    };

    // Enhanced command execution with automation awareness
    const executeCommandWithAutomation = (command) => {
      if (automationPaused.value || waitingForUserConfirmation.value) {
        // Manual command during paused automation
        addOutputLine({
          content: `👤 MANUAL: ${command}`,
          type: 'manual_command',
          timestamp: new Date()
        });
      }

      // Execute normally
      executeCommand(command);
    };

    // API Integration for Workflow Automation
    const startAutomatedWorkflow = (workflowData) => {
      hasAutomatedWorkflow.value = true;
      automationPaused.value = false;
      currentWorkflowStep.value = 0;
      workflowSteps.value = workflowData.steps || [];

      // Clear any previous automation queue
      automationQueue.value = [];

      // Add all steps to automation queue
      workflowData.steps.forEach((step, index) => {
        automationQueue.value.push({
          stepNumber: index + 1,
          totalSteps: workflowData.steps.length,
          command: step.command,
          description: step.description || `Execute: ${step.command}`,
          explanation: step.explanation || null,
          requiresConfirmation: step.requiresConfirmation !== false // Default to true
        });
      });

      addOutputLine({
        content: `🚀 AUTOMATED WORKFLOW STARTED: ${workflowData.name || 'Unnamed Workflow'}`,
        type: 'system_message',
        timestamp: new Date()
      });

      addOutputLine({
        content: `📋 ${workflowSteps.value.length} steps planned. Use PAUSE button to take manual control at any time.`,
        type: 'workflow_info',
        timestamp: new Date()
      });

      // Start the first step
      setTimeout(() => {
        processNextAutomationStep();
      }, 1500);
    };

    // Example workflow for testing
    const startExampleWorkflow = () => {
      const exampleWorkflow = {
        name: "System Update and Package Installation",
        steps: [
          {
            command: "sudo apt update",
            description: "Update package repositories",
            explanation: "This updates the list of available packages from configured repositories.",
            requiresConfirmation: true
          },
          {
            command: "sudo apt upgrade -y",
            description: "Upgrade installed packages",
            explanation: "This upgrades all installed packages to their latest versions.",
            requiresConfirmation: true
          },
          {
            command: "sudo apt install -y git curl wget",
            description: "Install essential tools",
            explanation: "Install commonly needed development tools.",
            requiresConfirmation: true
          },
          {
            command: "git --version && curl --version",
            description: "Verify installations",
            explanation: "Check that the tools were installed correctly.",
            requiresConfirmation: false
          }
        ]
      };

      startAutomatedWorkflow(exampleWorkflow);
    };

    // Listen for workflow events from backend
    const handleWorkflowMessage = (message) => {
      try {
        const data = JSON.parse(message);

        if (data.type === 'start_workflow') {
          startAutomatedWorkflow(data.workflow);
        } else if (data.type === 'pause_workflow') {
          automationPaused.value = true;
          addOutputLine({
            content: '⏸️ WORKFLOW PAUSED BY SYSTEM',
            type: 'system_message',
            timestamp: new Date()
          });
        } else if (data.type === 'resume_workflow') {
          automationPaused.value = false;
          addOutputLine({
            content: '▶️ WORKFLOW RESUMED BY SYSTEM',
            type: 'system_message',
            timestamp: new Date()
          });
          processNextAutomationStep();
        }
      } catch (error) {
        logger.warn('Failed to parse workflow message:', error);
      }
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
          {
            const cursorPos = terminalInput.value?.selectionStart ?? currentInput.value.length;
            const result = tabCompletion.complete(currentInput.value, cursorPos);
            if (result !== null) {
              currentInput.value = result;
            }
          }
          break;

        case 'Escape':
          if (tabCompletion.isVisible.value) {
            event.preventDefault();
            tabCompletion.dismiss();
          }
          break;

        case 'Enter':
          if (tabCompletion.isVisible.value) {
            event.preventDefault();
            const accepted = tabCompletion.acceptSelected(currentInput.value);
            if (accepted !== null) {
              currentInput.value = accepted;
            }
            return;
          }
          break;

        case 'c':
          if (event.ctrlKey) {
            event.preventDefault();
            sendSignal(sessionId.value, 'SIGINT');
          }
          break;

        case 'd':
          if (event.ctrlKey && !currentInput.value) {
            event.preventDefault();
            sendInput(sessionId.value, 'exit');
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
        // Ensure input is properly focused for automated testing
        nextTick(() => {
          if (terminalInput.value && document.activeElement !== terminalInput.value) {
            terminalInput.value.focus();
          }
        });
      }
    };

    const closeWindow = () => {
      if (confirm('Are you sure you want to close this terminal window?')) {
        if (isConnected(sessionId.value)) {
          disconnect(sessionId.value);
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
          if (error?.name !== 'AbortError') {
            logger.warn('Share failed:', error);
          }
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
      const oldStatus = connectionStatus.value;
      connectionStatus.value = status;

      logger.info(`Terminal status change: ${oldStatus} -> ${status}`);

      if (status === 'connected') {
        // Mark as not connecting anymore
        connecting.value = false;

        // Ensure input is focused and interactive when connection is established
        nextTick(() => {
          // Wait for canInput computed to update
          setTimeout(() => {
            if (canInput.value) {
              focusInput();
              // Additional focus attempt for automated testing reliability
              setTimeout(() => {
                if (canInput.value && terminalInput.value && document.activeElement !== terminalInput.value) {
                  focusInput();
                }
              }, 200);
            }
          }, 50);
        });
      } else if (status === 'disconnected' && !connecting.value) {
        showReconnectModal.value = true;
      } else if (status === 'connecting') {
        connecting.value = true;
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
      if (terminalMain.value && isConnected(sessionId.value)) {
        const rect = terminalMain.value.getBoundingClientRect();
        const charWidth = 8; // Approximate character width
        const charHeight = 16; // Approximate character height

        const cols = Math.floor((rect.width - 20) / charWidth);
        const rows = Math.floor((rect.height - 100) / charHeight);

        resize(sessionId.value, rows, cols);
      }
    };

    // Handle window beforeunload
    const handleBeforeUnload = (event) => {
      if (isConnected(sessionId.value)) {
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

      // Enhanced focus handling for automated testing
      nextTick(() => {
        focusInput();

        // Add additional focus recovery mechanisms for automated testing
        document.addEventListener('click', (event) => {
          // If click is inside terminal area but not on input, restore focus
          const terminalArea = document.querySelector('.terminal-window-standalone');
          if (terminalArea && terminalArea.contains(event.target) &&
              event.target !== terminalInput.value && canInput.value) {
            nextTick(() => focusInput());
          }
        });

        // Periodic focus check for automation scenarios (clean up on unmount)
        const focusInterval = setInterval(() => {
          if (canInput.value && terminalInput.value &&
              document.activeElement !== terminalInput.value &&
              document.querySelector('.terminal-window-standalone')) {
            focusInput();
          }
        }, 1000);

        // Store interval for cleanup
        window.terminalFocusInterval = focusInterval;
      });
    });

    onUnmounted(() => {
      // Clean up
      if (isConnected && typeof isConnected === 'function' && isConnected(sessionId.value)) {
        disconnect(sessionId.value);
      }

      // Remove event listeners
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('beforeunload', handleBeforeUnload);

      // Clean up focus interval for automated testing
      if (window.terminalFocusInterval) {
        clearInterval(window.terminalFocusInterval);
        window.terminalFocusInterval = null;
      }
    });

    // Watch for route changes (if session ID changes)
    watch(() => route.params.sessionId, (newSessionId) => {
      if (newSessionId && newSessionId !== sessionId.value) {
        // Disconnect from old session
        if (sessionId.value && isConnected(sessionId.value)) {
          disconnect(sessionId.value);
        }

        // Connect to new session
        sessionId.value = newSessionId;
        outputLines.value = [];
        connect();
      }
    });

    // Handle clicking a suggestion in the dropdown
    const handleCompletionSelect = (index) => {
      tabCompletion.selectedIndex.value = index;
      const accepted = tabCompletion.acceptSelected(currentInput.value);
      if (accepted !== null) {
        currentInput.value = accepted;
      }
      nextTick(() => focusInput());
    };

    return {
      // Tab completion (Issue #503)
      tabCompletion,
      handleCompletionSelect,

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
      showCommandConfirmation,
      showKillConfirmation,
      pendingCommand,
      pendingCommandRisk,
      pendingCommandReasons,
      runningProcesses,
      hasActiveProcess,

      // Automation Control Data
      automationPaused,
      hasAutomatedWorkflow,
      currentWorkflowStep,
      workflowSteps,
      showManualStepModal,
      showLegacyModal,
      pendingWorkflowStep,
      automationQueue,
      waitingForUserConfirmation,

      // Advanced workflow state
      isAdvancedMode,
      workflowTemplates,
      passwordPromptActive,
      currentPasswordPrompt,

      // Refs
      terminalMain,
      terminalOutput,
      terminalInput,

      // Computed
      canInput,
      hasRunningProcesses,
      connectionStatusText,

      // Methods
      connect,
      reconnect,
      sendCommand,
      executeCommand,
      executeConfirmedCommand,
      cancelCommand,
      emergencyKillAll,
      confirmEmergencyKill,
      interruptProcess,

      // Automation Control Methods
      toggleAutomationPause,
      requestManualStepConfirmation,
      confirmWorkflowStep,
      skipWorkflowStep,
      takeManualControl,
      executeCommandWithAutomation,
      startAutomatedWorkflow,
      startExampleWorkflow,
      handleWorkflowMessage,

      // Advanced Modal Methods
      executeConfirmedStep: (stepData) => {
        addOutputLine({
          content: `🤖 EXECUTING: ${stepData.command}`,
          type: 'system_message',
          timestamp: new Date()
        });
        executeAutomatedCommand(stepData.command);
        scheduleNextAutomationStep();
      },
      skipCurrentStep: (stepIndex) => {
        addOutputLine({
          content: `⏭️ STEP ${stepIndex + 1} SKIPPED BY USER`,
          type: 'system_message',
          timestamp: new Date()
        });
        scheduleNextAutomationStep();
      },
      executeAllRemainingSteps: () => {
        automationPaused.value = false;
        waitingForUserConfirmation.value = false;
        processNextAutomationStep();
      },
      saveCustomWorkflow: (workflowData) => {
        addOutputLine({
          content: `💾 WORKFLOW SAVED: ${workflowData.name}`,
          type: 'system_message',
          timestamp: new Date()
        });
      },
      updateWorkflowSteps: (newSteps) => {
        workflowSteps.value = newSteps;
        addOutputLine({
          content: `📋 WORKFLOW UPDATED: ${newSteps.length} steps configured`,
          type: 'system_message',
          timestamp: new Date()
        });
      },
      closeAdvancedModal: () => {
        showManualStepModal.value = false;
        waitingForUserConfirmation.value = false;
      },
      handlePasswordPrompt: (promptData) => {
        passwordPromptActive.value = true;
        currentPasswordPrompt.value = promptData;
      },

      // Other Methods
      handleKeydown,
      clearTerminal,
      focusInput,
      closeWindow,
      downloadLog,
      shareSession,
      hideReconnectModal,
      formatTerminalLine,
      getLineClass,
      // Testing utilities for automated tests
      isTerminalReady: () => {
        const ready = canInput.value && terminalInput.value && !terminalInput.value.disabled;
        logger.info(`Terminal ready check: canInput=${canInput.value}, hasInput=${!!terminalInput.value}, enabled=${terminalInput.value ? !terminalInput.value.disabled : false}, result=${ready}`);
        return ready;
      },
      ensureInputFocus: () => {
        if (canInput.value && terminalInput.value) {
          logger.info('Ensuring terminal input focus...');
          terminalInput.value.focus();
          const focused = document.activeElement === terminalInput.value;
          logger.info(`Focus result: ${focused}`);
          return focused;
        }
        logger.info('Cannot ensure focus: canInput=', canInput.value, 'hasInput=', !!terminalInput.value);
        return false;
      },
      // Additional debug utility for automated testing
      getDebugInfo: () => {
        return {
          canInput: canInput.value,
          connectionStatus: connectionStatus.value,
          connecting: connecting.value,
          waitingForUserConfirmation: waitingForUserConfirmation.value,
          hasTerminalInput: !!terminalInput.value,
          inputDisabled: terminalInput.value ? terminalInput.value.disabled : null,
          activeElement: document.activeElement?.className || 'none',
          isInputFocused: document.activeElement === terminalInput.value
        };
      }
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

.terminal-input-wrapper {
  position: relative;
  flex-shrink: 0;
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

.footer-button.workflow-test {
  background-color: #17a2b8;
  border-color: #138496;
  color: white;
  font-weight: 600;
}

.footer-button.workflow-test:hover {
  background-color: #138496;
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

.btn-danger {
  background-color: #dc3545;
  color: white;
}

.btn-danger:hover {
  background-color: #c82333;
}

/* Emergency control button styles */
.control-button.emergency-kill {
  background-color: #dc3545;
  color: white;
  font-weight: bold;
  border-color: #c82333;
}

.control-button.emergency-kill:hover:not(:disabled) {
  background-color: #c82333;
  border-color: #bd2130;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(220, 53, 69, 0.3);
}

.control-button.interrupt {
  background-color: #ffc107;
  color: #212529;
  border-color: #e0a800;
}

.control-button.interrupt:hover:not(:disabled) {
  background-color: #e0a800;
  border-color: #d39e00;
}

.control-button.takeover {
  background-color: #17a2b8;
  color: white;
  border-color: #138496;
  font-weight: 600;
}

.control-button.takeover:hover:not(:disabled) {
  background-color: #138496;
  border-color: #0c7084;
}

.control-button.takeover.active {
  background-color: #28a745;
  border-color: #1e7e34;
  animation: pulse-success 2s infinite;
}

.control-button.takeover.active:hover {
  background-color: #218838;
}

/* Command confirmation modal styles */
.confirmation-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  backdrop-filter: blur(2px);
}

.confirmation-modal {
  background-color: #2d2d2d;
  color: #fff;
  padding: 0;
  border-radius: 12px;
  max-width: 600px;
  width: 90%;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  border: 1px solid #444;
}

.confirmation-modal.emergency {
  border-color: #dc3545;
  box-shadow: 0 10px 30px rgba(220, 53, 69, 0.3);
}

.modal-header {
  padding: 20px 24px 16px 24px;
  border-bottom: 1px solid #444;
  background: linear-gradient(135deg, #333 0%, #2d2d2d 100%);
  border-radius: 12px 12px 0 0;
}

.modal-title {
  margin: 0;
  color: #ffc107;
  font-size: 18px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.confirmation-modal.emergency .modal-title {
  color: #ff6b6b;
}

.modal-content {
  padding: 24px;
}

.command-preview {
  background-color: #1e1e1e;
  border: 1px solid #444;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
}

.command-label {
  font-size: 12px;
  color: #888;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.command-text {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 14px;
  color: #87ceeb;
  background-color: #000;
  padding: 12px;
  border-radius: 6px;
  border-left: 4px solid #ffc107;
  white-space: pre-wrap;
  word-break: break-all;
}

.risk-assessment {
  margin-bottom: 20px;
}

.risk-level {
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
}

.risk-level.low {
  background-color: rgba(40, 167, 69, 0.2);
  color: #28a745;
  border: 1px solid #28a745;
}

.risk-level.moderate {
  background-color: rgba(255, 193, 7, 0.2);
  color: #ffc107;
  border: 1px solid #ffc107;
}

.risk-level.high {
  background-color: rgba(255, 107, 107, 0.2);
  color: #ff6b6b;
  border: 1px solid #ff6b6b;
}

.risk-level.critical {
  background-color: rgba(220, 53, 69, 0.3);
  color: #ff4757;
  border: 1px solid #dc3545;
  animation: pulse-danger 2s infinite;
}

.risk-reasons {
  color: #ccc;
}

.risk-reason {
  margin-bottom: 4px;
  font-size: 13px;
}

.confirmation-message {
  color: #ddd;
}

.confirmation-message p {
  margin-bottom: 12px;
}

.confirmation-message ul {
  margin: 12px 0;
  padding-left: 20px;
}

.confirmation-message li {
  margin-bottom: 6px;
  color: #ccc;
}

.emergency-warning {
  color: #ff6b6b;
}

.emergency-warning p {
  margin-bottom: 12px;
  font-weight: 500;
}

.process-item {
  background-color: #1e1e1e;
  padding: 8px 12px;
  border-radius: 4px;
  margin-bottom: 4px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
  color: #87ceeb;
}

.modal-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding: 20px 24px;
  border-top: 1px solid #444;
  background-color: #252525;
  border-radius: 0 0 12px 12px;
}

/* Enhanced animations */
@keyframes pulse-danger {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(220, 53, 69, 0.4);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(220, 53, 69, 0);
  }
}

/* Process status indicators */
.line-system_message {
  color: #9370db;
  font-weight: 500;
}

.line-error {
  color: #ff6b6b;
}

.line-command.high {
  border-left: 3px solid #ffc107;
  background-color: rgba(255, 193, 7, 0.1);
}

.line-command.critical {
  border-left: 3px solid #dc3545;
  background-color: rgba(220, 53, 69, 0.1);
}

/* Workflow Step Modal Styles */
.confirmation-modal.workflow-step {
  max-width: 700px;
  border-color: #17a2b8;
  box-shadow: 0 10px 30px rgba(23, 162, 184, 0.3);
}

.workflow-step-info {
  text-align: left;
}

.step-counter {
  background-color: #17a2b8;
  color: white;
  padding: 8px 16px;
  border-radius: 20px;
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 16px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.step-description h4 {
  margin: 0 0 8px 0;
  color: #17a2b8;
  font-size: 16px;
  font-weight: 600;
}

.step-description p {
  margin: 0 0 16px 0;
  color: #ccc;
  font-size: 14px;
  line-height: 1.5;
}

.workflow-options {
  background-color: #1e1e1e;
  border-radius: 8px;
  padding: 16px;
  margin-top: 20px;
  border-left: 4px solid #17a2b8;
}

.option-info p {
  margin: 0 0 12px 0;
  color: #17a2b8;
  font-weight: 600;
}

.option-info ul {
  margin: 0;
  padding-left: 20px;
  color: #ccc;
}

.option-info li {
  margin-bottom: 8px;
  font-size: 13px;
  line-height: 1.4;
}

.option-info li strong {
  color: #fff;
}

.workflow-actions {
  justify-content: space-between;
  padding: 20px 24px;
}

.btn-success {
  background-color: #28a745;
  color: white;
  border: 1px solid #1e7e34;
}

.btn-success:hover {
  background-color: #218838;
  border-color: #1c7430;
}

.btn-warning {
  background-color: #ffc107;
  color: #212529;
  border: 1px solid #e0a800;
}

.btn-warning:hover {
  background-color: #e0a800;
  border-color: #d39e00;
}

/* Animation for active automation state */
@keyframes pulse-success {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(40, 167, 69, 0.4);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(40, 167, 69, 0);
  }
}

/* Terminal line styles for automation */
.line-automated_command {
  color: #17a2b8;
  font-weight: 500;
  background-color: rgba(23, 162, 184, 0.1);
  border-left: 3px solid #17a2b8;
  padding-left: 8px;
}

.line-manual_command {
  color: #28a745;
  font-weight: 500;
  background-color: rgba(40, 167, 69, 0.1);
  border-left: 3px solid #28a745;
  padding-left: 8px;
}

.line-workflow_info {
  color: #6f42c1;
  background-color: rgba(111, 66, 193, 0.1);
  border-left: 3px solid #6f42c1;
  padding-left: 8px;
  font-style: italic;
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
