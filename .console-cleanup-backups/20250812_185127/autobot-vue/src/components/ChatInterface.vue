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
    <!-- Sidebar -->
    <div class="w-80 bg-blueGray-100 border-r border-blueGray-200 flex flex-col h-full overflow-hidden transition-all duration-300 flex-shrink-0" :class="{ 'w-12': sidebarCollapsed }">
        <button class="p-3 border-b border-blueGray-200 text-blueGray-600 hover:bg-blueGray-200 transition-colors flex-shrink-0" @click="sidebarCollapsed = !sidebarCollapsed">
          <i :class="sidebarCollapsed ? 'fas fa-chevron-right' : 'fas fa-chevron-left'"></i>
        </button>
        <div class="flex-1 overflow-y-auto p-4" v-if="!sidebarCollapsed" style="max-height: calc(100vh - 300px);">
          <h3 class="text-lg font-semibold text-blueGray-700 mb-4">Chat History</h3>
          <div class="space-y-2 mb-6">
            <div v-for="chat in chatList" :key="chat.chatId" class="p-3 rounded-lg cursor-pointer transition-all duration-150" :class="currentChatId === chat.chatId ? 'bg-indigo-100 border border-indigo-200' : 'bg-white hover:bg-blueGray-50 border border-blueGray-200'" @click="switchChat(chat.chatId)">
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
              <button class="btn btn-primary text-xs" @click="newChat">
                <i class="fas fa-plus mr-1"></i>
                New
              </button>
              <button class="btn btn-secondary text-xs" @click="resetChat" :disabled="!currentChatId">
                <i class="fas fa-redo mr-1"></i>
                Reset
              </button>
              <button class="btn btn-danger text-xs" @click="deleteSpecificChat" :disabled="!currentChatId">
                <i class="fas fa-trash mr-1"></i>
                Delete
              </button>
              <button class="btn btn-outline text-xs" @click="refreshChatList">
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
            <button class="btn btn-primary w-full" @click="reloadSystem" :disabled="systemReloading">
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
            <button @click="reloadSystem" class="mt-2 text-xs bg-yellow-600 text-white px-3 py-1 rounded hover:bg-yellow-700">
              Reload Now
            </button>
          </div>
        </div>
    </div>

    <!-- Main Chat Container -->
    <div class="flex-1 flex h-full overflow-hidden">
      <!-- Chat Content Area -->
      <div class="flex-1 flex flex-col h-full">
          <!-- Chat/Terminal Tabs -->
          <div class="flex border-b border-blueGray-200 bg-white flex-shrink-0">
            <button 
              @click="activeTab = 'chat'" 
              :class="['px-6 py-3 text-sm font-medium transition-colors', activeTab === 'chat' ? 'border-b-2 border-indigo-500 text-indigo-600 bg-indigo-50' : 'text-blueGray-600 hover:text-blueGray-800 hover:bg-blueGray-50']"
            >
              <i class="fas fa-comments mr-2"></i>
              Chat
            </button>
            <button 
              @click="activeTab = 'terminal'" 
              :class="['px-6 py-3 text-sm font-medium transition-colors', activeTab === 'terminal' ? 'border-b-2 border-indigo-500 text-indigo-600 bg-indigo-50' : 'text-blueGray-600 hover:text-blueGray-800 hover:bg-blueGray-50']"
            >
              <i class="fas fa-terminal mr-2"></i>
              Terminal
            </button>
          </div>

          <!-- Chat Tab Content -->
          <div v-if="activeTab === 'chat'" class="flex-1 flex flex-col h-full">
            <!-- Chat Messages -->
            <div class="flex-1 overflow-y-auto p-6 space-y-4" ref="chatMessages" role="log" style="max-height: calc(100vh - 350px); min-height: 400px;">
            <div v-for="(message, index) in filteredMessages" :key="index" class="flex" :class="message.sender === 'user' ? 'justify-end' : 'justify-start'">
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
                <div v-for="(file, index) in attachedFiles" :key="index" class="attached-file-chip">
                  <span class="file-icon">{{ getFileIcon(file) }}</span>
                  <span class="file-name">{{ file.name }}</span>
                  <button @click="removeAttachment(index)" class="remove-btn">&times;</button>
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
                  >
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
    <div v-if="showWorkflowApproval" class="workflow-modal-overlay" @click="showWorkflowApproval = false">
      <div class="workflow-modal" @click.stop>
        <div class="modal-header">
          <h2>Workflow Management</h2>
          <button @click="showWorkflowApproval = false" class="close-btn">
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
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue';
import TerminalSidebar from './TerminalSidebar.vue';
import TerminalWindow from './TerminalWindow.vue';
import WorkflowApproval from './WorkflowApproval.vue';
import WorkflowProgressWidget from './WorkflowProgressWidget.vue';
import KnowledgePersistenceDialog from './KnowledgePersistenceDialog.vue';
import apiClient from '../utils/ApiClient.js';
import { apiService } from '@/services/api.js';

