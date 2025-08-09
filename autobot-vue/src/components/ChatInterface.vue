<template>
  <div class="flex h-full bg-white overflow-hidden">
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
            <button class="btn btn-success w-full" @click="startBackendServer" :disabled="backendStarting">
              <i class="fas fa-play mr-2"></i>
              {{ backendStarting ? 'Starting...' : 'Start Backend Server' }}
            </button>
          </div>
        </div>
    </div>

    <!-- Main Chat Container -->
    <div class="flex-1 flex h-full overflow-hidden">
      <!-- Chat Content Area -->
      <div class="flex-1 flex flex-col h-full">
          <!-- Chat Messages -->
          <div class="flex-1 overflow-y-auto p-6 space-y-4" ref="chatMessages" role="log" style="max-height: calc(100vh - 300px); min-height: 400px;">
            <div v-for="(message, index) in filteredMessages" :key="index" class="flex" :class="message.sender === 'user' ? 'justify-end' : 'justify-start'">
              <div class="max-w-3xl rounded-lg p-4 shadow-sm" :class="message.sender === 'user' ? 'bg-indigo-500 text-white' : 'bg-white border border-blueGray-200 text-blueGray-700'">
                <div class="message-content" v-html="formatMessage(message.text, message.type)"></div>
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

              <!-- File Attachment Buttons -->
              <div class="flex flex-col gap-2">
                <label class="btn btn-secondary p-2" title="Attach file">
                  <i class="fas fa-paperclip"></i>
                  <input type="file" @change="handleFileAttachment" multiple style="display: none;" />
                </label>
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
    </div>

    <!-- Terminal Sidebar -->
    <TerminalSidebar
      v-if="showTerminalSidebar"
      :collapsed="terminalSidebarCollapsed"
      @update:collapsed="terminalSidebarCollapsed = $event"
      @open-new-tab="openTerminalInNewTab"
    />
  </div>
</template>

<script>
import { ref, reactive, computed, onMounted, nextTick } from 'vue';
import TerminalSidebar from './TerminalSidebar.vue';
import apiClient from '../utils/ApiClient.js';

export default {
  name: 'ChatInterface',
  components: {
    TerminalSidebar
  },
  setup() {
    // Reactive state
    const sidebarCollapsed = ref(false);
    const terminalSidebarCollapsed = ref(true);
    const showTerminalSidebar = ref(false);
    const inputMessage = ref('');
    const messages = ref([]);
    const chatList = ref([]);
    const currentChatId = ref(null);
    const backendStarting = ref(false);
    const chatMessages = ref(null);
    const attachedFiles = ref([]);

    // Settings
    const settings = ref({
      message_display: {
        show_thoughts: true,
        show_json: false,
        show_utility: false,
        show_planning: true,
        show_debug: false
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

        // Send to backend
        const response = await fetch(`http://localhost:8001/api/chats/${currentChatId.value}/message`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(messageData),
        });

        if (response.ok) {
          const result = await response.json();

          // Process the response to determine message type and content
          const responseText = result.response || result.response_text || 'No response received';
          const messageType = determineMessageType(responseText);

          messages.value.push({
            sender: 'bot',
            text: responseText,
            timestamp: new Date().toLocaleTimeString(),
            type: messageType
          });
        } else {
          messages.value.push({
            sender: 'bot',
            text: 'Error: Could not get response from server',
            timestamp: new Date().toLocaleTimeString(),
            type: 'error'
          });
        }
      } catch (error) {
        messages.value.push({
          sender: 'bot',
          text: `Error: ${error.message}`,
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

    const deleteSpecificChat = (chatId = null) => {
      const targetChatId = chatId || currentChatId.value;
      if (!targetChatId) return;

      chatList.value = chatList.value.filter(chat => chat.chatId !== targetChatId);

      if (currentChatId.value === targetChatId) {
        messages.value = [];
        if (chatList.value.length > 0) {
          switchChat(chatList.value[0].chatId);
        } else {
          newChat();
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

    const startBackendServer = async () => {
      backendStarting.value = true;
      try {
        // Simulate backend start
        await new Promise(resolve => setTimeout(resolve, 2000));
        console.log('Backend server started');
      } catch (error) {
        console.error('Failed to start backend:', error);
      } finally {
        backendStarting.value = false;
      }
    };

    const openTerminalInNewTab = () => {
      // Open terminal in new tab
      console.log('Opening terminal in new tab...');
    };

    // Initialize
    onMounted(async () => {
      // Load settings from localStorage
      const savedSettings = localStorage.getItem('chat-settings');
      if (savedSettings) {
        try {
          Object.assign(settings.value, JSON.parse(savedSettings));
        } catch (e) {
          console.error('Failed to load settings:', e);
        }
      }

      // Load chat list first
      await refreshChatList();

      // Try to load the last used chat
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
    });

    return {
      sidebarCollapsed,
      terminalSidebarCollapsed,
      showTerminalSidebar,
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
      startBackendServer,
      openTerminalInNewTab,
      // File handling
      attachedFiles,
      handleFileAttachment,
      removeAttachment,
      getFileIcon
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
</style>
