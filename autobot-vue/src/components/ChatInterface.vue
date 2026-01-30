<template>
  <div class="flex h-full bg-white overflow-hidden">
    <!-- Knowledge Persistence Dialog -->
    <KnowledgePersistenceDialog
      :visible="showKnowledgeDialog"
      :chat-id="currentChatId"
      :chat-context="currentChatContext"
      @close="showKnowledgeDialog = false"
      @decisions-applied="onKnowledgeDecisionsApplied"
      @chat-compiled="onChatCompiled"
    />

    <!-- Command Permission Dialog -->
    <CommandPermissionDialog
      :show="showCommandDialog"
      :command="pendingCommand.command"
      :purpose="pendingCommand.purpose"
      :risk-level="pendingCommand.riskLevel"
      :chat-id="currentChatId"
      :original-message="pendingCommand.originalMessage"
      @approved="onCommandApproved"
      @denied="onCommandDenied"
      @commented="onCommandCommented"
      @close="showCommandDialog = false"
    />
    <!-- Sidebar -->
    <div class="w-80 bg-blueGray-100 border-r border-blueGray-200 flex flex-col h-full overflow-hidden transition-all duration-300 flex-shrink-0" :class="{ 'w-12': sidebarCollapsed }">
        <button class="p-3 border-b border-blueGray-200 text-blueGray-600 hover:bg-blueGray-200 transition-colors flex-shrink-0" @click="sidebarCollapsed = !sidebarCollapsed" aria-label="Collapse">
          <i :class="sidebarCollapsed ? 'fas fa-chevron-right' : 'fas fa-chevron-left'"></i>
        </button>
        <div class="sidebar-content" v-if="!sidebarCollapsed">
          <h3>Chat History</h3>
          <div class="conversation-list">
            <div v-for="chat in chatList" :key="chat.chatId" class="conversation-item" :class="{ 'active': currentChatId === chat.chatId }" @click="switchChat(chat.chatId)">
              <span>{{ chat.name || getChatPreview(chat.chatId) || `Chat ${chat.chatId.slice(0, 8)}...` }}</span>
              <div class="conversation-actions">
                <button class="action-icon" @click.stop="editChatName(chat.chatId)" title="Edit Name">✎</button>
                <button class="action-icon delete" @click.stop="deleteSpecificChat(chat.chatId)" title="Delete">🗑️</button>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-2 pt-4 border-t border-blueGray-200">
              <button class="btn btn-primary text-xs" @click="newChat" aria-label="Add">
                <i class="fas fa-plus mr-1"></i>
                New
              </button>
              <button class="btn btn-secondary text-xs" @click="resetChat" :disabled="!currentChatId" aria-label="Reset">
                <i class="fas fa-redo mr-1"></i>
                Reset
              </button>
              <button class="btn btn-danger text-xs" @click="deleteSpecificChat" :disabled="!currentChatId" aria-label="Delete">
                <i class="fas fa-trash mr-1"></i>
                Delete
              </button>
              <button class="btn btn-outline text-xs" @click="refreshChatList" aria-label="Refresh">
                <i class="fas fa-sync mr-1"></i>
                Refresh
              </button>
            </div>
          </div>
          <h3 class="text-lg font-semibold text-blueGray-700 mb-4 mt-6">Message Display</h3>
          <div class="space-y-3">
            <label class="flex items-center">
              <input type="checkbox" v-model="settings.message_display.show_thoughts" class="mr-2" />
              <span class="text-sm text-blueGray-600">Show Thoughts</span>
            </label>
            <label class="flex items-center">
              <input type="checkbox" v-model="settings.message_display.show_json" class="mr-2" />
              <span class="text-sm text-blueGray-600">Show JSON Output</span>
            </label>
            <label class="flex items-center">
              <input type="checkbox" v-model="settings.message_display.show_utility" class="mr-2" />
              <span class="text-sm text-blueGray-600">Show Utility Messages</span>
            </label>
            <label class="flex items-center">
              <input type="checkbox" v-model="settings.message_display.show_planning" class="mr-2" />
              <span class="text-sm text-blueGray-600">Show Planning Messages</span>
            </label>
            <label class="flex items-center">
              <input type="checkbox" v-model="settings.message_display.show_debug" class="mr-2" />
              <span class="text-sm text-blueGray-600">Show Debug Messages</span>
            </label>
            <label class="flex items-center">
              <input type="checkbox" v-model="settings.chat.auto_scroll" class="mr-2" />
              <span class="text-sm text-blueGray-600">Autoscroll</span>
            </label>
          </div>
          <h3 class="text-lg font-semibold text-blueGray-700 mb-4 mt-6">Backend Control</h3>
          <div class="mb-4">
            <button class="btn btn-primary w-full" @click="reloadSystem" :disabled="systemReloading" aria-label="Refresh">
              <i class="fas fa-sync mr-2"></i>
              {{ systemReloading ? 'Reloading...' : 'Reload System' }}
            </button>
          </div>
          <!-- Reload needed notification -->
          <div v-if="reloadNeeded" class="mb-4 p-3 bg-yellow-100 border border-yellow-300 rounded-lg">
            <div class="flex items-center">
              <i class="fas fa-exclamation-triangle text-yellow-600 mr-2"></i>
              <span class="text-sm text-yellow-800">System reload recommended</span>
            </div>
            <button @click="reloadSystem" class="mt-2 text-xs bg-yellow-600 text-white px-3 py-1 rounded hover:bg-yellow-700" aria-label="Reload now">
              Reload Now
            </button>
          </div>
        </div>
    </div>

    <!-- Main Chat Container -->
    <div class="flex-1 flex h-full overflow-hidden">
      <!-- Chat Content Area -->
      <div class="flex-1 flex flex-col h-full">
          <!-- Chat/Terminal/Desktop Tabs -->
          <div class="flex border-b border-blueGray-200 bg-white flex-shrink-0">
            <button
              @click="activeTab = 'chat'"
              :class="['px-6 py-3 text-sm font-medium transition-colors', activeTab === 'chat' ? 'border-b-2 border-indigo-500 text-indigo-600 bg-indigo-50' : 'text-blueGray-600 hover:text-blueGray-800 hover:bg-blueGray-50']"
             aria-label="Action button">
              <i class="fas fa-comments mr-2"></i>
              Chat
            </button>
            <button
              @click="activeTab = 'terminal'"
              :class="['px-6 py-3 text-sm font-medium transition-colors', activeTab === 'terminal' ? 'border-b-2 border-indigo-500 text-indigo-600 bg-indigo-50' : 'text-blueGray-600 hover:text-blueGray-800 hover:bg-blueGray-50']"
             aria-label="Action button">
              <i class="fas fa-terminal mr-2"></i>
              Terminal
            </button>
            <button
              @click="activeTab = 'computer'"
              :class="['px-6 py-3 text-sm font-medium transition-colors', activeTab === 'computer' ? 'border-b-2 border-indigo-500 text-indigo-600 bg-indigo-50' : 'text-blueGray-600 hover:text-blueGray-800 hover:bg-blueGray-50']"
             aria-label="Computer desktop viewer">
              <i class="fas fa-desktop mr-2"></i>
              Computer
            </button>
            <button
              @click="activeTab = 'browser'"
              :class="['px-6 py-3 text-sm font-medium transition-colors', activeTab === 'browser' ? 'border-b-2 border-indigo-500 text-indigo-600 bg-indigo-50' : 'text-blueGray-600 hover:text-blueGray-800 hover:bg-blueGray-50']"
             aria-label="Browser automation viewer">
              <i class="fas fa-globe mr-2"></i>
              Browser
            </button>
          </div>

          <!-- Chat Tab Content -->
          <div v-if="activeTab === 'chat'" class="flex-1 flex flex-col h-full">
            <!-- Chat Messages -->
            <div class="flex-1 overflow-y-auto p-6 space-y-4" ref="chatMessages" role="log" style="max-height: calc(100vh - 350px); min-height: 400px;">
            <div v-for="(message, index) in filteredMessages" :key="message.id || message.timestamp || `msg-${index}`" class="flex" :class="message.sender === 'user' ? 'justify-end' : 'justify-start'">
              <div class="max-w-3xl rounded-lg p-4 shadow-sm" :class="message.sender === 'user' ? 'bg-indigo-500 text-white' : 'bg-white border border-blueGray-200 text-blueGray-700'">
                <div class="message-content" :data-type="message.type" v-html="formatMessage(message.text, message.type)"></div>
                <div class="text-xs mt-2 opacity-70">{{ message.timestamp }}</div>
              </div>
            </div>
            </div>

            <!-- Chat Input - Fixed at bottom -->
            <div class="border-t border-blueGray-200 p-4 bg-white flex-shrink-0">
              <!-- Attached Files Display -->
              <div v-if="attachedFiles.length > 0" class="mb-3 flex flex-wrap gap-2">
                <div v-for="(file, index) in attachedFiles" :key="file.name || file.id || `file-${index}`" class="attached-file-chip">
                  <span class="file-icon">{{ getFileIcon(file) }}</span>
                  <span class="file-name">{{ file.name }}</span>
                  <button @click="removeAttachment(index)" class="remove-btn" aria-label="&times;">&times;</button>
                </div>
              </div>

              <div class="flex items-end space-x-4">
                <div class="flex-1">
                  <textarea
                    v-model="inputMessage"
                    @keydown.enter.exact.prevent="sendMessage"
                    placeholder="Type your message or goal for AutoBot..."
                    rows="3"
                    class="w-full px-4 py-3 border border-blueGray-300 rounded-lg resize-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                  ></textarea>
                </div>

                <!-- Chat Control Buttons -->
                <div class="flex flex-col gap-2">
                  <label class="btn btn-secondary p-2" title="Attach file">
                    <i class="fas fa-paperclip"></i>
                    <input type="file" @change="handleFileAttachment" multiple style="display: none;" />
                  </label>
                  <button
                    @click="showKnowledgeManagement"
                    class="btn btn-secondary p-2"
                    title="Manage Knowledge"
                  >
                    <i class="fas fa-brain"></i>
                  </button>
                  <button
                    @click="sendMessage"
                    :disabled="!inputMessage.trim() && attachedFiles.length === 0"
                    class="btn btn-primary px-6 py-3 disabled:opacity-50 disabled:cursor-not-allowed"
                   aria-label="Send message">
                    <i class="fas fa-paper-plane mr-2"></i>
                    Send
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Terminal Tab Content -->
          <div v-else-if="activeTab === 'terminal'" class="flex-1 flex flex-col h-full">
            <TerminalWindow
              :key="currentChatId"
              :session-id="currentChatId"
              :chat-context="true"
              class="flex-1"
            />
          </div>

          <!-- Computer Desktop Tab Content -->
          <div v-else-if="activeTab === 'computer'" class="flex-1 flex flex-col h-full">
            <div class="p-4 bg-blue-50 border-b border-blue-200">
              <div class="flex items-center justify-between">
                <div class="flex items-center space-x-3">
                  <i class="fas fa-desktop text-blue-600"></i>
                  <div>
                    <h3 class="text-lg font-semibold text-blue-800">AutoBot Computer View</h3>
                    <p class="text-sm text-blue-600">Live Kali Linux desktop streaming for system automation</p>
                  </div>
                </div>
                <div class="text-sm text-blue-600">
                  <i class="fas fa-broadcast-tower mr-1"></i>
                  System Desktop Access
                </div>
              </div>
            </div>
            <ComputerDesktopViewer class="flex-1" />
          </div>

          <!-- Browser Automation Tab Content -->
          <div v-else-if="activeTab === 'browser'" class="flex-1 flex flex-col h-full">
            <div class="p-4 bg-green-50 border-b border-green-200">
              <div class="flex items-center justify-between">
                <div class="flex items-center space-x-3">
                  <i class="fas fa-globe text-green-600"></i>
                  <div>
                    <h3 class="text-lg font-semibold text-green-800">AutoBot Browser View</h3>
                    <p class="text-sm text-green-600">Live Playwright browser automation and web scraping</p>
                  </div>
                </div>
                <div class="text-sm text-green-600">
                  <i class="fas fa-broadcast-tower mr-1"></i>
                  Live Browser Streaming Active
                </div>
              </div>
            </div>
            <PlaywrightDesktopViewer class="flex-1" />
          </div>
      </div>
    </div>

    <!-- Terminal Sidebar -->
    <TerminalSidebar
      v-if="showTerminalSidebar"
      :collapsed="terminalSidebarCollapsed"
      @update:collapsed="terminalSidebarCollapsed = $event"
      @open-new-tab="openTerminalInNewTab"
    />

    <!-- Workflow Progress Widget (floating) -->
    <WorkflowProgressWidget
      v-if="activeWorkflowId"
      :workflow-id="activeWorkflowId"
      @open-full-view="openFullWorkflowView"
      @workflow-cancelled="onWorkflowCancelled"
    />

    <!-- Workflow Approval Modal -->
    <div v-if="showWorkflowApproval" class="workflow-modal-overlay" @click="showWorkflowApproval = false" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
      <div class="workflow-modal" @click.stop tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
        <div class="modal-header">
          <h2>Workflow Management</h2>
          <button @click="showWorkflowApproval = false" class="close-btn" aria-label="Close">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-content">
          <WorkflowApproval />
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, nextTick, computed, watch } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import { getConfig, getWebsocketUrl } from '@/config/ssot-config';

