/**
 * Shared Chat History Service
 *
 * Centralizes all chat history management logic to eliminate duplication
 * between ChatInterface.vue and HistoryView.vue components.
 */

import apiClient from '@/utils/ApiClient';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for ChatHistoryService
const logger = createLogger('ChatHistoryService');

export class ChatHistoryService {
  constructor() {
    this.chatList = [];
  }

  /**
   * Load chat list from backend with fallback to localStorage
   */
  async loadChatList() {
    try {
      // Try backend first
      const data = await apiClient.getChatList();
      this.chatList = data.chats || [];
    } catch (error) {
      logger.error('Error loading chat list from backend:', error);
      // Fallback to localStorage
      this.loadChatListFromLocalStorage();
    }

    // Load custom chat names if available
    await this.loadCustomChatNames();
    return this.chatList;
  }

  /**
   * Load chat list from localStorage as fallback
   */
  loadChatListFromLocalStorage() {
    const localChats = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith('chat_') && key.endsWith('_messages')) {
        const chatId = key.split('_')[1];
        localChats.push({ chatId, name: '' });
      }
    }
    this.chatList = localChats;
  }

  /**
   * Load custom chat names from localStorage
   */
  async loadCustomChatNames() {
    const savedChatList = localStorage.getItem('chat_list');
    if (savedChatList) {
      try {
        const customList = JSON.parse(savedChatList);
        this.chatList.forEach(chat => {
          const customChat = customList.find(c => c.chatId === chat.chatId);
          if (customChat && customChat.name) {
            chat.name = customChat.name;
          }
        });
      } catch (e) {
        logger.error('Error loading custom chat names:', e);
      }
    }
  }

  /**
   * Get chat preview text from the first user message
   */
  getChatPreview(chatId) {
    const persistedMessages = localStorage.getItem(`chat_${chatId}_messages`);
    if (persistedMessages) {
      try {
        const chatMessages = JSON.parse(persistedMessages);
        if (chatMessages.length > 0) {
          const userMessage = chatMessages.find(msg => msg.sender === 'user');
          if (userMessage && userMessage.text) {
            return userMessage.text.substring(0, 30) + (userMessage.text.length > 30 ? '...' : '');
          }
        }
      } catch (e) {
        logger.error('Error parsing chat messages for preview:', e);
      }
    }
    return '';
  }

  /**
   * Load messages for a specific chat
   */
  async loadChatMessages(chatId) {
    try {
      const data = await apiClient.getChatMessages(chatId);

      // Normalize message format - backend uses 'messageType', frontend expects 'type'
      const normalizedMessages = (data.history || []).map(msg => ({
        ...msg,
        type: msg.messageType || msg.type || 'response', // Ensure type field exists
        messageType: undefined // Remove to avoid confusion
      }));

      return normalizedMessages;
    } catch (error) {
      logger.error('Error loading chat messages from backend:', error);
      // Fallback to localStorage
      const persistedMessages = localStorage.getItem(`chat_${chatId}_messages`);
      if (persistedMessages) {
        const localMessages = JSON.parse(persistedMessages);

        // Also normalize localStorage messages in case they have messageType
        return localMessages.map(msg => ({
          ...msg,
          type: msg.messageType || msg.type || 'response',
          messageType: undefined
        }));
      }
      return [];
    }
  }

  /**
   * Save messages to both localStorage and backend
   */
  async saveChatMessages(chatId, messages) {
    if (!chatId) {
      logger.warn('No chat ID provided to save messages');
      return;
    }

    // Save to localStorage
    localStorage.setItem(`chat_${chatId}_messages`, JSON.stringify(messages));

    // Save to backend
    try {
      await apiClient.saveChatMessages(chatId, messages);
    } catch (error) {
      logger.error('Error saving chat messages to backend:', error);
    }
  }

  /**
   * Create a new chat
   */
  async createNewChat() {
    try {
      const newChatData = await apiClient.createNewChat();
      const newChatId = newChatData.chat_id;

      // Add to chat list
      this.chatList.push({ chatId: newChatId, name: '' });

      return newChatId;
    } catch (error) {
      logger.error('Failed to create new chat:', error);
      throw error;
    }
  }

  /**
   * Delete a specific chat
   */
  async deleteChat(chatId) {
    if (!chatId) {
      throw new Error('No chat ID provided for deletion');
    }

    try {
      await apiClient.deleteChat(chatId);

      // Remove from localStorage
      localStorage.removeItem(`chat_${chatId}_messages`);

      // Remove from chat list
      this.chatList = this.chatList.filter(chat => chat.chatId !== chatId);

      return true;
    } catch (error) {
      logger.error('Error deleting chat:', error);
      throw error;
    }
  }

  /**
   * Update chat name
   */
  editChatName(chatId, newName) {
    const chatIndex = this.chatList.findIndex(chat => chat.chatId === chatId);
    if (chatIndex !== -1) {
      this.chatList[chatIndex].name = newName;

      // Save updated chat list to localStorage
      localStorage.setItem('chat_list', JSON.stringify(this.chatList));
      return true;
    }
    return false;
  }

  /**
   * Get history entries with proper formatting for HistoryView
   */
  async getHistoryEntries() {
    await this.loadChatList();

    const historyEntries = await Promise.all(
      this.chatList.map(async (chat) => {
        try {
          const messages = await this.loadChatMessages(chat.chatId);
          const userMessage = messages.find(msg => msg.sender === 'user');
          const preview = userMessage
            ? userMessage.text.substring(0, 30) + (userMessage.text.length > 30 ? '...' : '')
            : 'No subject';

          return {
            id: chat.chatId,
            date: messages.length > 0 ? messages[0].timestamp : 'Unknown date',
            preview: preview,
            name: chat.name || ''
          };
        } catch (error) {
          logger.error(`Error loading messages for chat ${chat.chatId}:`, error);
          return {
            id: chat.chatId,
            date: 'Unknown date',
            preview: 'Error loading chat',
            name: chat.name || ''
          };
        }
      })
    );

    return historyEntries;
  }

  /**
   * Reset chat (clear messages)
   */
  async resetChat(chatId) {
    try {
      await apiClient.resetChat(chatId);
      return true;
    } catch (error) {
      logger.error('Error resetting chat:', error);
      throw error;
    }
  }
}

// Export singleton instance
export const chatHistoryService = new ChatHistoryService();
export default chatHistoryService;