export default {
  name: 'ChatInterface',
  components: {
    TerminalSidebar,
    TerminalWindow,
    WorkflowApproval,
    WorkflowProgressWidget,
    KnowledgePersistenceDialog
  },
  setup() {
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

    // Workflow state
    const activeWorkflowId = ref(null);
    const showWorkflowApproval = ref(false);
    const websocket = ref(null);
    
    // Knowledge management state
    const showKnowledgeDialog = ref(false);
    const currentChatContext = ref(null);
    const chatFileAssociations = ref({});

    // Settings
    const settings = ref({
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
    });

    // Computed properties
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
        const response = await apiService.get(`/api/chat_knowledge/context/${chatId}`);
        if (response.success) {
          currentChatContext.value = response.context;
        }
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

    const showKnowledgeManagement = () => {
      showKnowledgeDialog.value = true;
    };

    const onKnowledgeDecisionsApplied = (decisions) => {
      console.log('Knowledge decisions applied:', decisions);
      // Refresh chat context
      if (currentChatId.value) {
        loadChatContext(currentChatId.value);
      }
    };

    const onChatCompiled = (compiledData) => {
      console.log('Chat compiled to knowledge base:', compiledData);
      // Show success message or notification
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

            const uploadResponse = await fetch('http://localhost:8001/api/files/upload', {
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
        const workflowResponse = await fetch('http://localhost:8001/api/workflow/execute', {
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
            console.log('Workflow API response status:', workflowResponse.status);
            console.log('Workflow API response length:', responseText.length);
            console.log('Workflow API response preview:', responseText.substring(0, 100) + '...');

            workflowResult = JSON.parse(responseText);

            // Edge browser compatibility: validate parsed result structure
            if (!workflowResult || typeof workflowResult !== 'object') {
              throw new Error('Parsed response is not a valid object');
            }

          } catch (parseError) {
            console.error('Edge browser compatibility error:', parseError);
            console.error('Response status:', workflowResponse.status);
            console.error('Response headers:', Object.fromEntries(workflowResponse.headers.entries()));

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
            const messageType = determineMessageType(responseText);

            messages.value.push({
              sender: 'bot',
              text: responseText,
              timestamp: new Date().toLocaleTimeString(),
              type: messageType
            });
          }
        } else {
          messages.value.push({
            sender: 'bot',
            text: 'Error: Could not get response from server',
            timestamp: new Date().toLocaleTimeString(),
            type: 'error'
          });
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

        console.log('Created new chat:', newChatId);
      } catch (error) {
        console.error('Error creating new chat:', error);
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
        console.log(`Chat ${targetChatId} deleted successfully from backend`);

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
        console.log('Refreshing chat list...');
        const data = await apiClient.getChatList();
        chatList.value = data.chats || [];
        console.log('Loaded', chatList.value.length, 'chats');
      } catch (error) {
        console.error('Error loading chat list:', error);
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
          console.log('Created fallback chat due to loading error');
        }
      }
    };

    const loadChatMessages = async (chatId) => {
      try {
        console.log('Loading messages for chat:', chatId);
        const data = await apiClient.getChatMessages(chatId);
        // Backend returns 'history' field, not 'messages'
        messages.value = data.history || [];
        console.log('Loaded', messages.value.length, 'messages');

        // Scroll to bottom after loading
        await nextTick();
        if (chatMessages.value) {
          chatMessages.value.scrollTop = chatMessages.value.scrollHeight;
        }
      } catch (error) {
        console.error('Error loading chat messages:', error);
        messages.value = [];
      }
    };

    const saveChatMessages = async (chatId) => {
      try {
        console.log('Saving', messages.value.length, 'messages for chat:', chatId);
        await apiClient.saveChatMessages(chatId, messages.value);
        console.log('Messages saved successfully');
      } catch (error) {
        console.error('Error saving chat messages:', error);
      }
    };

    const reloadSystem = async () => {
      systemReloading.value = true;
      try {
        console.log('Reloading system...');
        const response = await apiClient.post('/api/system/reload');

        if (response.data.status === 'success') {
          console.log('System reloaded successfully:', response.data);
          reloadNeeded.value = false; // Clear reload notification

          // Show success message to user (you might want to add a toast notification here)
          const reloadResults = response.data.reload_results || [];
          const reloadedModules = response.data.reloaded_modules || [];

          console.log('Reload results:', reloadResults);
          console.log('Reloaded modules:', reloadedModules);

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
      console.log('Opening terminal in new tab...');
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
      const wsUrl = `ws://localhost:8001/ws`;
      websocket.value = new WebSocket(wsUrl);

      websocket.value.onopen = () => {
        console.log('WebSocket connected for workflow updates');
      };

      websocket.value.onmessage = (event) => {
        try {
          const eventData = JSON.parse(event.data);
          handleWebSocketEvent(eventData);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      websocket.value.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      websocket.value.onclose = () => {
        console.log('WebSocket disconnected, attempting to reconnect...');
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

      // Connect WebSocket for real-time updates
      connectWebSocket();

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
      onChatCompiled
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
