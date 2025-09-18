<template>
  <ErrorBoundary fallback="Chat interface failed to load. Please refresh the page.">
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
        <div class="flex-1 overflow-y-auto p-4" v-if="!sidebarCollapsed" style="max-height: calc(100vh - 300px);">
          <h3 class="text-lg font-semibold text-blueGray-700 mb-4">Chat History</h3>
          <div class="space-y-2 mb-6">
            <div v-for="chat in chatList" :key="chat.chatId" class="p-3 rounded-lg cursor-pointer transition-all duration-150" :class="currentChatId === chat.chatId ? 'bg-indigo-100 border border-indigo-200' : 'bg-white hover:bg-blueGray-50 border border-blueGray-200'" @click="switchChat(chat.chatId)" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
              <div class="flex items-center justify-between">
                <span class="text-sm text-blueGray-700 truncate">{{ chat.name || getChatPreview(chat.chatId) || `Chat ${chat.chatId ? chat.chatId.slice(0, 8) : 'Unknown'}...` }}</span>
                <div class="flex items-center space-x-1">
                  <button class="text-blueGray-400 hover:text-blueGray-600 p-1" @click.stop="editChatName(chat.chatId)" title="Edit Name">
                    <i class="fas fa-edit text-xs"></i>
                  </button>
                  <button class="text-red-400 hover:text-red-600 p-1" @click.stop="deleteSpecificChat(chat.chatId)" title="Delete">
                    <i class="fas fa-trash text-xs"></i>
                  </button>
                </div>
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
              <input type="checkbox" v-model="settings.message_display.show_thoughts" class="mr-2" id="show-thoughts" />
              <span class="text-sm text-blueGray-600" for="show-thoughts">Show Thoughts</span>
            </label>
            <label class="flex items-center">
              <input type="checkbox" v-model="settings.message_display.show_json" class="mr-2" id="show-json" />
              <span class="text-sm text-blueGray-600" for="show-json">Show JSON Output</span>
            </label>
            <label class="flex items-center">
              <input type="checkbox" v-model="settings.message_display.show_utility" class="mr-2" id="show-utility" />
              <span class="text-sm text-blueGray-600" for="show-utility">Show Utility Messages</span>
            </label>
            <label class="flex items-center">
              <input type="checkbox" v-model="settings.browser_integration.enabled" class="mr-2" id="browser-enabled" />
              <span class="text-sm text-blueGray-600" for="browser-enabled">Enable Browser Automation</span>
            </label>
            <label class="flex items-center">
              <input type="checkbox" v-model="settings.message_display.show_planning" class="mr-2" id="show-planning" />
              <span class="text-sm text-blueGray-600" for="show-planning">Show Planning Messages</span>
            </label>
            <label class="flex items-center">
              <input type="checkbox" v-model="settings.message_display.show_debug" class="mr-2" id="show-debug" />
              <span class="text-sm text-blueGray-600" for="show-debug">Show Debug Messages</span>
            </label>
            <label class="flex items-center">
              <input type="checkbox" v-model="settings.message_display.show_sources" class="mr-2" id="show-sources" />
              <span class="text-sm text-blueGray-600" for="show-sources">Show Sources</span>
            </label>
            <label class="flex items-center">
              <input type="checkbox" v-model="settings.chat.auto_scroll" class="mr-2" id="auto-scroll" />
              <span class="text-sm text-blueGray-600" for="auto-scroll">Autoscroll</span>
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
                  <!-- Knowledge Base Status -->
                  <div class="kb-status-group">
                    <div class="kb-status-indicator" :title="kbStatus.message">
                      <div 
                        class="status-dot" 
                        :class="{
                          'status-ready': kbStatus.status === 'ready' || kbStatus.status === 'completed',
                          'status-loading': kbStatus.status === 'ingesting',
                          'status-empty': kbStatus.status === 'empty',
                          'status-error': kbStatus.status === 'error'
                        }"
                      ></div>
                      <span class="status-text">KB: {{ kbStatus.documents_processed }} docs</span>
                    </div>
                    <button 
                      v-if="kbStatus.documents_processed > 0"
                      @click="browseKnowledgeBase"
                      class="kb-browse-btn"
                      title="Browse knowledge base content"
                    >
                      <i class="fas fa-book-open"></i>
                    </button>
                  </div>
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
            <div class="flex-1 p-4">
              <!-- Unified Research Browser Component -->
              <ResearchBrowser
                :session-id="currentResearchSession"
                :research-data="researchResults"
                class="flex-1"
              />
            </div>
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
  </ErrorBoundary>
