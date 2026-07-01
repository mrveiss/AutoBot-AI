<template>
  <div class="terminal-window-standalone">
    <TerminalHeader
      :session-title="sessionTitle"
      :has-running-processes="hasRunningProcesses"
      :automation-paused="automationPaused"
      :has-automated-workflow="hasAutomatedWorkflow"
      :has-active-process="hasActiveProcess"
      :connecting="connecting"
      @emergency-kill="emergencyKillAll"
      @toggle-automation="toggleAutomationPause"
      @interrupt-process="interruptProcess"
      @reconnect="reconnect"
      @clear-terminal="clearTerminal"
      @close-window="closeWindow"
    />

    <div class="terminal-status-bar">
      <div class="status-left">
        <div class="connection-status" :class="connectionStatus">
          <div class="status-dot"></div>
          <span>{{ connectionStatusText }}</span>
        </div>
        <div class="session-info">
          <span>{{ t('terminal.window.session') }} {{ sessionId?.slice(0, 8) }}...</span>
        </div>
      </div>
      <div class="status-right">
        <div class="terminal-stats">
          {{ t('terminal.window.lines') }} {{ outputLines.length }}
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
        <span>{{ t('terminal.window.shortcutHint') }}</span>
      </div>
      <div class="footer-actions">
        <button
          class="footer-button workflow-test"
          @click="startExampleWorkflow"
          :title="t('terminal.window.startExampleWorkflowTitle')"
          v-if="!hasAutomatedWorkflow"
        >
          🤖 {{ t('terminal.window.testWorkflow') }}
        </button>
        <button
          class="footer-button"
          @click="downloadLog"
          :title="t('terminal.window.downloadLogTitle')"
        >
          💾 {{ t('terminal.window.saveLog') }}
        </button>
        <button
          class="footer-button"
          @click="shareSession"
          :title="t('terminal.window.shareSessionTitle')"
        >
          🔗 {{ t('terminal.window.share') }}
        </button>
      </div>
    </div>

    <!-- Connection Lost Modal -->
    <div v-if="showReconnectModal" class="modal-overlay" @click="hideReconnectModal" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
      <div class="modal-content" @click.stop tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
        <h3>{{ t('terminal.window.connectionLost') }}</h3>
        <p>{{ t('terminal.window.connectionLostMessage') }}</p>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="hideReconnectModal" :aria-label="t('terminal.window.cancel')">
            {{ t('terminal.window.cancel') }}
          </button>
          <button class="btn btn-primary" @click="reconnect" :aria-label="t('terminal.window.reconnect')">
            {{ t('terminal.window.reconnect') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Command Confirmation Modal -->
    <div v-if="showCommandConfirmation" class="confirmation-modal-overlay" @click="cancelCommand" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
      <div class="confirmation-modal" @click.stop tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
        <div class="modal-header">
          <h3 class="modal-title">⚠️ {{ t('terminal.window.destructiveCommand') }}</h3>
        </div>
        <div class="modal-content">
          <div class="command-preview">
            <div class="command-label">{{ t('terminal.window.commandToExecute') }}</div>
            <div class="command-text">{{ pendingCommand }}</div>
          </div>

          <div class="risk-assessment">
            <div class="risk-level" :class="pendingCommandRisk">
              {{ t('terminal.window.riskLevel') }} <strong>{{ pendingCommandRisk.toUpperCase() }}</strong>
            </div>
            <div class="risk-reasons">
              <div v-for="reason in pendingCommandReasons" :key="reason" class="risk-reason">
                • {{ reason }}
              </div>
            </div>
          </div>

          <div class="confirmation-message">
            <p><strong>{{ t('terminal.window.commandMay') }}</strong></p>
            <ul>
              <li>{{ t('terminal.window.riskDeleteFiles') }}</li>
              <li>{{ t('terminal.window.riskModifyConfig') }}</li>
              <li>{{ t('terminal.window.riskChangePermissions') }}</li>
              <li>{{ t('terminal.window.riskInstallRemove') }}</li>
            </ul>
            <p><strong>{{ t('terminal.window.confirmProceed') }}</strong></p>
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
          <h3 class="modal-title">🛑 {{ t('terminal.window.emergencyKillAllProcesses') }}</h3>
        </div>
        <div class="modal-content">
          <div class="emergency-warning">
            <p><strong>⚠️ {{ t('terminal.window.emergencyKillWarning') }}</strong></p>
            <p>{{ t('terminal.window.runningProcesses') }}</p>
            <ul>
              <li v-for="process in runningProcesses" :key="process.pid" class="process-item">
                PID {{ process.pid }}: {{ process.command }}
              </li>
            </ul>
            <p><strong>{{ t('terminal.window.cannotBeUndone') }}</strong></p>
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
      @close="closeAdvancedModal"
    />

    <!-- Legacy Manual Step Confirmation Modal (fallback) -->
    <div v-if="showLegacyModal" class="confirmation-modal-overlay" @click="takeManualControl" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
      <div class="confirmation-modal workflow-step" @click.stop tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
        <div class="modal-header">
          <h3 class="modal-title">🤖 {{ t('terminal.window.workflowStepConfirmation') }}</h3>
        </div>
        <div class="modal-content">
          <div class="workflow-step-info" v-if="pendingWorkflowStep">
            <div class="step-counter">
              Step {{ pendingWorkflowStep.stepNumber }} of {{ pendingWorkflowStep.totalSteps }}
            </div>

            <div class="step-description">
              <h4>{{ pendingWorkflowStep.description }}</h4>
              <p>{{ pendingWorkflowStep.explanation || t('terminal.window.aiWantsToExecute') }}</p>
            </div>

            <div class="command-preview">
              <div class="command-label">{{ t('terminal.window.commandToExecute') }}</div>
              <div class="command-text">{{ pendingWorkflowStep.command }}</div>
            </div>

            <div class="workflow-options">
              <div class="option-info">
                <p><strong>{{ t('terminal.window.chooseAction') }}</strong></p>
                <ul>
                  <li><strong>{{ t('terminal.window.executeLabel') }}</strong> {{ t('terminal.window.executeDesc') }}</li>
                  <li><strong>{{ t('terminal.window.skipLabel') }}</strong> {{ t('terminal.window.skipDesc') }}</li>
                  <li><strong>{{ t('terminal.window.takeControlLabel') }}</strong> {{ t('terminal.window.takeControlDesc') }}</li>
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
import { useI18n } from 'vue-i18n';
import { useTerminalService } from '@/services/TerminalService';
import { useRoute, useRouter } from 'vue-router';
import AdvancedStepConfirmationModal from './AdvancedStepConfirmationModal.vue';
import CompletionSuggestions from './CompletionSuggestions.vue';
import TerminalHeader from './TerminalHeader.vue';
import { createLogger } from '@/utils/debugUtils';
import { useTabCompletion } from '@/composables/useTabCompletion';
import { escapeHtml } from '@/utils/sanitize';

const logger = createLogger('TerminalWindow');

export default {
  name: 'TerminalWindow',
  components: {
    AdvancedStepConfirmationModal,
    CompletionSuggestions,
    TerminalHeader
  },
  setup() {
    const { t } = useI18n();
    const route = useRoute();
    const router = useRouter();

    // Get the terminal service with all its methods
    const {
      sendInput,
      sendSignal,
      sendTabCompletion,
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
    const sessionTitle = ref(route?.query?.title || t('terminal.window.defaultTitle'));
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
        case 'connected': return t('terminal.window.statusConnected');
        case 'connecting': return t('terminal.window.statusConnecting');
        case 'disconnected': return t('terminal.window.statusDisconnected');
        case 'error': return t('terminal.window.statusError');
        default: return t('terminal.window.statusUnknown');
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
          onError: handleError,
          onTabCompletion: handleTabCompletionResponse,
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
      const reasons = [];

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
            // Local static completion (commands + history) for instant feedback
            const result = tabCompletion.complete(currentInput.value, cursorPos);
            if (result !== null) {
              currentInput.value = result;
            }
            // Backend completion for real shell completions (Issue #3279)
            if (currentInput.value.trim() && isConnected(sessionId.value)) {
              sendTabCompletion(sessionId.value, currentInput.value, cursorPos);
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

    // Handle backend tab completion response (Issue #3279)
    const handleTabCompletionResponse = (data) => {
      const expanded = tabCompletion.registerBackendCompletions(
        currentInput.value,
        data.completions || [],
        data.prefix || '',
        data.common_prefix || '',
      );
      if (expanded !== null) {
        currentInput.value = expanded;
      }
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
        .replace(/\u001b\[([0-9]{1,2}(;[0-9]{1,2})?)?[mGK]/g, '')
        .replace(/\r\n/g, '\n')
        .replace(/\r/g, '\n');

      // HTML escape for safety
      content = escapeHtml(content);

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

    // Named click handler for focus recovery — must be named for removeEventListener (#2849)
    const handleTerminalFocusClick = (event) => {
      const terminalArea = document.querySelector('.terminal-window-standalone');
      if (terminalArea && terminalArea.contains(event.target) &&
          event.target !== terminalInput.value && canInput.value) {
        nextTick(() => focusInput());
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

        // Named click handler for focus recovery (#2849)
        document.addEventListener('click', handleTerminalFocusClick);

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
      document.removeEventListener('click', handleTerminalFocusClick);
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
      // i18n
      t,

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
  /* #10750 C2: fill the flex parent (viewport - header) instead of full viewport */
  height: 100%;
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
  padding: var(--spacing-2) var(--spacing-4);
  border-bottom: 1px solid #333;
  user-select: none;
}

.window-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  font-weight: 600;
}

.terminal-icon {
  font-size: var(--text-base);
}

.window-controls {
  display: flex;
  gap: var(--spacing-2);
}

.control-button {
  background-color: #444;
  border: 1px solid #666;
  color: #fff;
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
  cursor: pointer;
  font-size: var(--text-xs);
  transition: all var(--duration-200);
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
  background-color: var(--color-error);
}

.terminal-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #1e1e1e;
  padding: var(--spacing-1) var(--spacing-4);
  border-bottom: 1px solid #333;
  font-size: var(--text-xs);
  color: #888;
}

.status-left, .status-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.connection-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--color-error);
}

.connection-status.connected .status-dot {
  background-color: var(--color-success);
}

.connection-status.connecting .status-dot {
  background-color: var(--color-warning);
  animation: pulse 1s infinite;
}

.connection-status.error .status-dot {
  background-color: var(--color-error);
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
  padding: var(--spacing-4);
  overflow-y: auto;
  font-size: var(--text-sm);
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-all;
}

.terminal-line {
  margin: var(--spacing-0);
  padding: var(--spacing-0);
  min-height: 1.4em;
}

.line-error {
  color: #ff6b6b;
}

.line-warning {
  color: var(--color-warning);
}

.line-success {
  color: var(--color-success);
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
  padding: var(--spacing-0) var(--spacing-4) var(--spacing-4) var(--spacing-4);
  background-color: #000;
}

.prompt {
  color: #00ff00;
  margin-right: var(--spacing-2);
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

.terminal-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.cursor {
  color: #00ff00;
  font-weight: bold;
  margin-left: var(--spacing-0-5);
}

.cursor.blink {
  animation: blink 1s infinite;
}

.terminal-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #2d2d2d;
  padding: var(--spacing-1-5) var(--spacing-4);
  border-top: 1px solid #333;
  font-size: var(--text-xs);
}

.footer-info {
  color: #888;
}

.footer-actions {
  display: flex;
  gap: var(--spacing-2);
}

.footer-button {
  background-color: #444;
  border: 1px solid #666;
  color: #ccc;
  padding: 3px 8px;
  border-radius: var(--radius-default);
  cursor: pointer;
  font-size: var(--text-xs);
  transition: background-color var(--duration-200);
}

.footer-button:hover {
  background-color: #555;
}

.footer-button.workflow-test {
  background-color: var(--color-info);
  border-color: var(--color-info-hover);
  color: var(--text-on-primary);
  font-weight: 600;
}

.footer-button.workflow-test:hover {
  background-color: var(--color-info-hover);
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
  z-index: var(--z-modal);
}

.modal-content {
  background-color: #2d2d2d;
  color: #fff;
  padding: var(--spacing-6);
  border-radius: var(--radius-lg);
  max-width: 400px;
  width: 90%;
  text-align: center;
}

.modal-content h3 {
  margin-top: var(--spacing-0);
  color: var(--color-warning);
}

.modal-actions {
  display: flex;
  gap: var(--spacing-3);
  justify-content: center;
  margin-top: var(--spacing-5);
}

.btn {
  padding: var(--spacing-2) var(--spacing-4);
  border: none;
  border-radius: var(--radius-default);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: background-color var(--duration-200);
}

.btn-primary {
  background-color: var(--color-primary);
  color: var(--text-on-primary);
}

.btn-primary:hover {
  background-color: var(--color-primary-hover);
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--text-on-primary);
}

.btn-secondary:hover {
  background-color: var(--color-secondary-hover);
}

.btn-danger {
  background-color: var(--color-error);
  color: var(--text-on-error);
}

.btn-danger:hover {
  background-color: var(--color-danger-hover);
}

/* Emergency control button styles */
.control-button.emergency-kill {
  background-color: var(--color-error);
  color: var(--text-on-error);
  font-weight: bold;
  border-color: var(--color-error-hover);
}

.control-button.emergency-kill:hover:not(:disabled) {
  background-color: var(--color-error-hover);
  border-color: var(--color-error-dark);
  transform: translateY(-1px);
  box-shadow: 0 2px 4px var(--color-error-bg);
}

.control-button.interrupt {
  background-color: var(--color-warning);
  color: var(--text-on-warning);
  border-color: var(--color-warning-hover);
}

.control-button.interrupt:hover:not(:disabled) {
  background-color: var(--color-warning-hover);
  border-color: var(--color-warning-dark);
}

.control-button.takeover {
  background-color: var(--color-info);
  color: var(--text-on-primary);
  border-color: var(--color-info-hover);
  font-weight: 600;
}

.control-button.takeover:hover:not(:disabled) {
  background-color: var(--color-info-hover);
  border-color: var(--color-info-dark);
}

.control-button.takeover.active {
  background-color: var(--color-success);
  border-color: var(--color-success-hover);
  animation: pulse-success 2s infinite;
}

.control-button.takeover.active:hover {
  background-color: var(--color-success-hover);
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
  z-index: var(--z-popover);
  backdrop-filter: blur(2px);
}

.confirmation-modal {
  background-color: #2d2d2d;
  color: #fff;
  padding: var(--spacing-0);
  border-radius: var(--radius-xl);
  max-width: 600px;
  width: 90%;
  box-shadow: var(--shadow-lg);
  border: 1px solid #444;
}

.confirmation-modal.emergency {
  border-color: var(--color-error);
  box-shadow: 0 10px 30px var(--color-danger-bg);
}

.modal-header {
  padding: var(--spacing-5) var(--spacing-6) var(--spacing-4) var(--spacing-6);
  border-bottom: 1px solid #444;
  background: var(--bg-secondary);
  border-radius: var(--radius-xl) 12px 0 0;
}

.modal-title {
  margin: var(--spacing-0);
  color: var(--color-warning);
  font-size: var(--text-lg);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.confirmation-modal.emergency .modal-title {
  color: #ff6b6b;
}

.modal-content {
  padding: var(--spacing-6);
}

.command-preview {
  background-color: #1e1e1e;
  border: 1px solid #444;
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-5);
}

.command-label {
  font-size: var(--text-xs);
  color: #888;
  margin-bottom: var(--spacing-2);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.command-text {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: var(--text-sm);
  color: #87ceeb;
  background-color: #000;
  padding: var(--spacing-3);
  border-radius: var(--radius-md);
  border-left: 4px solid var(--color-warning);
  white-space: pre-wrap;
  word-break: break-all;
}

.risk-assessment {
  margin-bottom: var(--spacing-5);
}

.risk-level {
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 600;
  margin-bottom: var(--spacing-3);
}

.risk-level.low {
  background-color: var(--color-success-bg);
  color: var(--color-success);
  border: 1px solid var(--color-success);
}

.risk-level.moderate {
  background-color: var(--color-warning-bg);
  color: var(--color-warning);
  border: 1px solid var(--color-warning);
}

.risk-level.high {
  background-color: rgba(255, 107, 107, 0.2);
  color: #ff6b6b;
  border: 1px solid #ff6b6b;
}

.risk-level.critical {
  background-color: var(--color-danger-bg);
  color: var(--color-error-light);
  border: 1px solid var(--color-error);
  animation: pulse-danger 2s infinite;
}

.risk-reasons {
  color: #ccc;
}

.risk-reason {
  margin-bottom: var(--spacing-1);
  font-size: var(--text-sm);
}

.confirmation-message {
  color: #ddd;
}

.confirmation-message p {
  margin-bottom: var(--spacing-3);
}

.confirmation-message ul {
  margin: var(--spacing-3) var(--spacing-0);
  padding-left: var(--spacing-5);
}

.confirmation-message li {
  margin-bottom: var(--spacing-1-5);
  color: #ccc;
}

.emergency-warning {
  color: #ff6b6b;
}

.emergency-warning p {
  margin-bottom: var(--spacing-3);
  font-weight: 500;
}

.process-item {
  background-color: #1e1e1e;
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-default);
  margin-bottom: var(--spacing-1);
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: var(--text-sm);
  color: #87ceeb;
}

.modal-actions {
  display: flex;
  gap: var(--spacing-3);
  justify-content: flex-end;
  padding: var(--spacing-5) var(--spacing-6);
  border-top: 1px solid #444;
  background-color: #252525;
  border-radius: 0 0 var(--radius-xl) var(--radius-xl);
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
  border-left: 3px solid var(--color-warning);
  background-color: var(--color-warning-bg);
}

.line-command.critical {
  border-left: 3px solid var(--color-error);
  background-color: var(--color-danger-bg);
}

/* Workflow Step Modal Styles */
.confirmation-modal.workflow-step {
  max-width: 700px;
  border-color: var(--color-info);
  box-shadow: 0 10px 30px var(--color-info-bg);
}

.workflow-step-info {
  text-align: left;
}

.step-counter {
  background-color: var(--color-info);
  color: var(--text-on-primary);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-2xl);
  display: inline-block;
  font-size: var(--text-xs);
  font-weight: 600;
  margin-bottom: var(--spacing-4);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.step-description h4 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2) var(--spacing-0);
  color: var(--color-info);
  font-size: var(--text-base);
  font-weight: 600;
}

.step-description p {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-4) var(--spacing-0);
  color: #ccc;
  font-size: var(--text-sm);
  line-height: 1.5;
}

.workflow-options {
  background-color: #1e1e1e;
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  margin-top: var(--spacing-5);
  border-left: 4px solid var(--color-info);
}

.option-info p {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-3) var(--spacing-0);
  color: var(--color-info);
  font-weight: 600;
}