const logger = createLogger('ChatInterface');

export default {
  name: 'ChatInterface',
  components: {
    TerminalSidebar,
    TerminalWindow,
    WorkflowApproval,
    WorkflowProgressWidget,
    KnowledgePersistenceDialog,
    CommandPermissionDialog,
    // Desktop viewer components (placeholder)
    PlaywrightDesktopViewer,
    ComputerDesktopViewer
  },
  setup() {
    const messages = ref([]);
    const inputMessage = ref('');
    const chatMessages = ref(null);
    // Settings structure to match a comprehensive config file
    const settings = ref({
      message_display: {
        show_thoughts: true,
        show_json: false, // Default to off as per user feedback
        show_utility: false, // Default to off as per user feedback
        show_planning: true,
        show_debug: false // Default to off to reduce noise
      },
      chat: {
        auto_scroll: true,
        max_messages: 100
      },
      backend: {
        use_phi2: false,
        api_endpoint: getConfig().backendUrl,
        ollama_endpoint: getConfig().ollamaUrl,
        ollama_model: 'tinyllama:latest',
        streaming: false
      },
      ui: {
        theme: 'light', // Options: 'light', 'dark'
        font_size: 'medium' // Options: 'small', 'medium', 'large'
      }
    });
    const sidebarCollapsed = ref(false);
    const terminalSidebarCollapsed = ref(true);
    const showTerminalSidebar = ref(false);
    const activeTab = ref('chat'); // Default to chat tab
    const inputMessage = ref('');
    const messages = ref([]);
    const chatList = ref([]);
    const currentChatId = ref(null);
    const backendStarting = ref(false);
    const systemReloading = ref(false);
    const reloadNeeded = ref(false);
    const chatMessages = ref(null);
    const attachedFiles = ref([]);

    // Workflow state
    const activeWorkflowId = ref(null);
    const showWorkflowApproval = ref(false);
    const websocket = ref(null);

    // Knowledge management state
    const showKnowledgeDialog = ref(false);
    const currentChatContext = ref(null);
    const chatFileAssociations = ref({});

    // Command permission state
    const showCommandDialog = ref(false);
    const pendingCommand = ref({
      command: '',
      purpose: '',
      riskLevel: 'LOW',
      originalMessage: ''
    });

    // Connection status checking functions
    const checkBackendConnection = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/health`, {
          method: 'GET',
          timeout: 5000
        });
        if (response.ok) {
          backendStatus.value = {
            connected: true,
            class: 'connected',
            text: 'Connected',
            message: 'Backend server is responding'
          };
          return true;
        } else {
          throw new Error(`Backend returned ${response.status}`);
        }
      } catch (error) {
        backendStatus.value = {
          connected: false,
          class: 'disconnected',
          text: 'Disconnected',
          message: `Backend connection failed: ${error.message}`
        };
        return false;
      }
    };

    const checkLLMConnection = async () => {
      try {
        // Check if we can reach the LLM endpoint
        const llmEndpoint = settings.value.backend.ollama_endpoint || getConfig().ollamaUrl;
        const response = await fetch(`${llmEndpoint}/api/tags`, {
          method: 'GET',
          timeout: 5000
        });
        if (response.ok) {
          llmStatus.value = {
            connected: true,
            class: 'connected',
            text: 'Connected',
            message: 'LLM service is available'
          };
          return true;
        } else {
          throw new Error(`LLM service returned ${response.status}`);
        }
      } catch (error) {
        llmStatus.value = {
          connected: false,
          class: 'disconnected',
          text: 'Disconnected',
          message: `LLM connection failed: ${error.message}`
        };
        return false;
      }
    };

    const checkConnections = async () => {
      await checkBackendConnection();
      await checkLLMConnection();
    };

    onMounted(async () => {
      // Check if there are persisted messages for this chat session
      const chatId = window.location.hash.split('chatId=')[1] || 'default';
      const persistedMessages = localStorage.getItem(`chat_${chatId}_messages`);
      if (persistedMessages) {
        messages.value = JSON.parse(persistedMessages);
      } else {
        // No default welcome message
        messages.value = [];
      }

      // Load settings from local storage if available
      const savedSettings = localStorage.getItem('chat_settings');
      if (savedSettings) {
        settings.value = JSON.parse(savedSettings);
      }

      // Check connections first
      await checkConnections();

      // Fetch backend settings to override with latest configuration
      await fetchBackendSettings();
      // Load system prompts on initialization
      await loadPrompts();

      // Set up periodic connection checking
      setInterval(checkConnections, 10000); // Check every 10 seconds
    });

    // Function to save settings to local storage and backend
    const saveSettings = async () => {
      localStorage.setItem('chat_settings', JSON.stringify(settings.value));
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/settings`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ settings: settings.value })
        });
        if (!response.ok) {
          logger.error('Failed to save settings to backend:', response.statusText);
        }
      } catch (error) {
        logger.error('Error saving settings to backend:', error);
      }
    };

    // Function to save backend-specific settings
    const saveBackendSettings = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/settings/backend`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ settings: { backend: settings.value.backend } })
        });
        if (!response.ok) {
          logger.error('Failed to save backend settings:', response.statusText);
        } else {
          logger.info('Backend settings saved successfully.');
        }
      } catch (error) {
        logger.error('Error saving backend settings:', error);
      }
    };

    // Function to fetch backend settings
    const fetchBackendSettings = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/settings/backend`);
        if (response.ok) {
          const backendSettings = await response.json();
          settings.value.backend = { ...settings.value.backend, ...backendSettings };
          logger.info('Backend settings loaded successfully.');
        } else {
          logger.error('Failed to load backend settings:', response.statusText);
        }
      } catch (error) {
        logger.error('Error loading backend settings:', error);
      }
    };

    // Function to load system prompts from backend
    const loadPrompts = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/prompts`);
        if (response.ok) {
          const data = await response.json();
          prompts.value = data.prompts || [];
          defaults.value = data.defaults || {};
          logger.info(`Loaded ${prompts.value.length} system prompts from backend.`);
        } else {
          logger.error('Failed to load system prompts:', response.statusText);
        }
      } catch (error) {
        logger.error('Error loading system prompts:', error);
      }
    };

    // Computed property to group prompts by type
    const groupedPrompts = computed(() => {
      const grouped = {};
      prompts.value.forEach(prompt => {
        const type = prompt.type || 'custom';
        if (!grouped[type]) {
          grouped[type] = { type, prompts: [] };
        }
        grouped[type].prompts.push(prompt);
      });
      return Object.values(grouped).sort((a, b) => {
        if (a.type === 'default') return -1;
        if (b.type === 'default') return 1;
        return a.type.localeCompare(b.type);
      });
    });

    // Function to edit a system prompt
    const editPrompt = async (promptId) => {
      const prompt = prompts.value.find(p => p.id === promptId);
      if (!prompt) {
        logger.warn(`Prompt ${promptId} not found for editing.`);
        return;
      }
      const newContent = prompt(`Edit prompt: ${prompt.name}`, prompt.content);
      if (newContent !== null) {
        try {
          const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/prompts/${promptId}`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ content: newContent })
          });
          if (response.ok) {
            const updatedPrompt = await response.json();
            const index = prompts.value.findIndex(p => p.id === promptId);
            if (index !== -1) {
              prompts.value[index] = updatedPrompt;
            }
            logger.info(`Updated prompt ${prompt.name} successfully.`);
          } else {
            logger.error('Failed to update prompt:', response.statusText);
          }
        } catch (error) {
          logger.error('Error updating prompt:', error);
        }
      }
    };

    // Function to revert a system prompt to default
    const revertPrompt = async (promptId) => {
      const prompt = prompts.value.find(p => p.id === promptId);
      if (!prompt) {
        logger.warn(`Prompt ${promptId} not found for reverting.`);
        return;
      }
      if (confirm(`Are you sure you want to revert ${prompt.name} to its default content?`)) {
        try {
          const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/prompts/${promptId}/revert`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            }
          });
          if (response.ok) {
            const updatedPrompt = await response.json();
            const index = prompts.value.findIndex(p => p.id === promptId);
            if (index !== -1) {
              prompts.value[index] = updatedPrompt;
            }
            logger.info(`Reverted prompt ${prompt.name} to default successfully.`);
          } else {
            logger.error('Failed to revert prompt:', response.statusText);
          }
        } catch (error) {
          logger.error('Error reverting prompt:', error);
        }
      }
    };

    // Watch for changes in settings and save them to local storage
    watch(settings, () => {
      saveSettings();
      if (settings.value.backend) {
        saveBackendSettings();
      }
    }, { deep: true });

    const filteredMessages = computed(() => {
      return messages.value.filter(message => {
        if (message.type === 'thought' && !settings.value.message_display.show_thoughts) return false;
        if (message.type === 'json' && !settings.value.message_display.show_json) return false;
        if (message.type === 'utility' && !settings.value.message_display.show_utility) return false;
        if (message.type === 'planning' && !settings.value.message_display.show_planning) return false;
        if (message.type === 'debug' && !settings.value.message_display.show_debug) return false;
        return true;
      });
    });

    // Methods
    const formatMessage = (text, type) => {
      // First clean and escape the text
      let cleanedText = escapeJsonChars(text);

      // Check if text is a structured response that needs parsing
      const parsedContent = parseStructuredMessage(cleanedText);

      if (parsedContent.length > 0) {
        // Multiple message types found, format each separately
        return parsedContent.map(item => formatSingleMessage(item.text, item.type)).join('');
      }

      // Single message type
      return formatSingleMessage(cleanedText, type);
    };

    const escapeJsonChars = (text) => {
      if (!text) return '';

      // Clean up JSON escape characters and brackets that are rendering literally
      return text
        .replace(/\\"/g, '"')           // Replace \" with "
        .replace(/\\n/g, '\n')         // Replace \n with actual newlines
        .replace(/\\r/g, '\r')         // Replace \r with carriage returns
        .replace(/\\t/g, '\t')         // Replace \t with tabs
        .replace(/\\\\/g, '\\')        // Replace \\\\ with single backslash
        .replace(/^\{|\}$/g, '')       // Remove wrapping { }
        .replace(/^\[|\]$/g, '')       // Remove wrapping [ ]
        .replace(/^"|"$/g, '');        // Remove wrapping quotes
    };

    const parseStructuredMessage = (text) => {
      const messages = [];
      let remainingText = text;

      // Check for "Tool Used:" pattern first - this is the most common format
      const toolPattern = /Tool Used: ([^\n]+)[\n\s]*Output: (.*?)(?=\n\d{2}:\d{2}:\d{2}|\nTool Used:|$)/gis;
      let toolMatch;

      while ((toolMatch = toolPattern.exec(text)) !== null) {
        // Add the tool usage as utility message
        messages.push({
          type: 'tool_output',
          text: `<strong>${toolMatch[1].trim()}</strong>`,
          order: toolMatch.index
        });

        const outputContent = toolMatch[2].trim();

        // Try to parse the output as JSON
        if (outputContent.startsWith('{') || outputContent.startsWith("{'")) {
          try {
            let jsonContent = outputContent;

            // Handle single quotes to double quotes conversion
            if (outputContent.startsWith("{'")) {
              jsonContent = outputContent.replace(/'/g, '"');
            }

            const parsed = JSON.parse(jsonContent);

            // Add the JSON output
            messages.push({
              type: 'json',
              text: JSON.stringify(parsed, null, 2),
              order: toolMatch.index + 1
            });

            // Check if it has response_text and extract the final response
            if (parsed.response_text) {
              let innerContent = parsed.response_text;

              // If response_text is a string that looks like JSON, parse it
              if (typeof innerContent === 'string' && (innerContent.startsWith('{') || innerContent.startsWith('{'))) {
                try {
                  const innerParsed = JSON.parse(innerContent);

                  // Extract the actual conversational response
                  if (innerParsed.response) {
                    const responseText = typeof innerParsed.response === 'object'
                      ? (innerParsed.response.greeting || innerParsed.response.message || JSON.stringify(innerParsed.response))
                      : innerParsed.response;

                    messages.push({
                      type: 'response',
                      text: responseText,
                      order: toolMatch.index + 2
                    });
                  } else if (typeof innerParsed === 'string') {
                    messages.push({
                      type: 'response',
                      text: innerParsed,
                      order: toolMatch.index + 2
                    });
                  }
                } catch {
                  // If inner parsing fails, just show the response_text as regular content
                  messages.push({
                    type: 'response',
                    text: innerContent,
                    order: toolMatch.index + 2
                  });
                }
              } else {
                messages.push({
                  type: 'response',
                  text: innerContent,
                  order: toolMatch.index + 2
                });
              }
            }

          } catch (e) {
            // Not valid JSON, treat as regular utility output
            messages.push({
              type: 'utility',
              text: outputContent,
              order: toolMatch.index + 1
            });
          }

          // Always use the backend API endpoint for goal requests
          let apiEndpoint = settings.value.backend.api_endpoint;
          let goalEndpoint = '/api/chat';
          logger.info('Using API endpoint for goal request:', apiEndpoint, 'with endpoint:', goalEndpoint);

          const response = await fetch(`${apiEndpoint}${goalEndpoint}`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: requestBody
          });
          if (response.ok) {
            const contentType = response.headers.get('content-type');
            if (settings.value.message_display.show_utility) {
              messages.value.push({
                sender: 'debug',
                text: `Response content type: ${contentType}`,
                timestamp: new Date().toLocaleTimeString(),
                type: 'utility'
              });
            }
            if (contentType && contentType.includes('text/event-stream')) {
              if (settings.value.message_display.show_utility) {
                messages.value.push({
                  sender: 'debug',
                  text: `Detected streaming response. Initiating streaming handler.`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'utility'
                });
              }
              // Handle streaming response using ReadableStream directly from the initial response
              handleStreamingResponseFromResponse(response);
            } else {
              if (settings.value.message_display.show_utility) {
                messages.value.push({
                  sender: 'bot',
                  text: `Non-streaming response detected. Waiting for JSON data.`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'utility'
                });
              }
              const botResponse = await response.json();
              logger.info('Raw bot response:', botResponse);
              let responseText = botResponse.text || JSON.stringify(botResponse);
              let responseType = botResponse.type || 'response';

              // Handle OpenAI-compatible response format for non-streaming
              if (botResponse.object === 'chat.completion' && botResponse.choices && botResponse.choices.length > 0) {
                const choice = botResponse.choices[0];
                if (choice.message && choice.message.content) {
                  responseText = choice.message.content;
                  responseType = 'response';
                }
              }

              if (settings.value.message_display.show_json) {
                messages.value.push({
                  sender: 'bot',
                  text: `Response from backend: ${JSON.stringify(botResponse, null, 2)}`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'json'
                });
              }

              // Extract detailed LLM request and response if available
              if (botResponse.llm_request && settings.value.message_display.show_utility) {
                messages.value.push({
                  sender: 'bot',
                  text: `LLM Request: ${JSON.stringify(botResponse.llm_request, null, 2)}`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'utility'
                });
              }
              if (botResponse.llm_response && settings.value.message_display.show_utility) {
                messages.value.push({
                  sender: 'bot',
                  text: `LLM Response: ${JSON.stringify(botResponse.llm_response, null, 2)}`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'utility'
                });
              }

              messages.value.push({
                sender: 'bot',
                text: responseText,
                timestamp: new Date().toLocaleTimeString(),
                type: responseType
              });
            }
          } else {
            logger.error('Failed to get bot response:', response.statusText);
            if (settings.value.message_display.show_utility) {
              messages.value.push({
                sender: 'bot',
                text: `Error from backend: Status ${response.status} - ${response.statusText}`,
                timestamp: new Date().toLocaleTimeString(),
                type: 'utility'
              });
            }
            messages.value.push({
              sender: 'bot',
              text: `Error: Unable to connect to the backend. Please ensure the server is running.`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'response'
            });
          }
        } catch (error) {
          logger.error('Error sending message:', error);
          if (settings.value.message_display.show_utility) {
            messages.value.push({
              sender: 'bot',
              text: `Error sending request to backend: ${error.message}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'utility'
            });
          }
          messages.value.push({
            sender: 'bot',
            text: `Error: Unable to connect to the backend. Please ensure the server is running.`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'response'
          });
        }

        // Remove processed content from remaining text
        remainingText = remainingText.replace(toolMatch[0], '').trim();
      }

      // Check for other structured patterns in remaining text
      const patterns = [
        { type: 'thought', pattern: /\[THOUGHT\](.*?)\[\/THOUGHT\]/gis },
        { type: 'planning', pattern: /\[PLANNING\](.*?)\[\/PLANNING\]/gis },
        { type: 'utility', pattern: /\[UTILITY\](.*?)\[\/UTILITY\]/gis },
        { type: 'debug', pattern: /\[DEBUG\](.*?)\[\/DEBUG\]/gis },
        { type: 'json', pattern: /\[JSON\](.*?)\[\/JSON\]/gis }
      ];

      patterns.forEach(({ type, pattern }) => {
        let match;
        while ((match = pattern.exec(remainingText)) !== null) {
          messages.push({
            type,
            text: match[1].trim(),
            order: match.index + 1000 // Ensure these come after tool outputs
          });
        }
      });

      // Sort messages by order to maintain proper sequence
      messages.sort((a, b) => (a.order || 0) - (b.order || 0));

      return messages.length > 0 ? messages : [];
    };

    const formatSingleMessage = (text, type) => {
      const escapedText = text.replace(/</g, '&lt;').replace(/>/g, '&gt;');

      switch (type) {
        case 'thought':
          return `<div class="thought-message">
            <div class="message-header">💭 Thoughts</div>
            <div class="message-content">${escapedText}</div>
          </div>`;
        case 'planning':
          return `<div class="planning-message">
            <div class="message-header">📋 Planning</div>
            <div class="message-content">${escapedText}</div>
          </div>`;
        case 'utility':
          return `<div class="utility-message">
            <div class="message-header">⚙️ Utility</div>
            <div class="message-content">${escapedText}</div>
          </div>`;
        case 'debug':
          return `<div class="debug-message">
            <div class="message-header">🐛 Debug</div>
            <div class="message-content"><pre>${escapedText}</pre></div>
          </div>`;
        case 'json':
          return `<div class="json-message">
            <div class="message-header">📊 JSON Output</div>
            <div class="message-content"><pre>${escapedText}</pre></div>
          </div>`;
        case 'tool_output':
          return `<div class="tool-output-message">
            <div class="message-header">🔧 Tool Output</div>
            <div class="message-content">${escapedText}</div>
          </div>`;
        default:
          return `<div class="regular-message">${escapedText}</div>`;
      }
    };

    const determineMessageType = (text) => {
      if (!text) return 'response';

      // Check for JSON patterns
      if (text.includes('response_text') || (text.startsWith('{') && text.includes('"status"'))) {
        return 'json';
      }

      // Check for tool output patterns
      if (text.includes('Tool Used:') && text.includes('Output:')) {
        return 'tool_output';
      }

      // Check for structured message patterns
      if (text.includes('[THOUGHT]') || text.includes('[PLANNING]') ||
          text.includes('[UTILITY]') || text.includes('[DEBUG]')) {
        return 'structured';
      }

      return 'response';
    };

    // File handling functions
    const handleFileAttachment = (event) => {
      const files = Array.from(event.target.files);
      attachedFiles.value.push(...files);
    };

    const removeAttachment = (index) => {
      attachedFiles.value.splice(index, 1);
    };

    const getFileIcon = (file) => {
      const extension = file.name.split('.').pop().toLowerCase();
      const iconMap = {
        'txt': '📄',
        'pdf': '📕',
        'doc': '📘',
        'docx': '📘',
        'md': '📝',
        'json': '📊',
        'xml': '📋',
        'csv': '📊',
        'py': '🐍',
        'js': '📜',
        'html': '🌐',
        'css': '🎨',
        'img': '🖼️',
        'png': '🖼️',
        'jpg': '🖼️',
        'jpeg': '🖼️',
        'gif': '🖼️'
      };
      return iconMap[extension] || '📎';
    };

    // Knowledge management methods
    const loadChatContext = async (chatId) => {
      try {
        // Chat context loading temporarily disabled - using basic chat functionality
        // const response = await apiService.get(`/api/chat_knowledge/context/${chatId}`);
        // if (response.success) {
        //   currentChatContext.value = response.context;
        // }

        // For now, use basic context
        currentChatContext.value = { chatId };
      } catch (error) {
        logger.error('Failed to load chat context:', error);
      }
    };

    const associateFileWithChat = async (filePath, fileName) => {
      try {
        await apiService.post('/api/chat_knowledge/files/associate', {
          chat_id: currentChatId.value,
          file_path: filePath,
          association_type: 'upload',
          metadata: { original_filename: fileName }
        });

        // Update local associations
        if (!chatFileAssociations.value[currentChatId.value]) {
          chatFileAssociations.value[currentChatId.value] = [];
        }
        chatFileAssociations.value[currentChatId.value].push({
          file_path: filePath,
          file_name: fileName,
          type: 'upload'
        });
      } catch (error) {
        logger.error('Failed to associate file with chat:', error);
      }
    };

    const showKnowledgeManagement = () => {
      showKnowledgeDialog.value = true;
    };

    const onKnowledgeDecisionsApplied = (decisions) => {
      // Refresh chat context
      if (currentChatId.value) {
        loadChatContext(currentChatId.value);
      }
    };

    const onChatCompiled = (compiledData) => {
      // Show success message or notification
    };

    const onCommandApproved = (result) => {
      logger.info('Command approved:', result);
      // The dialog already sent "yes" to the backend
      showCommandDialog.value = false;

      // Add approval message to chat
      messages.value.push({
        sender: 'user',
        content: '✅ Command approved and executed',
        timestamp: new Date().toISOString(),
        messageType: 'approval'
      });

      // Add the result to messages if provided
      if (result.result) {
        messages.value.push(result.result);
      }
    };

    const onCommandDenied = (reason) => {
      logger.info('Command denied:', reason);
      showCommandDialog.value = false;

      // Add denial message to chat
      messages.value.push({
        sender: 'user',
        content: '❌ Command denied by user',
        timestamp: new Date().toISOString(),
        messageType: 'denial'
      });

      // Add agent acknowledgment
      messages.value.push({
        sender: 'assistant',
        content: 'Understood. I won\'t execute that command. Is there anything else I can help you with?',
        timestamp: new Date().toISOString(),
        messageType: 'response'
      });
    };

    const onCommandCommented = (data) => {
      logger.info('Command commented:', data);
      showCommandDialog.value = false;

      // Add the user's feedback to chat
      messages.value.push({
        sender: 'user',
        content: `💬 **Command Feedback**: ${data.comment}`,
        timestamp: new Date().toISOString(),
        messageType: 'comment'
      });

      // Add the agent's response to the feedback
      if (data.response) {
        messages.value.push(data.response);
      } else {
        // Fallback response if no backend response
        messages.value.push({
          sender: 'assistant',
          content: `Thank you for the feedback! I'll take your suggestion into account. The original command was: \`${data.command}\`\n\nWould you like me to try a different approach or modify the command based on your suggestion?`,
          timestamp: new Date().toISOString(),
          messageType: 'response'
        });
      }
    };

    const sendMessage = async () => {
      if (!inputMessage.value.trim() && attachedFiles.value.length === 0) return;

      // Add user message with file info if any
      let messageText = inputMessage.value;
      if (attachedFiles.value.length > 0) {
        const fileNames = attachedFiles.value.map(f => f.name).join(', ');
        messageText += `\n\n📎 Attached files: ${fileNames}`;
      }

      messages.value.push({
        sender: 'user',
        text: messageText,
        timestamp: new Date().toLocaleTimeString(),
        type: 'message'
      });

      const userInput = inputMessage.value;
      const filesToUpload = [...attachedFiles.value];
      inputMessage.value = '';
      attachedFiles.value = [];

      try {
        // Upload files first if any
        let uploadedFilePaths = [];
        if (filesToUpload.length > 0) {
          for (const file of filesToUpload) {
            const formData = new FormData();
            formData.append('file', file);

            const uploadResponse = await fetch(`${getConfig().backendUrl}/api/files/upload`, {
              method: 'POST',
              body: formData
            });

            if (uploadResponse.ok) {
              const result = await uploadResponse.json();
              uploadedFilePaths.push(result.path || file.name);

              // Associate file with current chat
              await associateFileWithChat(result.path || file.name, file.name);
            }
          }
        }

        // Send message with file references
        const messageData = {
          message: userInput
        };

        if (uploadedFilePaths.length > 0) {
          messageData.attachments = uploadedFilePaths;
        }

        // Check if this should use workflow orchestration
        const workflowResponse = await fetch(`${getConfig().backendUrl}/api/workflow/execute`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            user_message: userInput,
            auto_approve: false
          }),
        });

        if (workflowResponse.ok) {
          // Enhanced Edge browser compatibility: validate response before parsing
          let workflowResult;
          try {
            const responseText = await workflowResponse.text();

            // Edge browser compatibility: validate response content
            if (!responseText || responseText.trim() === '') {
              throw new Error('Empty response received from server');
            }

            // Edge browser compatibility: check for valid JSON structure
            if (!responseText.includes('{') || !responseText.includes('}')) {
              throw new Error('Invalid JSON response format received');
            }

            // Log for debugging in Edge browser

            workflowResult = JSON.parse(responseText);

            // Edge browser compatibility: validate parsed result structure
            if (!workflowResult || typeof workflowResult !== 'object') {
              throw new Error('Parsed response is not a valid object');
            }

          } catch (parseError) {
            logger.error('Edge browser compatibility error:', parseError);
            logger.error('Response status:', workflowResponse.status);
            logger.error('Response headers:', Object.fromEntries(workflowResponse.headers.entries()));

            // Show user-friendly error message for Edge browser
            messages.value.push({
              sender: 'bot',
              text: 'I encountered a compatibility issue processing your request. This sometimes happens in Microsoft Edge browser. Please try refreshing the page or using Chrome/Firefox. If the issue persists, please contact support.',
              timestamp: new Date().toLocaleTimeString(),
              type: 'error'
            });
            return;
          }

          if (workflowResult.type === 'workflow_orchestration') {
            // Workflow orchestration triggered
            activeWorkflowId.value = workflowResult.workflow_id;

            messages.value.push({
              sender: 'bot',
              text: `🔄 Workflow orchestration started for your request. I've broken this down into ${workflowResult.workflow_response.workflow_preview.length} coordinated steps involving multiple agents.`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'workflow'
            });

            // Show workflow details
            if (workflowResult.workflow_response.workflow_preview) {
              const stepsList = workflowResult.workflow_response.workflow_preview
                .map((step, i) => `${i + 1}. ${step}`)
                .join('\n');

              messages.value.push({
                sender: 'bot',
                text: `**Workflow Steps:**\n${stepsList}`,
                timestamp: new Date().toLocaleTimeString(),
                type: 'planning'
              });
            }
          } else {
            // Direct execution
            const responseText = workflowResult.result?.response || workflowResult.result?.response_text || 'No response received';
            const responseType = workflowResult.result?.messageType;

            // Check if this is a command permission request
            if (responseType === 'command_permission_request' && workflowResult.result?.commandData) {
              // Set up the command dialog data
              pendingCommand.value = {
                command: workflowResult.result.commandData.command,
                purpose: workflowResult.result.commandData.purpose,
                riskLevel: workflowResult.result.commandData.riskLevel || 'LOW',
                originalMessage: workflowResult.result.commandData.originalMessage
              };

              // Show the permission dialog
              showCommandDialog.value = true;

              // Also add a message to chat history for reference
              messages.value.push({
                sender: 'bot',
                text: responseText,
                timestamp: new Date().toLocaleTimeString(),
                type: 'command_request'
              });
            } else {
              // Normal message processing
              const messageType = determineMessageType(responseText);

              messages.value.push({
                sender: 'bot',
                text: responseText,
                timestamp: new Date().toLocaleTimeString(),
                type: messageType
              });
            }
          }
        } else {
          // Workflow failed, try fallback to regular chat
          logger.info('Workflow failed, falling back to regular chat endpoint');
          try {
            const chatResponse = await apiClient.sendChatMessage(userInput, {
              chatId: currentChatId.value || 'default'
            });

            if (chatResponse.type === 'json' && chatResponse.data) {
              const responseText = chatResponse.data.content || chatResponse.data.response || 'No response received';
              const responseType = chatResponse.data.messageType;

              // Check if this is a command permission request
              if (responseType === 'command_permission_request' && chatResponse.data.commandData) {
                // Set up the command dialog data
                pendingCommand.value = {
                  command: chatResponse.data.commandData.command,
                  purpose: chatResponse.data.commandData.purpose,
                  riskLevel: chatResponse.data.commandData.riskLevel || 'LOW',
                  originalMessage: chatResponse.data.commandData.originalMessage
                };

                // Show the permission dialog
                showCommandDialog.value = true;

                // Also add a message to chat history for reference
                messages.value.push({
                  sender: 'bot',
                  text: responseText,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'command_request'
                });
              } else {
                // Normal message processing
                const messageType = determineMessageType(responseText);

                messages.value.push({
                  sender: 'bot',
                  text: responseText,
                  timestamp: new Date().toLocaleTimeString(),
                  type: messageType
                });
              }
            } else {
              throw new Error('Invalid response from chat endpoint');
            }
          } catch (fallbackError) {
            logger.error('Fallback chat also failed:', fallbackError);
            messages.value.push({
              sender: 'bot',
              text: 'Error: Could not get response from server (both workflow and chat endpoints failed)',
              timestamp: new Date().toLocaleTimeString(),
              type: 'error'
            });
          }
        }
      } catch (error) {
        // Enhanced Edge browser compatibility error handling
        logger.error('Chat interface error:', error);
        logger.error('Error type:', error.constructor.name);

        // Check if this is an LLM model error that requires system reload
        if (error.message && (
          error.message.includes('Unsupported LLM model type') ||
          error.message.includes('model type') ||
          error.message.includes('LLM') ||
          error.response?.status === 500
        )) {
          setReloadNeeded(true);
        }

        // Edge browser specific error handling
        let errorMessage = error.message || 'An unknown error occurred';

        // Check for Edge-specific network errors
        if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
          errorMessage = 'Network connection error. Please check your internet connection and try again.';
        } else if (error.message.includes('JSON') || error.message.includes('Unexpected token')) {
          errorMessage = 'Response parsing error. This sometimes happens in Microsoft Edge browser. Please try refreshing the page.';
        } else if (error.message.includes('AbortError') || error.message.includes('timeout')) {
          errorMessage = 'Request timeout. Please try again or refresh the page.';
        }

        messages.value.push({
          sender: 'bot',
          text: `Error: ${errorMessage}`,
          timestamp: new Date().toLocaleTimeString(),
          type: 'error'
        });
      }

      // Auto-scroll
      nextTick(() => {
        if (chatMessages.value && settings.value.chat.auto_scroll) {
          chatMessages.value.scrollTop = chatMessages.value.scrollHeight;
        }
      });
    };

    const newChat = async () => {
      try {
        // Create new chat via backend
        const data = await apiClient.createNewChat();
        const newChatId = data.chatId || `chat-${Date.now()}`;

        currentChatId.value = newChatId;
        messages.value = [];

        // Save to localStorage
        localStorage.setItem('lastChatId', newChatId);

        // Add to chat list
        chatList.value.unshift({
          id: newChatId,
          chatId: newChatId,
          name: null,
          lastMessage: null,
          timestamp: new Date()
        });

      } catch (error) {
        logger.error('Error creating new chat:', error);
        // Fallback to local chat creation
        const newChatId = `chat-${Date.now()}`;
        currentChatId.value = newChatId;
        messages.value = [];
        localStorage.setItem('lastChatId', newChatId);

        chatList.value.unshift({
          id: newChatId,
          chatId: newChatId,
          name: null,
          lastMessage: null,
          timestamp: new Date()
        });
      }
    };

    const resetChat = () => {
      messages.value = [];
    };

    const deleteSpecificChat = async (chatId = null) => {
      const targetChatId = chatId || currentChatId.value;
      if (!targetChatId) return;

      try {
        // Delete from backend first
        await apiClient.deleteChat(targetChatId);

        // Then update frontend state
        chatList.value = chatList.value.filter(chat => chat.chatId !== targetChatId);

        if (currentChatId.value === targetChatId) {
          messages.value = [];
          if (chatList.value.length > 0) {
            switchChat(chatList.value[0].chatId);
          } else {
            newChat();
          }
        }
      } catch (error) {
        // Handle 404 errors silently (expected for legacy chats)
        if (error.message && error.message.includes('404')) {
          // Legacy chats may not exist on backend - just remove from frontend silently
          logger.debug(`Chat ${targetChatId} not found on backend (legacy format) - removing from local list`);
        } else {
          // Only log unexpected errors
          logger.error('Unexpected error deleting chat:', error);
        }

        // Always update frontend state regardless of backend result
        // This ensures chat deletion appears to work for users
        chatList.value = chatList.value.filter(chat => chat.chatId !== targetChatId);

        if (currentChatId.value === targetChatId) {
          messages.value = [];
          if (chatList.value.length > 0) {
            switchChat(chatList.value[0].chatId);
          } else {
            newChat();
          }
        }
      }
    };

    const switchChat = async (chatId) => {
      // Save current chat messages before switching
      if (currentChatId.value && messages.value.length > 0) {
        await saveChatMessages(currentChatId.value);
      }

      currentChatId.value = chatId;

      // Save the current chat ID to localStorage
      localStorage.setItem('lastChatId', chatId);

      // Load messages for this chat from backend
      await loadChatMessages(chatId);

      // Load chat context for knowledge management
      await loadChatContext(chatId);
    };

    const editChatName = (chatId) => {
      const chat = chatList.value.find(c => c.chatId === chatId);
      if (chat) {
        const newName = prompt('Enter new chat name:', chat.name || '');
        if (newName !== null) {
          chat.name = newName.trim() || null;
        }
      }
    };

    const getChatPreview = (chatId) => {
      // Return first few words of last message in this chat
      return 'Chat preview...';
    };

    const refreshChatList = async () => {
      try {
        const data = await apiClient.getChatList();
        chatList.value = data.chats || [];
      } catch (error) {
        logger.error('Error loading chat list:', error);
        // Fallback: create a default chat if list fails to load
        if (chatList.value.length === 0) {
          const fallbackChatId = `fallback-${Date.now()}`;
          chatList.value = [{
            id: fallbackChatId,
            chatId: fallbackChatId,
            name: 'Default Chat',
            lastMessage: null,
            timestamp: new Date()
          }];
        }
      }
    };

    const loadChatMessages = async (chatId) => {
      try {
        const data = await apiClient.getChatMessages(chatId);
        // Backend returns 'history' field, not 'messages'
        const history = data.history || [];

        // Map messageType to type for frontend filtering compatibility
        messages.value = history.map(message => ({
          ...message,
          type: message.messageType || message.type || 'default'
        }));

        // Scroll to bottom after loading
        await nextTick();
        if (chatMessages.value) {
          chatMessages.value.scrollTop = chatMessages.value.scrollHeight;
        }
      } catch (error) {
        logger.error('Error loading chat messages:', error);
        messages.value = [];
      }
    };

    const saveChatMessages = async (chatId) => {
      try {
        await apiClient.saveChatMessages(chatId, messages.value);
      } catch (error) {
        logger.error('Error saving chat messages:', error);
      }
    };

    const reloadSystem = async () => {
      systemReloading.value = true;
      try {
        const response = await apiClient.post('/api/system/reload');

        if (response.data.status === 'success') {
          reloadNeeded.value = false; // Clear reload notification

          // Show success message to user (you might want to add a toast notification here)
          const reloadResults = response.data.reload_results || [];
          const reloadedModules = response.data.reloaded_modules || [];


          // Add system message to chat
          const systemMessage = {
            sender: 'system',
            text: `System reloaded successfully. Modules updated: ${reloadedModules.length}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'system'
          };
          messages.value.push(systemMessage);

        } else {
          throw new Error('System reload failed');
        }
      } catch (error) {
        logger.error('Failed to reload system:', error);

        // Add error message to chat
        const errorMessage = {
          sender: 'system',
          text: `System reload failed: ${error.message}`,
          timestamp: new Date().toLocaleTimeString(),
          type: 'error'
        };
        messages.value.push(errorMessage);
      } finally {
        systemReloading.value = false;
      }
    };

    // Function to check if reload is needed (you can call this when detecting errors)
    const setReloadNeeded = (needed = true) => {
      reloadNeeded.value = needed;
    };

    const openTerminalInNewTab = () => {
      // Open terminal in new tab
    };

    // Workflow methods
    const openFullWorkflowView = (view) => {
      if (view === 'approvals' || view === 'workflow') {
        showWorkflowApproval.value = true;
      }
    };

    const onWorkflowCancelled = (workflowId) => {
      if (activeWorkflowId.value === workflowId) {
        activeWorkflowId.value = null;
      }
      messages.value.push({
        sender: 'bot',
        text: `❌ Workflow ${workflowId} has been cancelled.`,
        timestamp: new Date().toLocaleTimeString(),
        type: 'system'
      });
    };

    // WebSocket methods
    const connectWebSocket = () => {
      const wsUrl = getWebsocketUrl();
      websocket.value = new WebSocket(wsUrl);

      websocket.value.onopen = () => {
      };

      websocket.value.onmessage = (event) => {
        try {
          const eventData = JSON.parse(event.data);
          handleWebSocketEvent(eventData);
        } catch (error) {
          logger.error('Failed to parse WebSocket message:', error);
        }
      };

      websocket.value.onerror = (error) => {
        logger.error('WebSocket error:', error);
      };

      websocket.value.onclose = () => {
        setTimeout(connectWebSocket, 3000);
      };
    };

    const handleWebSocketEvent = (eventData) => {
      const eventType = eventData.type;
      const payload = eventData.payload;

      if (eventType.startsWith('workflow_')) {
        // Handle workflow events
        if (eventType === 'workflow_step_started') {
          messages.value.push({
            sender: 'workflow',
            text: `🔄 Started: ${payload.description}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'workflow'
          });
        } else if (eventType === 'workflow_step_completed') {
          messages.value.push({
            sender: 'workflow',
            text: `✅ Completed: ${payload.description}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'workflow'
          });
        } else if (eventType === 'workflow_approval_required') {
          activeWorkflowId.value = payload.workflow_id;
          messages.value.push({
            sender: 'workflow',
            text: `⏸️ Approval Required: ${payload.description}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'workflow'
          });
        } else if (eventType === 'workflow_completed') {
          messages.value.push({
            sender: 'workflow',
            text: `🎉 Workflow completed successfully! (${payload.total_steps} steps)`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'workflow'
          });
          if (activeWorkflowId.value === payload.workflow_id) {
            activeWorkflowId.value = null;
          }
        } else if (eventType === 'workflow_failed') {
          messages.value.push({
            sender: 'workflow',
            text: `❌ Workflow failed: ${payload.error}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'workflow'
          });
          if (activeWorkflowId.value === payload.workflow_id) {
            activeWorkflowId.value = null;
          }
        }

        // Auto-scroll to show new workflow updates
        nextTick(() => {
          if (chatMessages.value && settings.value.chat.auto_scroll) {
            chatMessages.value.scrollTop = chatMessages.value.scrollHeight;
          }
        });
      }
    };

    const handleStreamingResponseFromResponse = (response) => {
      if (eventSource) {
        eventSource.close();
      }
      let fullResponseText = '';
      let fullThoughtText = '';
      let fullJsonText = '';
      let fullUtilityText = '';
      let fullPlanningText = '';
      let currentToolCall = null;

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');

      function readStream() {
        reader.read().then(({ done, value }) => {
          if (done) {
            if (settings.value.message_display.show_utility) {
              messages.value.push({
                sender: 'bot',
                text: 'Streaming response completed.',
                timestamp: new Date().toLocaleTimeString(),
                type: 'utility'
              });
            }
            const lastBotMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
            if (lastBotMessageIndex >= 0) {
              messages.value[lastBotMessageIndex].final = true;
            }
            const lastThoughtMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'thought' && !msg.final);
            if (lastThoughtMessageIndex >= 0) {
              messages.value[lastThoughtMessageIndex].final = true;
            }
            const lastJsonMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'json' && !msg.final);
            if (lastJsonMessageIndex >= 0) {
              messages.value[lastJsonMessageIndex].final = true;
            }
            const lastUtilityMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'utility' && !msg.final);
            if (lastUtilityMessageIndex >= 0) {
              messages.value[lastUtilityMessageIndex].final = true;
            }
            const lastPlanningMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'planning' && !msg.final);
            if (lastPlanningMessageIndex >= 0) {
              messages.value[lastPlanningMessageIndex].final = true;
            }
            saveMessagesToStorage();
            return;
          }

          const chunk = decoder.decode(value, { stream: true });
          if (settings.value.message_display.show_debug) {
            messages.value.push({
              sender: 'debug',
              text: `Raw chunk received: ${chunk}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          }

          try { // Outer try block for chunk parsing
            const dataMatches = chunk.split('\n').filter(line => line.startsWith('data: '));
            if (dataMatches.length > 0) {
              for (const dataLine of dataMatches) {
                const dataStr = dataLine.replace('data: ', '').trim();
                if (!dataStr) continue;

                try { // Inner try block for JSON parsing
                  const data = JSON.parse(dataStr);

                  if (settings.value.message_display.show_json) {
                    messages.value.push({
                      sender: 'bot',
                      text: JSON.stringify(data, null, 2),
                      timestamp: new Date().toLocaleTimeString(),
                      type: 'json',
                      final: false
                    });
                  }

                  if (data.object === 'chat.completion.chunk' && data.choices && data.choices.length > 0) {
                    const choice = data.choices[0];
                    if (choice.delta) {
                      if (choice.delta.content) {
                        fullResponseText += choice.delta.content;
                        const lastBotMessageIndex = messages.value.findLastIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
                        if (lastBotMessageIndex >= 0) {
                          messages.value[lastBotMessageIndex].text = fullResponseText;
                        } else {
                          messages.value.push({
                            sender: 'bot',
                            text: fullResponseText,
                            timestamp: new Date().toLocaleTimeString(),
                            type: 'response',
                            final: false
                          });
                        }
                        nextTick(() => {
                          if (chatMessages.value && settings.value.chat.auto_scroll) {
                            chatMessages.value.scrollTop = chatMessages.value.scrollHeight;
                          }
                        });
                      }
                      if (choice.delta.tool_calls) {
                          const toolCallDelta = choice.delta.tool_calls[0];
                          if (toolCallDelta.function) {
                              if (toolCallDelta.function.name) {
                                  if (!currentToolCall || currentToolCall.id !== toolCallDelta.id) {
                                      currentToolCall = {
                                          id: toolCallDelta.id,
                                          name: toolCallDelta.function.name,
                                          arguments: ''
                                      };
                                  }
                              }
                              if (toolCallDelta.function.arguments) {
                                  if (currentToolCall) {
                                      currentToolCall.arguments += toolCallDelta.function.arguments;
                                  }
                              }
                          }
                      }
                    }
                    if (choice.finish_reason) {
                      if (choice.finish_reason === 'tool_calls' && data.choices[0].message && data.choices[0].message.tool_calls) {
                        if (settings.value.message_display.show_utility) {
                          messages.value.push({
                            sender: 'bot',
                            text: `Tool call requested: ${JSON.stringify(data.choices[0].message.tool_calls, null, 2)}`,
                            timestamp: new Date().toLocaleTimeString(),
                            type: 'utility'
                          });
                        }
                        reader.cancel();

                        const toolCall = currentToolCall;
                        if (toolCall && (toolCall.name === 'fetch_wikipedia_content' || toolCall.name === 'get_wikipedia_content')) {
                          try {
                            const args = JSON.parse(toolCall.arguments || '{}');
                            const searchQuery = args.search_query || 'unknown query';
                            messages.value.push({
                              sender: 'bot',
                              text: `Fetching Wikipedia content for "${searchQuery}"...`,
                              timestamp: new Date().toLocaleTimeString(),
                              type: 'utility'
                            });
                            messages.value.push({
                              sender: 'bot',
                              text: `Wikipedia content for "${searchQuery}": [Simulated response] This is a placeholder for the actual Wikipedia content that would be fetched.`,
                              timestamp: new Date().toLocaleTimeString(),
                              type: 'response',
                              final: true
                            });
                            saveMessagesToStorage();
                          } catch (error) {
                            if (settings.value.message_display.show_utility) {
                              messages.value.push({
                                sender: 'bot',
                                text: `Error processing tool call arguments: ${error.message}`,
                                timestamp: new Date().toLocaleTimeString(),
                                type: 'utility'
                              });
                            }
                          }
                        }
                        const lastBotMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
                        if (lastBotMessageIndex >= 0) {
                          messages.value[lastBotMessageIndex].final = true;
                        }
                        saveMessagesToStorage();
                        currentToolCall = null;
                        return;
                      }
                      const lastBotMessageIndex = messages.value.findLastIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
                      if (lastBotMessageIndex >= 0) {
                        messages.value[lastBotMessageIndex].final = true;
                      }
                      saveMessagesToStorage();
                      reader.cancel();
                      return;
                    }
                  } else if (data.text) {
                      if (data.type === 'thought') {
                        fullThoughtText += data.text;
                        const lastThoughtMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'thought' && !msg.final);
                        if (lastThoughtMessageIndex >= 0) {
                          messages.value[lastThoughtMessageIndex].text = data.full_text || fullThoughtText;
                        } else if (settings.value.message_display.show_thoughts) {
                          messages.value.push({
                            sender: 'bot',
                            text: data.full_text || fullThoughtText,
                            timestamp: new Date().toLocaleTimeString(),
                            type: 'thought',
                            final: false
                          });
                        }
                      } else if (data.type === 'json') {
                        fullJsonText += data.text;
                        const lastJsonMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'json' && !msg.final);
                        if (lastJsonMessageIndex >= 0) {
                          messages.value[lastJsonMessageIndex].text = data.full_text || fullJsonText;
                        } else if (settings.value.message_display.show_json) {
                          messages.value.push({
                            sender: 'bot',
                            text: data.full_text || fullJsonText,
                            timestamp: new Date().toLocaleTimeString(),
                            type: 'json',
                            final: false
                          });
                        }
                      } else if (data.type === 'utility') {
                        fullUtilityText += data.text;
                        const lastUtilityMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'utility' && !msg.final);
                        if (lastUtilityMessageIndex >= 0) {
                          messages.value[lastUtilityMessageIndex].text = data.full_text || fullUtilityText;
                        } else if (settings.value.message_display.show_utility) {
                          messages.value.push({
                            sender: 'bot',
                            text: data.full_text || fullUtilityText,
                            timestamp: new Date().toLocaleTimeString(),
                            type: 'utility',
                            final: false
                          });
                        }
                      } else if (data.type === 'planning') {
                        fullPlanningText += data.text;
                        const lastPlanningMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'planning' && !msg.final);
                        if (lastPlanningMessageIndex >= 0) {
                          messages.value[lastPlanningMessageIndex].text = data.full_text || fullPlanningText;
                        } else if (settings.value.message_display.show_planning) {
                          messages.value.push({
                            sender: 'bot',
                            text: data.full_text || fullPlanningText,
                            timestamp: new Date().toLocaleTimeString(),
                            type: 'planning',
                            final: false
                          });
                        }
                      } else {
                        const currentMessageText = data.full_text || (fullResponseText + data.text);
                        fullResponseText = currentMessageText;
                        const lastBotMessageIndex = messages.value.findLastIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
                        if (lastBotMessageIndex >= 0) {
                          messages.value[lastBotMessageIndex].text = currentMessageText;
                        } else {
                          messages.value.push({
                            sender: 'bot',
                            text: currentMessageText,
                            timestamp: new Date().toLocaleTimeString(),
                            type: 'response',
                            final: false
                          });
                        }
                      }
                      nextTick(() => {
                        if (chatMessages.value && settings.value.chat.auto_scroll) {
                          chatMessages.value.scrollTop = chatMessages.value.scrollHeight;
                        }
                      });
                    }
                    if (data.done) {
                      const lastBotMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
                      if (lastBotMessageIndex >= 0) {
                        messages.value[lastBotMessageIndex].text = data.full_text || messages.value[lastBotMessageIndex].text;
                        messages.value[lastBotMessageIndex].final = true;
                      }
                      const lastThoughtMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'thought' && !msg.final);
                      if (lastThoughtMessageIndex >= 0) {
                        messages.value[lastThoughtMessageIndex].text = data.full_text || messages.value[lastThoughtMessageIndex].text;
                        messages.value[lastThoughtMessageIndex].final = true;
                      }
                      const lastJsonMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'json' && !msg.final);
                      if (lastJsonMessageIndex >= 0) {
                        messages.value[lastJsonMessageIndex].text = data.full_text || messages.value[lastJsonMessageIndex].text;
                        messages.value[lastJsonMessageIndex].final = true;
                      }
                      const lastUtilityMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'utility' && !msg.final);
                      if (lastUtilityMessageIndex >= 0) {
                        messages.value[lastUtilityMessageIndex].text = data.full_text || messages.value[lastUtilityMessageIndex].text;
                        messages.value[lastUtilityMessageIndex].final = true;
                      }
                      const lastPlanningMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'planning' && !msg.final);
                      if (lastPlanningMessageIndex >= 0) {
                        messages.value[lastPlanningMessageIndex].text = data.full_text || messages.value[lastPlanningMessageIndex].text;
                        messages.value[lastPlanningMessageIndex].final = true;
                      }
                      saveMessagesToStorage();
                      reader.cancel();
                      return;
                    }
                } catch (error) { // Catch for inner try block
                  logger.error('Error parsing JSON data:', error, 'from data:', dataStr);
                  if (settings.value.message_display.show_debug) {
                    messages.value.push({
                      sender: 'debug',
                      text: `Error parsing JSON data: ${error.message} from data: ${dataStr}`,
                      timestamp: new Date().toLocaleTimeString(),
                      type: 'debug'
                    });
                  }
                }
              }
            } else { // Else for dataMatches.length > 0
              if (settings.value.message_display.show_debug) {
                messages.value.push({
                  sender: 'debug',
                  text: `No data match found in chunk: ${chunk}`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'debug'
                });
              }
            }
          } catch (error) { // Catch for outer try block
            logger.error('Error parsing streaming data:', error, 'from chunk:', chunk);
            if (settings.value.message_display.show_debug) {
              messages.value.push({
                sender: 'debug',
                text: `Error parsing streaming data: ${error.message} from chunk: ${chunk}`,
                timestamp: new Date().toLocaleTimeString(),
                type: 'debug'
              });
            }
            messages.value.push({
              sender: 'bot',
              text: `Error: Streaming connection failed. Please try again.`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'response',
              final: true
            });
            saveMessagesToStorage();
          }
          readStream(); // Recursive call to continue reading the stream
        }).catch(error => { // Catch for the promise returned by reader.read().then()
          logger.error('Error reading stream:', error);
          if (settings.value.message_display.show_debug) {
            messages.value.push({
              sender: 'debug',
              text: `Error reading stream: ${error.message}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          }
          messages.value.push({
            sender: 'bot',
            text: `Error: Streaming connection failed. Please try again.`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'response',
            final: true
          });
          saveMessagesToStorage();
        });
      }
      readStream(); // Initial call to start reading the stream
    };

    const newChat = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/chats/new`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
          const newChatData = await response.json();
          messages.value = [];
          window.location.hash = `chatId=${newChatData.chatId}`;
          currentChatId.value = newChatData.chatId;
          logger.info('New Chat created:', newChatData.chatId);
          // Don't add an automatic welcome message - let the chat start clean
          // Update chat list
          chatList.value.push({ chatId: newChatData.chatId, name: newChatData.name || '' });
        } else {
          logger.error('Failed to create new chat:', response.statusText);
          messages.value.push({
            sender: 'bot',
            text: 'Failed to create new chat. Please check backend.',
            timestamp: new Date().toLocaleTimeString(),
            type: 'response'
          });
        }
      } catch (error) {
        logger.error('Error creating new chat:', error);
        messages.value.push({
          sender: 'bot',
          text: 'Error creating new chat. Please check backend.',
          timestamp: new Date().toLocaleTimeString(),
          type: 'response'
        });
      }
    };

    const resetChat = async () => {
      try {
        const chatId = window.location.hash.split('chatId=')[1];
        if (!chatId) {
          messages.value.push({
            sender: 'bot',
            text: 'No active chat to reset.',
            timestamp: new Date().toLocaleTimeString(),
            type: 'response'
          });
          return;
        }
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/chats/${chatId}/reset`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
      messages.value = [];
      messages.value.push({
        sender: 'bot',
        text: 'Chat reset successfully.',
        timestamp: new Date().toLocaleTimeString(),
        type: 'response'
      });
        } else {
          logger.error('Failed to reset chat:', response.statusText);
          messages.value.push({
            sender: 'bot',
            text: 'Failed to reset chat. Please check backend.',
            timestamp: new Date().toLocaleTimeString(),
            type: 'response'
          });
        }
      } catch (error) {
        logger.error('Error resetting chat:', error);
        messages.value.push({
          sender: 'bot',
          text: 'Error resetting chat. Please check backend.',
          timestamp: new Date().toLocaleTimeString(),
          type: 'response'
        });
      }
    };

    const deleteChat = async () => {
      const chatId = window.location.hash.split('chatId=')[1];
      if (!chatId) {
        messages.value.push({
          sender: 'bot',
          text: 'No active chat to delete.',
          timestamp: new Date().toLocaleTimeString(),
          type: 'response'
        });
        return;
      }
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/chats/${chatId}`, {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
          // Remove from local storage
          localStorage.removeItem(`chat_${chatId}_messages`);
          // Remove from chat list
          chatList.value = chatList.value.filter(chat => chat.chatId !== chatId);
          // If the deleted chat was active, clear messages
          if (!specificChatId || chatId === currentChatId.value) {
            messages.value = [];
            // Update current chat ID to null since no chat is active
            currentChatId.value = null;
            window.location.hash = '';
            messages.value.push({
              sender: 'bot',
              text: 'Chat deleted successfully. Click "New Chat" to start a new conversation.',
              timestamp: new Date().toLocaleTimeString(),
              type: 'response'
            });
          } else {
            logger.info(`Chat ${chatId} deleted successfully.`);
          }
        } else {
          logger.error('Failed to delete chat:', response.statusText);
          messages.value.push({
            sender: 'bot',
            text: 'Failed to delete chat. Please check backend.',
            timestamp: new Date().toLocaleTimeString(),
            type: 'response'
          });
        }
      } catch (error) {
        logger.error('Error deleting chat:', error);
        messages.value.push({
          sender: 'bot',
          text: 'Error deleting chat. Please check backend.',
          timestamp: new Date().toLocaleTimeString(),
          type: 'response'
        });
      }
    };

    const loadChatMessages = async (chatId) => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/chats/${chatId}`);
        if (response.ok) {
          const data = await response.json();
          messages.value = data;
            logger.info(`Loaded chat messages from backend for chat ${chatId}.`);
        } else {
          logger.error('Failed to load chat messages:', response.statusText);
          // Fallback to local storage if backend fails
          const persistedMessages = localStorage.getItem(`chat_${chatId}_messages`);
          if (persistedMessages) {
            messages.value = JSON.parse(persistedMessages);
            logger.info(`Loaded chat messages from local storage for chat ${chatId}.`);
          } else {
            messages.value = [];
            messages.value.push({
              sender: 'bot',
              text: 'No chat history found. How can I assist you?',
              timestamp: new Date().toLocaleTimeString(),
              type: 'response'
            });
          }
        }
      } catch (error) {
        logger.error('Error loading chat messages:', error);
        // Fallback to local storage if backend fails
        const persistedMessages = localStorage.getItem(`chat_${chatId}_messages`);
        if (persistedMessages) {
          messages.value = JSON.parse(persistedMessages);
            logger.info(`Loaded chat messages from local storage for chat ${chatId}.`);
        } else {
          messages.value = [];
        }
      }
    };

    const saveMessagesToStorage = async () => {
      const chatId = window.location.hash.split('chatId=')[1];
      if (!chatId) {
        logger.warn('No chat ID found to save messages.');
        return;
      }
      // Save to local storage
      localStorage.setItem(`chat_${chatId}_messages`, JSON.stringify(messages.value));
      // Also save to backend
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/chats/${chatId}/save`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ messages: messages.value })
        });
        if (!response.ok) {
          logger.error('Failed to save chat messages to backend:', response.statusText);
        } else {
          logger.info('Chat messages saved to backend successfully.');
        }
      } catch (error) {
        logger.error('Error saving chat messages to backend:', error);
      }
    };

    // Function to start the backend server
    const startBackendServer = async () => {
      backendStarting.value = true;
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/restart`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
          const result = await response.json();
          logger.info(`Backend server restart initiated: ${result.message}`);
        } else {
          logger.error('Failed to restart backend server:', response.statusText);
        }
      } catch (error) {
        logger.error('Error restarting backend server:', error);
      } finally {
        backendStarting.value = false;
      }
    };

    // Function to load chat list from backend or local storage
    const loadChatList = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/chats`);
        if (response.ok) {
          const data = await response.json();
          chatList.value = data.chats || [];
          logger.info(`Loaded chat list from backend with ${chatList.value.length} chats.`);
        } else {
          logger.error('Failed to load chat list from backend:', response.statusText);
          // Fallback to local storage
          loadChatListFromLocalStorage();
        }
      } catch (error) {
        logger.error('Error loading chat list from backend:', error);
        // Fallback to local storage
        loadChatListFromLocalStorage();
      }
    };

    // Function to build chat list from local storage
    const loadChatListFromLocalStorage = () => {
      const localChats = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key.startsWith('chat_') && key.endsWith('_messages')) {
          const chatId = key.split('_')[1];
          localChats.push({ chatId, name: '' });
        }
      }
      chatList.value = localChats;
      logger.info(`Loaded chat list from local storage with ${localChats.length} chats.`);
    };

    // Function to switch to a different chat
    const switchChat = async (chatId) => {
      if (chatId === currentChatId.value) return;
      window.location.hash = `chatId=${chatId}`;
      currentChatId.value = chatId;
      messages.value = [];
      // Always try to load from backend first
      await loadChatMessages(chatId);
    };

    // Function to get a preview of the chat for display in the history list
    const getChatPreview = (chatId) => {
      const persistedMessages = localStorage.getItem(`chat_${chatId}_messages`);
      if (persistedMessages) {
        try {
          const chatMessages = JSON.parse(persistedMessages);
          if (chatMessages.length > 0) {
            const userMessage = chatMessages.find(msg => msg.sender === 'user');
            if (userMessage && userMessage.text) {
              return userMessage.text.substring(0, 20) + (userMessage.text.length > 20 ? '...' : '');
            }
          }
        } catch (e) {
          logger.error('Error parsing chat messages for preview:', e);
        }
      }
      return '';
    };

    // Function to edit chat name
    const editChatName = (chatId) => {
      const newName = prompt('Enter a name for this chat:', chatList.value.find(chat => chat.chatId === chatId)?.name || '');
      if (newName) {
        const chatIndex = chatList.value.findIndex(chat => chat.chatId === chatId);
        if (chatIndex !== -1) {
          chatList.value[chatIndex].name = newName;
          // Save updated chat list to local storage
          localStorage.setItem('chat_list', JSON.stringify(chatList.value));
          logger.info(`Updated name for chat ${chatId} to "${newName}".`);
        }
      }
    };

    // Function to refresh chat list
    const refreshChatList = async () => {
      await loadChatList();
      logger.info(`Chat history list refreshed from backend.`);
    };

    // Function to handle specific chat deletion
    const deleteSpecificChat = async (specificChatId = null) => {
      const chatId = specificChatId || window.location.hash.split('chatId=')[1];
      if (!chatId) {
        messages.value.push({
          sender: 'bot',
          text: 'No active chat to delete.',
          timestamp: new Date().toLocaleTimeString(),
          type: 'response'
        });
        return;
      }
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/chats/${chatId}`, {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
          // Remove from local storage
          localStorage.removeItem(`chat_${chatId}_messages`);
          // Remove from chat list
          chatList.value = chatList.value.filter(chat => chat.chatId !== chatId);
          // If the deleted chat was active, clear messages
          if (!specificChatId || chatId === currentChatId.value) {
            messages.value = [];
            // Update current chat ID to null since no chat is active
            currentChatId.value = null;
            window.location.hash = '';
            messages.value.push({
              sender: 'bot',
              text: 'Chat deleted successfully. Click "New Chat" to start a new conversation.',
              timestamp: new Date().toLocaleTimeString(),
              type: 'response'
            });
          } else {
            logger.info(`Chat ${chatId} deleted successfully.`);
          }
        } else {
          logger.error('Failed to delete chat:', response.statusText);
          messages.value.push({
            sender: 'bot',
            text: 'Failed to delete chat. Please check backend.',
            timestamp: new Date().toLocaleTimeString(),
            type: 'response'
          });
        }
      } catch (error) {
        logger.error('Error deleting chat:', error);
        messages.value.push({
          sender: 'bot',
          text: 'Error deleting chat. Please check backend.',
          timestamp: new Date().toLocaleTimeString(),
          type: 'response'
        });
      }
    };

    // Initial load of chat messages based on URL hash
    onMounted(async () => {
      // Load settings from localStorage with fallback defaults
      try {
        const savedSettings = localStorage.getItem('chat-settings');
        if (savedSettings) {
          Object.assign(settings.value, JSON.parse(savedSettings));
        }
      } catch (e) {
        logger.error('Failed to load settings:', e);
        // Ensure default settings are applied
        settings.value = {
          message_display: {
            show_json: false,
            show_planning: true,
            show_debug: false,
            show_thoughts: true,
            show_utility: false
          },
          chat: {
            auto_scroll: true
          }
        };
      }

      // Connect WebSocket for real-time updates
      connectWebSocket();

      // Load chat list with timeout protection
      try {
        await Promise.race([
          refreshChatList(),
          new Promise((_, reject) => setTimeout(() => reject(new Error('Timeout')), 10000))
        ]);
      } catch (error) {
        logger.warn('Chat list loading timed out or failed, using fallback');
      }

      // Try to load the last used chat with fallback
      try {
        const lastChatId = localStorage.getItem('lastChatId');
        if (lastChatId && chatList.value.some(chat => chat.chatId === lastChatId)) {
          await switchChat(lastChatId);
        } else if (chatList.value.length > 0) {
          // Load the most recent chat
          await switchChat(chatList.value[0].chatId);
        } else {
          // Create new chat only if no chats exist
          await newChat();
        }
      } catch (error) {
        logger.error('Chat initialization failed:', error);
        // Ensure we have at least a default chat for the UI to work
        if (!currentChatId.value) {
          const defaultChatId = `default-${Date.now()}`;
          currentChatId.value = defaultChatId;
          localStorage.setItem('lastChatId', defaultChatId);
        }
      }
    });

    // Cleanup
    onUnmounted(() => {
      if (websocket.value) {
        websocket.value.close();
      }
    });

    return {
      sidebarCollapsed,
      terminalSidebarCollapsed,
      showTerminalSidebar,
      activeTab,
      inputMessage,
      messages,
      chatList,
      currentChatId,
      backendStarting,
      chatMessages,
      settings,
      filteredMessages,
      formatMessage,
      sendMessage,
      newChat,
      resetChat,
      deleteSpecificChat,
      switchChat,
      editChatName,
      getChatPreview,
      refreshChatList,
      reloadSystem,
      systemReloading,
      reloadNeeded,
      setReloadNeeded,
      openTerminalInNewTab,
      // File handling
      attachedFiles,
      handleFileAttachment,
      removeAttachment,
      getFileIcon,
      // Workflow handling
      activeWorkflowId,
      showWorkflowApproval,
      openFullWorkflowView,
      onWorkflowCancelled,
      // WebSocket
      connectWebSocket,
      handleWebSocketEvent,
      // Knowledge management
      showKnowledgeDialog,
      currentChatContext,
      chatFileAssociations,
      showKnowledgeManagement,
      onKnowledgeDecisionsApplied,
      onChatCompiled,
      // Command permission
      showCommandDialog,
      pendingCommand,
      onCommandApproved,
      onCommandDenied,
      onCommandCommented
    };
  }
};
</script>

<style scoped>
/* Message type specific styles */
.message-content {
  word-wrap: break-word;
  line-height: 1.5;
}

.message-content pre {
  background-color: #f1f5f9;
  padding: 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  overflow-x: auto;
  font-family: monospace;
}

/* Message type styles with headers */
.message-header {
  font-weight: 600;
  font-size: 0.875rem;
  margin-bottom: 0.5rem;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  display: inline-block;
}

.message-content {
  margin-top: 0.5rem;
  line-height: 1.5;
}

/* System message styling */
.message-content[data-type="system"] {
  background-color: #e0f2fe;
  border: 1px solid #0277bd;
  border-radius: 0.375rem;
  padding: 0.75rem;
  color: #01579b;
}

/* Error message styling */
.message-content[data-type="error"] {
  background-color: #ffebee;
  border: 1px solid #f44336;
  border-radius: 0.375rem;
  padding: 0.75rem;
  color: #c62828;
}

.thought-message {
  border-left: 4px solid #64748b;
  background-color: #f8fafc;
  padding: 0.75rem;
  margin: 0.5rem 0;
  border-radius: 0 0.5rem 0.5rem 0;
}

.thought-message .message-header {
  background-color: #64748b;
  color: white;
}

.thought-message .message-content {
  font-style: italic;
  color: #475569;
}

.planning-message {
  border-left: 4px solid #6366f1;
  background-color: #eef2ff;
  padding: 0.75rem;
  margin: 0.5rem 0;
  border-radius: 0 0.5rem 0.5rem 0;
}

.planning-message .message-header {
  background-color: #6366f1;
  color: white;
}

.planning-message .message-content {
  color: #3730a3;
  font-weight: 500;
}

.utility-message {
  border-left: 4px solid #10b981;
  background-color: #ecfdf5;
  padding: 0.75rem;
  margin: 0.5rem 0;
  border-radius: 0 0.5rem 0.5rem 0;
}

.utility-message .message-header {
  background-color: #10b981;
  color: white;
}

.utility-message .message-content {
  color: #047857;
}

.debug-message {
  border-left: 4px solid #eab308;
  background-color: #fefce8;
  padding: 0.75rem;
  margin: 0.5rem 0;
  border-radius: 0 0.5rem 0.5rem 0;
}

.debug-message .message-header {
  background-color: #eab308;
  color: white;
}

.debug-message .message-content {
  color: #92400e;
  font-family: monospace;
  font-size: 0.875rem;
}

.json-message {
  border-left: 4px solid #8b5cf6;
  background-color: #f5f3ff;
  padding: 0.75rem;
  margin: 0.5rem 0;
  border-radius: 0 0.5rem 0.5rem 0;
}

.json-message .message-header {
  background-color: #8b5cf6;
  color: white;
}

.json-message .message-content {
  color: #6d28d9;
  font-family: monospace;
  font-size: 0.875rem;
  background-color: #f8fafc;
  padding: 0.5rem;
  border-radius: 0.25rem;
  margin-top: 0.5rem;
  overflow-x: auto;
}

.tool-output-message {
  border-left: 4px solid #06b6d4;
  background-color: #ecfeff;
  padding: 0.75rem;
  margin: 0.5rem 0;
  border-radius: 0 0.5rem 0.5rem 0;
}

.tool-output-message .message-header {
  background-color: #06b6d4;
  color: white;
}

.tool-output-message .message-content {
  color: #0891b2;
  font-family: monospace;
  font-size: 0.875rem;
}

.regular-message {
  padding: 0.75rem;
  margin: 0.5rem 0;
  background-color: white;
  border-radius: 0.5rem;
  line-height: 1.6;
}

/* File attachment styles */
.attached-file-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #e5e7eb;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 0.875rem;
}

.attached-file-chip .file-icon {
  font-size: 1rem;
}

.attached-file-chip .remove-btn {
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  font-size: 1.2rem;
  line-height: 1;
  padding: 0;
  margin-left: 4px;
}

.attached-file-chip .remove-btn:hover {
  color: #ef4444;
}

.btn-secondary {
  background-color: #6b7280;
  color: white;
  border: none;
  border-radius: 0.375rem;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-secondary:hover {
  background-color: #4b5563;
}

/* Workflow modal styles */
.workflow-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.workflow-modal {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 1200px;
  max-height: 90%;
  overflow: hidden;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e5e7eb;
  background: #f9fafb;
}

.modal-header h2 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 600;
  color: #111827;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.25rem;
  color: #6b7280;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
}

.close-btn:hover {
  background: #e5e7eb;
  color: #374151;
}

.modal-content {
  height: calc(90vh - 80px);
  overflow-y: auto;
}

/* Workflow message type */
.message-content[data-type="workflow"] {
  background-color: #eff6ff;
  border: 1px solid #3b82f6;
  border-radius: 0.375rem;
  padding: 0.75rem;
  color: #1e40af;
}
</style>