</template>

<script>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { useGlobalWebSocket } from '@/composables/useGlobalWebSocket.js';
import { generateChatId } from '@/utils/ChatIdGenerator.js';
import TerminalSidebar from './TerminalSidebar.vue';
import TerminalWindow from './TerminalWindow.vue';
import WorkflowApproval from './WorkflowApproval.vue';
import WorkflowProgressWidget from './WorkflowProgressWidget.vue';
import KnowledgePersistenceDialog from './KnowledgePersistenceDialog.vue';
import CommandPermissionDialog from './CommandPermissionDialog.vue';
// Desktop viewer components (placeholder implementation)
import PlaywrightDesktopViewer from './PlaywrightDesktopViewer.vue';
import ComputerDesktopViewer from './ComputerDesktopViewer.vue';
import ResearchBrowser from './ResearchBrowser.vue';
import ErrorBoundary from './ErrorBoundary.vue';
import apiClient from '../utils/ApiClient.js';
import { apiService } from '@/services/api.js';
import { API_CONFIG } from '@/config/environment.js';

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
    ComputerDesktopViewer,
    ResearchBrowser,
    ErrorBoundary
  },
  setup() {
    // Global WebSocket Service with error handling
    const wsService = useGlobalWebSocket();
    const wsConnected = wsService?.isConnected || ref(false);
    const wsOn = wsService?.on || (() => () => {});
    const wsSend = wsService?.send || (() => false);
    const wsState = wsService?.state || ref({});

    // Reactive state
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

    // Knowledge Base Status
    const kbStatus = ref({
      status: 'loading',
      message: 'Loading knowledge base status...',
      progress: 0,
      current_operation: null,
      documents_processed: 0,
      documents_total: 0,
      last_updated: null
    });

    // Message Display Controls

    // Research Browser state
    const currentResearchSession = ref(null);
    const researchResults = ref(null);
    const showResearchBrowser = ref(false);

    // Workflow state
    const activeWorkflowId = ref(null);
    const showWorkflowApproval = ref(false);

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

    // Settings
    const settings = ref({
      message_display: {
        show_json: false,
        show_planning: true,
        show_debug: false,
        show_thoughts: true,
        show_utility: false,
        show_sources: true  // Default on for source attribution
      },
      browser_integration: {
        enabled: false,
        auto_search: false,
        auto_screenshot: false,
        show_browser_actions: true
      },
      chat: {
        auto_scroll: true
      }
    });

    // Computed properties
    const filteredMessages = computed(() => {
      return messages.value.filter(message => {
        // Filter based on message type and display toggles from settings
        if (message.type === 'thought' && !settings.value.message_display.show_thoughts) return false;
        if (message.type === 'json' && !settings.value.message_display.show_json) return false;
        if (message.type === 'utility' && !settings.value.message_display.show_utility) return false;
        if (message.type === 'planning' && !settings.value.message_display.show_planning) return false;
        if (message.type === 'debug' && !settings.value.message_display.show_debug) return false;
        if (message.type === 'source' && !settings.value.message_display.show_sources) return false;

        // Always show regular user/assistant messages
        if (!message.type || message.type === 'user' || message.type === 'assistant') return true;

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
        } else {
          // Non-JSON output
          messages.push({
            type: 'utility',
            text: outputContent,
            order: toolMatch.index + 1
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
        case 'source':
        case 'source_attribution':
          return `<div class="source-attribution-message">
            <div class="message-header">📋 Sources</div>
            <div class="message-content">${escapedText}</div>
          </div>`;
        case 'research_summary':
          return `<div class="research-summary-message">
            <div class="message-header">🔍 Research Results</div>
            <div class="message-content">${escapedText}</div>
            <div class="research-action mt-2 text-sm text-blue-600">
              💡 Switch to Browser tab to interact with research sessions
            </div>
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
        console.error('Failed to load chat context:', error);
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
        console.error('Failed to associate file with chat:', error);
      }
    };

    const fetchKnowledgeBaseStatus = async () => {
      try {
        const response = await apiClient.get('/api/knowledge_base/ingestion/status');
        if (response) {
          kbStatus.value = {
            status: response.status || 'unknown',
            message: response.message || 'Status unknown',
            progress: response.progress || 0,
            current_operation: response.current_operation,
            documents_processed: response.documents_processed || 0,
            documents_total: response.documents_total || 0,
            last_updated: response.last_updated
          };
        }
      } catch (error) {
        console.error('Failed to fetch knowledge base status:', error);
        kbStatus.value = {
          status: 'error',
          message: 'Failed to load KB status',
          progress: 0,
          current_operation: null,
          documents_processed: 0,
          documents_total: 0,
          last_updated: null
        };
      }
    };

    const showKnowledgeManagement = () => {
      showKnowledgeDialog.value = true;
    };

    const browseKnowledgeBase = () => {
      // Navigate to the knowledge management page (entries browser)
      window.open('/knowledge/manage', '_blank');
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
      // Command approved
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
      // Command denied
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
      // Command commented
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
            try {
              const result = await apiClient.uploadFile(file);
              uploadedFilePaths.push(result.path || file.name);

              // Associate file with current chat
              await associateFileWithChat(result.path || file.name, file.name);
            } catch (uploadError) {
              // File upload failed - notify user
              const errorMessage = `Failed to upload file "${file.name}": ${uploadError.message}`;
              console.error('File upload failed:', errorMessage);

              messages.value.push({
                sender: 'system',
                text: `📎 ❌ ${errorMessage}`,
                timestamp: new Date().toLocaleTimeString(),
                type: 'error'
              });

              // Continue with other files, but note the failure
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

        // Try direct chat endpoint first for faster responses
        let chatResponse;
        try {
          chatResponse = await apiClient.sendChatMessage(userInput, { chatId: currentChatId.value, ...messageData });
        } catch (error) {
          console.warn('🔄 Direct chat failed, falling back to workflow orchestration:', error.message);
          // Fallback to workflow orchestration if direct chat fails
          try {
            chatResponse = await apiClient.executeWorkflow(`Please respond to: ${userInput}`, false);
          } catch (workflowError) {
            console.error('Both chat and workflow failed:', workflowError);
            throw new Error('Unable to send message - both chat and workflow endpoints failed');
          }
        }

        // Process response data (ApiClient returns data directly, not response objects)
        if (chatResponse) {
          // ApiClient already handles JSON parsing and validation
          let workflowResult = chatResponse;

          // Debug logging for troubleshooting
          console.log('✅ Chat/Workflow result received:', {
            type: workflowResult.type,
              hasResult: !!workflowResult.result,
              hasWorkflowResponse: !!workflowResult.workflow_response,
              hasData: !!workflowResult.data,
              keys: Object.keys(workflowResult)
            });

          // Handle direct chat response with workflow messages
          if (workflowResult.type === 'json' && workflowResult.data) {
            // First, add any workflow messages if present
            if (workflowResult.data.workflow_messages && Array.isArray(workflowResult.data.workflow_messages)) {
              for (const wfMsg of workflowResult.data.workflow_messages) {
                messages.value.push({
                  sender: wfMsg.sender || 'assistant',
                  text: wfMsg.text || '',
                  timestamp: wfMsg.timestamp || new Date().toLocaleTimeString(),
                  type: wfMsg.type || 'message',
                  metadata: wfMsg.metadata || {}
                });
              }
            }

            // Then add the main response
            const responseText = workflowResult.data.response || 'No response received';
            messages.value.push({
              sender: 'bot',
              text: responseText,
              timestamp: new Date().toLocaleTimeString(),
              type: 'response'
            });
          } else if (workflowResult.type === 'workflow_orchestration') {
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
          } else if (workflowResult.type === 'direct_execution' || !workflowResult.type) {
            // Direct execution or simple response
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
          // Workflow failed, show error and try fallback
          console.warn(`Workflow API failed with status ${workflowResponse.status}: ${workflowResponse.statusText}`);

          // Notify user about workflow failure
          messages.value.push({
            sender: 'system',
            text: `⚠️ Workflow orchestration unavailable (${workflowResponse.status}). Falling back to direct chat...`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'warning'
          });

          // Workflow failed, falling back to regular chat endpoint
          try {
            const chatResponse = await apiClient.sendChatMessage(userInput, {
              chatId: currentChatId.value || 'default'
            });

            if (chatResponse.type === 'json' && chatResponse.data) {
              // First, add any workflow messages if present
              if (chatResponse.data.workflow_messages && Array.isArray(chatResponse.data.workflow_messages)) {
                for (const wfMsg of chatResponse.data.workflow_messages) {
                  messages.value.push({
                    sender: wfMsg.sender || 'assistant',
                    text: wfMsg.text || '',
                    timestamp: wfMsg.timestamp || new Date().toLocaleTimeString(),
                    type: wfMsg.type || 'message',
                    metadata: wfMsg.metadata || {}
                  });
                }
              }

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

                // Handle research results if present
                if (chatResponse.data.research && chatResponse.data.research.success && chatResponse.data.research.results) {
                  researchResults.value = chatResponse.data.research;

                  // Check if any results have interaction required
                  const hasInteraction = chatResponse.data.research.results.some(result =>
                    result.interaction_required || result.status === 'interaction_required'
                  );

                  if (hasInteraction) {
                    showResearchBrowser.value = true;
                    currentResearchSession.value = chatResponse.data.research.results.find(r => r.session_id)?.session_id || null;
                  }

                  // Add research summary message
                  const resultCount = chatResponse.data.research.results.length;
                  const interactionCount = chatResponse.data.research.results.filter(r => r.interaction_required).length;

                  let researchSummary = `🔍 **Research completed**: ${resultCount} results found`;
                  if (interactionCount > 0) {
                    researchSummary += ` (${interactionCount} require user interaction)`;
                  }

                  messages.value.push({
                    sender: 'system',
                    text: researchSummary,
                    timestamp: new Date().toLocaleTimeString(),
                    type: 'research_summary',
                    researchData: chatResponse.data.research
                  });
                }
              }
            } else {
              throw new Error('Invalid response from chat endpoint');
            }
          } catch (fallbackError) {
            console.error('Fallback chat also failed:', fallbackError);
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
        console.error('Chat interface error:', error);
        console.error('Error type:', error.constructor.name);

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
        const newChatId = data.chatId || generateChatId();

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
        console.error('Error creating new chat:', error);
        // Fallback to local chat creation
        const newChatId = generateChatId();
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

    const resetChat = async () => {
      if (!currentChatId.value) return;
      
      try {
        await apiClient.resetChat(currentChatId.value);
        messages.value = [];
        showSuccess('Chat reset successfully');
      } catch (error) {
        console.error('Failed to reset chat:', error);
        showError(`Failed to reset chat: ${error.message}`);
      }
    };

    const deleteSpecificChat = async (chatId = null) => {
      // CRITICAL FIX: Validate chatId parameter to prevent PointerEvent objects
      const isValidChatId = chatId && typeof chatId === 'string' && chatId.length > 0;
      const targetChatId = isValidChatId ? chatId : currentChatId.value;
      if (!targetChatId || typeof targetChatId !== 'string') {
        console.error('Invalid chat ID for deletion:', targetChatId);
        return;
      }

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
            // Don't auto-create new chat - let user create manually
            currentChatId.value = null;
            localStorage.removeItem('lastChatId');
          }
        }
      } catch (error) {
        // Handle 404 errors silently (expected for legacy chats)
        if (error.message && error.message.includes('404')) {
          // Legacy chats may not exist on backend - just remove from frontend silently
          console.debug(`Chat ${targetChatId} not found on backend (legacy format) - removing from local list`);
        } else {
          // Only log unexpected errors
          console.error('Unexpected error deleting chat:', error);
        }

        // Always update frontend state regardless of backend result
        // This ensures chat deletion appears to work for users
        chatList.value = chatList.value.filter(chat => chat.chatId !== targetChatId);

        if (currentChatId.value === targetChatId) {
          messages.value = [];
          if (chatList.value.length > 0) {
            switchChat(chatList.value[0].chatId);
          } else {
            // Don't auto-create new chat - let user create manually
            currentChatId.value = null;
            localStorage.removeItem('lastChatId');
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
        console.error('Error loading chat list:', error);

        // Show user-friendly error for chat list loading
        let errorMessage = 'Failed to load chat history';
        if (error.message?.includes('timeout')) {
          errorMessage = '📝 Chat list timeout - using offline mode';
        } else if (error.message?.includes('Network') || error.message?.includes('fetch')) {
          errorMessage = '📝 Network error - chat list unavailable';
        }

        // Add subtle error notification
        messages.value.push({
          sender: 'system',
          text: errorMessage,
          timestamp: new Date().toLocaleTimeString(),
          type: 'info'
        });

        // Keep chat list empty if it fails to load - don't create fallback chats
        console.log('Chat list remains empty - user can create new chat manually');
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
        console.error('Error loading chat messages:', error);

        // Show user-friendly error for message loading
        let errorMessage = 'Failed to load chat messages';
        if (error.message?.includes('timeout')) {
          errorMessage = '💬 Message loading timeout - starting fresh chat';
        } else if (error.message?.includes('Network') || error.message?.includes('fetch')) {
          errorMessage = '💬 Network error - starting new conversation';
        }

        messages.value = [{
          sender: 'system',
          text: errorMessage,
          timestamp: new Date().toLocaleTimeString(),
          type: 'info'
        }];
      }
    };

    const saveChatMessages = async (chatId) => {
      try {
        await apiClient.saveChatMessages(chatId, messages.value);
      } catch (error) {
        console.error('Error saving chat messages:', error);

        // Show user-friendly error message for different types of failures
        let errorMessage = 'Failed to save chat messages';

        if (error.message?.includes('timeout')) {
          errorMessage = `💾 Chat save timeout - your messages are preserved locally but couldn't sync to server`;
        } else if (error.message?.includes('Network') || error.message?.includes('fetch')) {
          errorMessage = `💾 Network error - chat messages saved locally only`;
        } else {
          errorMessage = `💾 Save error: ${error.message || 'Unknown error'}`;
        }

        // Add non-intrusive error notification
        messages.value.push({
          sender: 'system',
          text: errorMessage,
          timestamp: new Date().toLocaleTimeString(),
          type: 'warning'
        });
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
        console.error('Failed to reload system:', error);

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

    // WebSocket methods - now using global WebSocket service
    const connectWebSocket = () => {
      console.log('🔌 Using global WebSocket service, connection state:', wsConnected.value);
      // Global WebSocket service handles connection automatically
    };

    const handleWebSocketEvent = (eventData) => {
      const eventType = eventData.type;
      const payload = eventData.payload;

      // Handle ping/pong for keepalive
      if (eventType === 'ping') {
        // Respond with pong using global WebSocket service
        wsSend({ type: 'pong' });
        return;
      }

      if (eventType === 'llm_response') {
        // Handle LLM responses from WebSocket
        console.log('📨 Processing LLM response from WebSocket:', payload);

        // Add the response to messages
        messages.value.push({
          sender: payload.sender || 'bot',
          text: payload.response || payload.content || 'No response content',
          timestamp: new Date().toLocaleTimeString(),
          type: payload.message_type || 'response',
          sources: payload.sources || []
        });

        // Auto-scroll to show new message
        nextTick(() => {
          if (chatMessages.value && settings.value.chat.auto_scroll) {
            chatMessages.value.scrollTop = chatMessages.value.scrollHeight;
          }
        });

        return; // Early return to avoid duplicate handling
      }

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

    // Initialize
    onMounted(async () => {
      // Load settings from localStorage with fallback defaults
      try {
        const savedSettings = localStorage.getItem('chat-settings');
        if (savedSettings) {
          Object.assign(settings.value, JSON.parse(savedSettings));
        }
      } catch (e) {
        console.error('Failed to load settings:', e);
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

      // Set up WebSocket event listeners for chat functionality
      // Global WebSocket service handles the connection automatically
      console.log('🔌 Setting up chat WebSocket listeners, connection state:', wsState.value.connected);

      // Listen for chat-relevant events
      wsOn('connection_established', (data) => {
        console.log('✅ Chat interface connected to WebSocket');

        // Show connection restored message if there were previous errors
        messages.value.push({
          sender: 'system',
          text: '🔌 Real-time connection established',
          timestamp: new Date().toLocaleTimeString(),
          type: 'success'
        });
      });

      wsOn('llm_response', (data) => {
        console.log('📨 Received LLM response via WebSocket:', data);
        if (data.payload && data.payload.response) {
          handleWebSocketEvent(data);
        }
      });

      wsOn('error', (data) => {
        console.log('❌ WebSocket error in chat interface:', data);

        // Show user-visible error notification
        messages.value.push({
          sender: 'system',
          text: `🔌 Connection issue: Real-time updates may be delayed. ${data?.message || 'WebSocket error'}`,
          timestamp: new Date().toLocaleTimeString(),
          type: 'error'
        });
      });

      wsOn('message', (eventData) => {
        // Handle all WebSocket messages for chat functionality
        handleWebSocketEvent(eventData);
      });

      // Watch for tab changes - WebSocket connection is now global
      watch(activeTab, (newTab, oldTab) => {
        console.log('📱 Tab changed from', oldTab, 'to', newTab, 'WebSocket connected:', wsConnected.value);
        // Global WebSocket service maintains connection across all tabs
        // No need to manage connection per tab
      });

      // Load chat list with timeout protection
      try {
        await Promise.race([
          refreshChatList(),
          new Promise((_, reject) => setTimeout(() => reject(new Error('Timeout')), 10000))
        ]);
      } catch (error) {
        console.warn('Chat list loading timed out or failed, using fallback');
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
        console.error('Chat initialization failed:', error);
        // Don't create default chats automatically - user should create manually
        console.log('User needs to create a new chat manually');
      }

      // Initialize knowledge base status and set up periodic updates
      try {
        await fetchKnowledgeBaseStatus();
        
        // Set up periodic status updates every 5 seconds
        const kbStatusInterval = setInterval(fetchKnowledgeBaseStatus, 5000);
        
        // Clean up interval on unmount
        onUnmounted(() => {
          clearInterval(kbStatusInterval);
        });
      } catch (error) {
        console.error('Failed to initialize knowledge base status:', error);
      }
    });


    // Cleanup
    onUnmounted(() => {
      console.log('🔌 ChatInterface unmounted, global WebSocket service continues running');
      // Global WebSocket service continues running for other components
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
      // Message Display Controls
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
      // WebSocket (using global service)
      wsConnected,
      wsState,
      handleWebSocketEvent,
      // Knowledge management
      showKnowledgeDialog,
      currentChatContext,
      chatFileAssociations,
      showKnowledgeManagement,
      onKnowledgeDecisionsApplied,
      onChatCompiled,
      // Knowledge base status
      kbStatus,
      fetchKnowledgeBaseStatus,
      browseKnowledgeBase,
      // Command permission
      showCommandDialog,
      pendingCommand,
      onCommandApproved,
      onCommandDenied,
      onCommandCommented,
      // Research Browser
      currentResearchSession,
      researchResults,
      showResearchBrowser
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

.source-attribution-message {
  border-left: 4px solid #3b82f6;
  background-color: #eff6ff;
  padding: 0.75rem;
  margin: 0.5rem 0;
  border-radius: 0 0.5rem 0.5rem 0;
}

.source-attribution-message .message-header {
  background-color: #3b82f6;
  color: white;
  padding: 0.25rem 0.75rem;
  margin: -0.75rem -0.75rem 0.5rem -0.75rem;
  border-radius: 0 0.5rem 0 0;
  font-weight: 600;
  font-size: 0.875rem;
}

.source-attribution-message .message-content {
  color: #1e40af;
  font-size: 0.875rem;
  line-height: 1.5;
}

.source-attribution-message .message-content ul {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}

.source-attribution-message .message-content li {
  margin: 0.25rem 0;
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

.research-summary-message {
  border-left: 4px solid #10b981;
  background-color: #ecfdf5;
  padding: 0.75rem;
  margin: 0.5rem 0;
  border-radius: 0 0.5rem 0.5rem 0;
}

.research-summary-message .message-header {
  background-color: #10b981;
  color: white;
  padding: 0.25rem 0.75rem;
  margin: -0.75rem -0.75rem 0.5rem -0.75rem;
  border-radius: 0 0.5rem 0 0;
  font-weight: 600;
  font-size: 0.875rem;
}

.research-summary-message .message-content {
  color: #059669;
  font-size: 0.875rem;
  line-height: 1.5;
}

.research-summary-message .research-action {
  color: #3b82f6;
  font-style: italic;
}

/* Knowledge Base Status Group */
.kb-status-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Knowledge Base Status Indicator */
.kb-status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  color: #374151;
  cursor: help;
}

.kb-status-indicator .status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.kb-status-indicator .status-dot.status-ready {
  background-color: #10b981; /* Green for ready/completed */
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);
}

.kb-status-indicator .status-dot.status-loading {
  background-color: #f59e0b; /* Amber for loading */
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.2);
  animation: pulse 1.5s infinite;
}

.kb-status-indicator .status-dot.status-empty {
  background-color: #9ca3af; /* Gray for empty */
  box-shadow: 0 0 0 2px rgba(156, 163, 175, 0.2);
}

.kb-status-indicator .status-dot.status-error {
  background-color: #ef4444; /* Red for error */
  box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.2);
}

.kb-status-indicator .status-text {
  color: #6b7280;
  font-size: 11px;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

/* Knowledge Base Browse Button */
.kb-browse-btn {
  padding: 6px 8px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.2s ease;
  min-width: 28px;
  height: 28px;
}

.kb-browse-btn:hover {
  background: #2563eb;
}

.kb-browse-btn:active {
  background: #1d4ed8;
}

.kb-browse-btn i {
  font-size: 11px;
}
</style>
