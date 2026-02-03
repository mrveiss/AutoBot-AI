/**
 * Shared composable for chat history management
 * Eliminates duplication between ChatInterface.vue and HistoryView.vue
 */
import { ref } from 'vue';
import apiClient from '@/utils/ApiClient.js';

export function useChatHistory() {
  const chatList = ref([]);
  const currentChatId = ref(null);

  // Function to build chat list from local storage
  const loadChatListFromLocalStorage = () => {
    const localChats = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith('chat_') && key.endsWith('_messages')) {
        const chatId = key.split('_')[1];
        const messagesStr = localStorage.getItem(key);
        if (messagesStr) {
          try {
            const messages = JSON.parse(messagesStr);
            // Look for the first user message to use as a preview
            const userMessage = messages.find(msg => msg.sender === 'user');
            const subject = userMessage ?
              userMessage.text.substring(0, 30) + (userMessage.text.length > 30 ? '...' : '') :
              'No subject';

            localChats.push({
              chatId,
              id: chatId, // For HistoryView compatibility
              date: messages.length > 0 ? messages[0].timestamp : 'Unknown date',
              preview: subject,
              name: ''
            });
          } catch (e) {
            console.error(`Error parsing messages for chat ${chatId}:`, e);
          }
        }
      }
    }
    chatList.value = localChats;
    console.log(`Chat history loaded from local storage: ${localChats.length} chats`);
    return localChats;
  };

  // Function to fetch chat history from backend with fallback to local storage
  const loadChatList = async () => {
    try {
      const response = await apiClient.get('/api/chats');
      const chats = response.chats || [];

      const processedChats = await Promise.all(chats.map(async (chat) => {
        try {
          const messagesResponse = await apiClient.getChatMessages(chat.chatId);
          const messages = messagesResponse.history || [];
          const userMessage = messages.find(msg => msg.sender === 'user');
          const subject = userMessage ?
            userMessage.text.substring(0, 30) + (userMessage.text.length > 30 ? '...' : '') :
            'No subject';

          return {
            chatId: chat.chatId,
            id: chat.chatId, // For HistoryView compatibility
            date: messages.length > 0 ? messages[0].timestamp : 'Unknown date',
            preview: subject,
            name: chat.name || ''
          };
        } catch (error) {
          console.error(`Error loading messages for chat ${chat.chatId}:`, error);
          return {
            chatId: chat.chatId,
            id: chat.chatId,
            date: 'Unknown date',
            preview: 'Error loading chat',
            name: chat.name || ''
          };
        }
      }));

      chatList.value = processedChats;
      console.log(`Chat history loaded from backend: ${processedChats.length} chats`);
    } catch (error) {
      console.error('Error loading chat list from backend:', error);
      // Fallback to local storage
      loadChatListFromLocalStorage();
    }
  };

  // Function to get a preview of the chat for display
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
        console.error('Error parsing chat messages for preview:', e);
      }
    }
    return '';
  };

  // Function to delete a specific chat
  const deleteChat = async (chatId) => {
    if (!chatId) {
      console.warn('No chat ID provided for deletion');
      return { success: false, message: 'No chat ID provided' };
    }

    try {
      await apiClient.deleteChat(chatId);

      // Remove from local storage
      localStorage.removeItem(`chat_${chatId}_messages`);

      // Remove from chat list
      chatList.value = chatList.value.filter(chat => chat.chatId !== chatId && chat.id !== chatId);

      // If the deleted chat was active, clear current chat ID
      if (chatId === currentChatId.value) {
        currentChatId.value = null;
        window.location.hash = '';
      }

      console.log(`Chat ${chatId} deleted successfully`);
      return { success: true, message: 'Chat deleted successfully' };
    } catch (error) {
      console.error('Error deleting chat:', error);
      return { success: false, message: `Error deleting chat: ${error.message}` };
    }
  };

  // Function to create a new chat
  const createNewChat = async () => {
    try {
      const newChatData = await apiClient.createNewChat();
      const newChatId = newChatData.chat_id;

      // Add to chat list
      const newChat = {
        chatId: newChatId,
        id: newChatId,  // For HistoryView compatibility
        name: '',
        preview: '',
        date: new Date().toLocaleTimeString()
      };
      chatList.value.push(newChat);

      // Set as current chat
      currentChatId.value = newChatId;
      window.location.hash = `chatId=${newChatId}`;

      console.log('New Chat created:', newChatId);
      return { success: true, chatId: newChatId };
    } catch (error) {
      console.error('Failed to create new chat:', error);
      return { success: false, error: error.message };
    }
  };

  // Function to switch to a different chat
  const switchToChat = (chatId) => {
    if (chatId === currentChatId.value) return;

    window.location.hash = `chatId=${chatId}`;
    currentChatId.value = chatId;
    console.log('Switched to chat:', chatId);
  };

  // Function to edit chat name
  const editChatName = (chatId, newName) => {
    const chatIndex = chatList.value.findIndex(chat =>
      chat.chatId === chatId || chat.id === chatId
    );
    if (chatIndex !== -1) {
      chatList.value[chatIndex].name = newName;

      // Save updated chat list to local storage
      const customChatList = chatList.value.map(chat => ({
        chatId: chat.chatId || chat.id,
        name: chat.name
      }));
      localStorage.setItem('chat_list', JSON.stringify(customChatList));

      console.log(`Updated name for chat ${chatId} to "${newName}"`);
      return true;
    }
    return false;
  };

  // Function to load custom chat names from local storage
  const loadCustomChatNames = () => {
    const savedChatList = localStorage.getItem('chat_list');
    if (savedChatList) {
      try {
        const customList = JSON.parse(savedChatList);
        // Update names in the chat list based on custom names
        chatList.value.forEach(chat => {
          const customChat = customList.find(c => c.chatId === (chat.chatId || chat.id));
          if (customChat && customChat.name) {
            chat.name = customChat.name;
          }
        });
      } catch (e) {
        console.error('Error loading custom chat list names:', e);
      }
    }
  };

  return {
    chatList,
    currentChatId,
    loadChatListFromLocalStorage,
    loadChatList,
    getChatPreview,
    deleteChat,
    createNewChat,
    switchToChat,
    editChatName,
    loadCustomChatNames
  };
}