.option-info ul {
  margin: var(--spacing-0);
  padding-left: var(--spacing-5);
  color: #ccc;
}

.option-info li {
  margin-bottom: var(--spacing-2);
  font-size: var(--text-sm);
  line-height: 1.4;
}

.option-info li strong {
  color: #fff;
}

.workflow-actions {
  justify-content: space-between;
  padding: var(--spacing-5) var(--spacing-6);
}

.btn-success {
  background-color: var(--color-success);
  color: var(--text-on-success);
  border: 1px solid var(--color-success-hover);
}

.btn-success:hover {
  background-color: var(--color-success-hover);
  border-color: var(--color-success-dark);
}

.btn-warning {
  background-color: var(--color-warning);
  color: var(--text-on-warning);
  border: 1px solid var(--color-warning-hover);
}

.btn-warning:hover {
  background-color: var(--color-warning-hover);
  border-color: var(--color-warning-dark);
}

/* Animation for active automation state */
@keyframes pulse-success {
  0%, 100% {
    box-shadow: 0 0 0 0 var(--color-success-bg);
  }
  50% {
    box-shadow: 0 0 0 8px transparent;
  }
}

/* Terminal line styles for automation */
.line-automated_command {
  color: var(--color-info);
  font-weight: 500;
  background-color: var(--color-info-bg);
  border-left: 3px solid var(--color-info);
  padding-left: var(--spacing-2);
}

.line-manual_command {
  color: var(--color-success);
  font-weight: 500;
  background-color: var(--color-success-bg);
  border-left: 3px solid var(--color-success);
  padding-left: var(--spacing-2);
}

.line-workflow_info {
  color: #6f42c1;
  background-color: rgba(111, 66, 193, 0.1);
  border-left: 3px solid #6f42c1;
  padding-left: var(--spacing-2);
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
  border-radius: var(--radius-default);
}

.terminal-output::-webkit-scrollbar-thumb:hover {
  background: #777;
}

/* Responsive */
@media (max-width: 768px) {
  .window-header {
    padding: var(--spacing-1-5) var(--spacing-3);
  }

  .terminal-status-bar {
    padding: 3px 12px;
  }

  .terminal-output {
    padding: var(--spacing-3);
    font-size: var(--text-xs);
  }

  .terminal-input-line {
    padding: var(--spacing-0) var(--spacing-3) var(--spacing-3) var(--spacing-3);
  }

  .footer-info {
    display: none; /* Hide on mobile */
  }
}
</style>
