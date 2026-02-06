/**
 * Shared Chat History Composable
 *
 * Provides reactive chat history management with proper API endpoints
 */

import { ref, computed, watch, onMounted } from 'vue';
import apiClient from '@/utils/ApiClient.js';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for useChatHistory
const logger = createLogger('useChatHistory');

export function useChatHistory() {
  // Reactive state
  const chatList = ref([]);
  const currentChatId = ref(null);
  const messages = ref([]);
  const isLoading = ref(false);
  const error = ref(null);

  // Get current chat from URL hash
  const getCurrentChatFromUrl = () => {
    const hash = window.location.hash.substring(1);
    const params = new URLSearchParams(hash);
    return params.get('chatId');
  };

  // Set current chat ID and update URL
  const setCurrentChat = (chatId) => {
    currentChatId.value = chatId;
    if (chatId) {
      window.location.hash = `chatId=${chatId}`;
    } else {
      window.location.hash = '';
    }
  };

  // Computed properties
  const currentChat = computed(() => {
    return chatList.value.find(chat => chat.chatId === currentChatId.value) || null;
  });

  const chatCount = computed(() => chatList.value.length);

  const hasChats = computed(() => chatList.value.length > 0);

  const sortedChatList = computed(() => {
    return [...chatList.value].sort((a, b) => new Date(b.date) - new Date(a.date));
  });

  // Load chat list from backend
  const loadChatList = async () => {
    isLoading.value = true;
    error.value = null;

    try {
      const data = await apiClient.getChatList();

      // Handle different response structures
      const chats = data.chats || data.data || data || [];

      chatList.value = chats.map(chat => ({
        chatId: chat.session_id || chat.chatId || chat.id,
        id: chat.session_id || chat.chatId || chat.id, // For compatibility
        name: chat.title || chat.name || '',
        preview: chat.preview || 'No subject',
        date: chat.created_at || chat.date || new Date().toISOString()
      }));

    } catch (error) {
      logger.error('Failed to load chat list from backend:', error);
      error.value = error.message;

      // Fallback to localStorage
      await loadChatListFromLocalStorage();
    } finally {
      isLoading.value = false;
    }
  };

  // Fallback: Load chat list from localStorage
  const loadChatListFromLocalStorage = () => {

    const localChats = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith('chat_') && key.endsWith('_messages')) {
        const chatId = key.split('_')[1];
        if (chatId) {
          localChats.push({
            chatId,
            id: chatId,
            name: '',
            preview: getChatPreviewFromStorage(chatId),
            date: new Date().toISOString()
          });
        }
      }
    }

    chatList.value = localChats;
  };

  // Get chat preview from localStorage
  const getChatPreviewFromStorage = (chatId) => {
    try {
      const messagesKey = `chat_${chatId}_messages`;
      const persistedMessages = localStorage.getItem(messagesKey);

      if (persistedMessages) {
        const chatMessages = JSON.parse(persistedMessages);
        if (chatMessages.length > 0) {
          const userMessage = chatMessages.find(msg => msg.sender === 'user');
          if (userMessage && userMessage.text) {
            return userMessage.text.substring(0, 30) + (userMessage.text.length > 30 ? '...' : '');
          }
        }
      }
    } catch (e) {
      logger.error(`Error getting chat preview for ${chatId}:`, e);
    }
    return 'No subject';
  };

  // Load messages for a specific chat
  const loadChatMessages = async (chatId) => {
    if (!chatId) return [];

    isLoading.value = true;
    error.value = null;

    try {
      const data = await apiClient.getChatMessages(chatId);

      // Handle different response structures
      const chatMessages = data.messages || data.data || data || [];

      // Normalize message format
      const normalizedMessages = chatMessages.map(msg => ({
        ...msg,
        type: msg.messageType || msg.type || 'response',
        messageType: undefined // Remove to avoid confusion
      }));

      messages.value = normalizedMessages;

      return normalizedMessages;
    } catch (error) {
      logger.error(`Failed to load messages for chat ${chatId}:`, error);
      error.value = error.message;

      // Fallback to localStorage
      const localMessages = await loadMessagesFromLocalStorage(chatId);
      messages.value = localMessages;
      return localMessages;
    } finally {
      isLoading.value = false;
    }
  };

  // Fallback: Load messages from localStorage
  const loadMessagesFromLocalStorage = async (chatId) => {
    try {
      const messagesKey = `chat_${chatId}_messages`;
      const persistedMessages = localStorage.getItem(messagesKey);

      if (persistedMessages) {
        const localMessages = JSON.parse(persistedMessages);

        // Normalize localStorage messages
        return localMessages.map(msg => ({
          ...msg,
          type: msg.messageType || msg.type || 'response',
          messageType: undefined
        }));
      }
    } catch (e) {
      logger.error(`Error loading messages from localStorage for chat ${chatId}:`, e);
    }

    return [];
  };

  // Function to create a new chat - FIXED TO USE CORRECT ENDPOINT
  const createNewChat = async () => {
    try {
      // Use the correct endpoint: POST /api/chat/sessions (not /api/chat/chats/new)
      const newChatData = await apiClient.createNewChat();
      const newChatId = newChatData.session_id || newChatData.id || newChatData.chat_id;

      if (!newChatId) {
        throw new Error('No chat ID returned from server');
      }

      // Add to chat list
      const newChat = {
        chatId: newChatId,
        id: newChatId,  // For HistoryView compatibility
        name: newChatData.title || '',
        preview: 'New chat',
        date: newChatData.created_at || new Date().toISOString()
      };
      chatList.value.push(newChat);

      // Set as current chat
      currentChatId.value = newChatId;
      window.location.hash = `chatId=${newChatId}`;

      return newChatId;
    } catch (error) {
      logger.error('Failed to create new chat:', error);
      error.value = error.message;
      throw error;
    }
  };

  // Function to delete a chat
  const deleteChat = async (chatId) => {
    if (!chatId) {
      throw new Error('No chat ID provided for deletion');
    }

    try {
      await apiClient.deleteChat(chatId);

      // Remove from localStorage
      localStorage.removeItem(`chat_${chatId}_messages`);

      // Remove from chat list
      chatList.value = chatList.value.filter(chat => chat.chatId !== chatId);

      // Clear current chat if it was deleted
      if (currentChatId.value === chatId) {
        currentChatId.value = null;
        messages.value = [];
        window.location.hash = '';
      }

      return true;
    } catch (error) {
      logger.error('Error deleting chat:', error);
      error.value = error.message;
      throw error;
    }
  };

  // Function to save chat messages (DEPRECATED - messages should be sent individually)
  const saveChatMessages = async (chatId, messageList) => {
    logger.warn('saveChatMessages is deprecated. Messages should be sent individually via sendChatMessage()');

    if (!chatId) {
      logger.warn('No chat ID provided to save messages');
      return;
    }

    // Save to localStorage for backward compatibility
    localStorage.setItem(`chat_${chatId}_messages`, JSON.stringify(messageList));

    // Update messages in state
    if (currentChatId.value === chatId) {
      messages.value = messageList;
    }

  };

  // Function to send a message
  const sendMessage = async (messageContent, options = {}) => {
    if (!messageContent || !messageContent.trim()) {
      throw new Error('Message content cannot be empty');
    }

    try {
      const chatId = options.session_id || currentChatId.value;

      if (!chatId) {
        throw new Error('No chat session ID available');
      }

      const result = await apiClient.sendChatMessage(messageContent, {
        session_id: chatId,
        ...options
      });

      // If successful, reload messages for this chat
      if (result.type === 'json' && result.data.success) {
        await loadChatMessages(chatId);
      }

      return result;
    } catch (error) {
      logger.error('Failed to send message:', error);
      error.value = error.message;
      throw error;
    }
  };

  // Function to update chat name
  const updateChatName = async (chatId, newName) => {
    try {
      // Update via API if available
      try {
        await apiClient.updateChatSession(chatId, { title: newName });
      } catch (apiError) {
        logger.warn('Failed to update chat name via API, updating locally only:', apiError);
      }

      // Update in local chat list
      const chatIndex = chatList.value.findIndex(chat => chat.chatId === chatId);
      if (chatIndex !== -1) {
        chatList.value[chatIndex].name = newName;
      }

      // Save to localStorage for backward compatibility
      const savedChatList = chatList.value.map(chat => ({
        chatId: chat.chatId,
        name: chat.name
      }));
      localStorage.setItem('chat_list', JSON.stringify(savedChatList));

      return true;
    } catch (error) {
      logger.error('Error updating chat name:', error);
      error.value = error.message;
      return false;
    }
  };

  // Function to clear current error
  const clearError = () => {
    error.value = null;
  };

  // Watch for URL changes
  watch(() => window.location.hash, () => {
    const chatId = getCurrentChatFromUrl();
    if (chatId && chatId !== currentChatId.value) {
      currentChatId.value = chatId;
      loadChatMessages(chatId);
    }
  });

  // Watch for current chat changes
  watch(currentChatId, async (newChatId, oldChatId) => {
    if (newChatId && newChatId !== oldChatId) {
      await loadChatMessages(newChatId);
    }
  });

  // Initialize on mount
  onMounted(async () => {
    // Load chat list first
    await loadChatList();

    // Check URL for current chat
    const urlChatId = getCurrentChatFromUrl();
    if (urlChatId) {
      currentChatId.value = urlChatId;
      await loadChatMessages(urlChatId);
    }
  });

  return {
    // Reactive state
    chatList,
    currentChatId,
    messages,
    isLoading,
    error,

    // Computed properties
    currentChat,
    chatCount,
    hasChats,
    sortedChatList,

    // Functions
    loadChatList,
    loadChatMessages,
    createNewChat,
    deleteChat,
    saveChatMessages,
    sendMessage,
    updateChatName,
    setCurrentChat,
    clearError,
    getCurrentChatFromUrl
  };
}
