<template>
  <div class="flex h-full bg-white">
    <div class="flex-1 flex flex-col">
      <!-- Sidebar -->
      <div class="w-80 bg-blueGray-100 border-r border-blueGray-200 flex flex-col transition-all duration-300" :class="{ 'w-12': sidebarCollapsed }">
        <button class="p-3 border-b border-blueGray-200 text-blueGray-600 hover:bg-blueGray-200 transition-colors" @click="sidebarCollapsed = !sidebarCollapsed">
          <i :class="sidebarCollapsed ? 'fas fa-chevron-right' : 'fas fa-chevron-left'"></i>
        </button>
        <div class="flex-1 overflow-y-auto p-4" v-if="!sidebarCollapsed">
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

      <!-- Chat Messages -->
      <div class="flex-1 flex flex-col">
        <div class="flex-1 overflow-y-auto p-6 space-y-4" ref="chatMessages" role="log">
          <div v-for="(message, index) in filteredMessages" :key="index" class="flex" :class="message.sender === 'user' ? 'justify-end' : 'justify-start'">
            <div class="max-w-3xl rounded-lg p-4 shadow-sm" :class="message.sender === 'user' ? 'bg-indigo-500 text-white' : 'bg-white border border-blueGray-200 text-blueGray-700'">
              <div class="message-content" v-html="formatMessage(message.text, message.type)"></div>
              <div class="text-xs mt-2 opacity-70">{{ message.timestamp }}</div>
            </div>
          </div>
        </div>

        <!-- Chat Input -->
        <div class="border-t border-blueGray-200 p-4">
          <div class="flex items-end space-x-4">
            <div class="flex-1">
              <textarea
                id="chat-input"
                v-model="inputMessage"
                placeholder="Type your message or goal for AutoBot..."
                @keyup.enter="sendMessage"
                rows="3"
                class="w-full px-4 py-3 border border-blueGray-300 rounded-lg resize-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              ></textarea>
            </div>
            <button
              @click="sendMessage"
              class="btn btn-primary px-6 py-3"
              :disabled="!inputMessage.trim()"
            >
              <i class="fas fa-paper-plane mr-2"></i>
              Send
            </button>
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
  </div>
</template>

<script>
import { ref, reactive, computed, onMounted, nextTick } from 'vue';
import TerminalSidebar from './TerminalSidebar.vue';

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
      if (type === 'thought') {
        return `<div class="thought-message">${text}</div>`;
      } else if (type === 'planning') {
        return `<div class="planning-message"><strong>Planning:</strong> ${text}</div>`;
      } else if (type === 'debug' || type === 'json') {
        return `<div class="debug-message"><strong>Debug:</strong> <pre>${text}</pre></div>`;
      } else if (type === 'utility') {
        return `<div class="utility-message"><strong>Utility:</strong> ${text}</div>`;
      } else if (type === 'tool_output') {
        return `<div class="tool-output-message"><strong>Tool Output:</strong> ${text}</div>`;
      }
      return text;
    };

    const sendMessage = async () => {
      if (!inputMessage.value.trim()) return;

      // Add user message
      messages.value.push({
        sender: 'user',
        text: inputMessage.value,
        timestamp: new Date().toLocaleTimeString(),
        type: 'message'
      });

      const userInput = inputMessage.value;
      inputMessage.value = '';

      try {
        // Send to backend
        const response = await fetch('http://localhost:8001/api/chat/send', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            message: userInput,
            chat_id: currentChatId.value
          }),
        });

        if (response.ok) {
          const result = await response.json();
          messages.value.push({
            sender: 'bot',
            text: result.response || 'No response received',
            timestamp: new Date().toLocaleTimeString(),
            type: 'response'
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

    const newChat = () => {
      const newChatId = `chat-${Date.now()}`;
      currentChatId.value = newChatId;
      messages.value = [];

      // Add to chat list if not exists
      if (!chatList.value.find(chat => chat.chatId === newChatId)) {
        chatList.value.unshift({
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

    const switchChat = (chatId) => {
      currentChatId.value = chatId;
      // Load messages for this chat (would typically come from backend)
      messages.value = [];
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

    const refreshChatList = () => {
      // Refresh chat list from backend
      console.log('Refreshing chat list...');
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
    onMounted(() => {
      newChat(); // Create initial chat

      // Load settings from localStorage
      const savedSettings = localStorage.getItem('chat-settings');
      if (savedSettings) {
        try {
          Object.assign(settings.value, JSON.parse(savedSettings));
        } catch (e) {
          console.error('Failed to load settings:', e);
        }
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
      openTerminalInNewTab
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
  @apply bg-blueGray-100 p-2 rounded text-xs overflow-x-auto font-mono;
}

.thought-message {
  @apply border-l-4 border-blueGray-500 bg-blueGray-50 p-3 rounded-r italic;
}

.planning-message {
  @apply border-l-4 border-indigo-500 bg-indigo-50 p-3 rounded-r font-medium;
}

.debug-message {
  @apply border-l-4 border-yellow-500 bg-yellow-50 p-3 rounded-r text-xs;
}

.utility-message {
  @apply border-l-4 border-emerald-500 bg-emerald-50 p-3 rounded-r text-sm;
}

.tool-output-message {
  @apply border-l-4 border-emerald-500 bg-emerald-50 p-3 rounded-r font-mono text-sm;
}
</style>
