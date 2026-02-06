// ChatManager.js - Centralized chat management utility
import appConfig from '@/config/AppConfig.js';
import apiClient from '@/utils/ApiClient.js';
import { NetworkConstants } from '@/constants/network';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for ChatManager
const logger = createLogger('ChatManager');

class ChatManager {
  constructor() {
    this.apiClient = apiClient;
    this.currentChatId = null;
    this.apiEndpoint = ''; // Will be loaded async
    this.settings = {
      backend: {
        api_endpoint: '' // Will be loaded async
      }
    };
    this.initializeEndpoint();
    this.loadSettings();
  }

  // Initialize API endpoint async
  async initializeEndpoint() {
    try {
      this.apiEndpoint = await appConfig.getApiUrl('');
      this.settings.backend.api_endpoint = this.apiEndpoint;
    } catch (error) {
      logger.warn('Using fallback API endpoint');
      this.apiEndpoint = `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`;
      this.settings.backend.api_endpoint = this.apiEndpoint;
    }
  }

  // Load settings from localStorage
  loadSettings() {
    try {
      const savedSettings = localStorage.getItem('chat_settings');
      if (savedSettings) {
        this.settings = JSON.parse(savedSettings);
        this.apiEndpoint = this.settings.backend?.api_endpoint || this.apiEndpoint;
      }
    } catch (error) {
      logger.error('Error loading settings:', error);
    }
  }

  // Save settings to localStorage
  saveSettings() {
    try {
      localStorage.setItem('chat_settings', JSON.stringify(this.settings));
    } catch (error) {
      logger.error('Error saving settings:', error);
    }
  }

  // Update API endpoint
  updateApiEndpoint(endpoint) {
    this.apiClient.setBaseUrl(endpoint);
    this.settings.backend.api_endpoint = endpoint;
    this.saveSettings();
  }

  // Create a new chat
  async createNewChat() {
    try {
      const data = await this.apiClient.createNewChat();
      this.currentChatId = data.chatId;
      return data;
    } catch (error) {
      logger.error('Error creating new chat:', error);
      throw error;
    }
  }

  // Get list of all chats
  async getChatList() {
    try {
      const data = await this.apiClient.getChatList();
      const chats = data.sessions || data || [];
      // Filter out chats with invalid IDs
      return chats.filter(chat => chat.chatId && chat.chatId !== 'undefined' && chat.chatId !== 'null');
    } catch (error) {
      logger.error('Error getting chat list:', error);
      return this.getFallbackChatList();
    }
  }

  // Fallback to localStorage for chat list
  getFallbackChatList() {
    const chats = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith('chat_') && key.endsWith('_messages')) {
        const chatId = key.slice(5, -9); // Remove 'chat_' prefix and '_messages' suffix
        // Only add chats with valid IDs
        if (chatId && chatId !== 'undefined' && chatId !== 'null') {
          chats.push({ chatId, name: '' });
        }
      }
    }
    return chats;
  }

  // Load messages for a specific chat
  async loadChatMessages(chatId) {
    try {
      // Try backend first using ApiClient
      const messages = await this.apiClient.getChatMessages(chatId);
      return messages;
    } catch (error) {
      logger.warn(`Backend failed for chat ${chatId}, falling back to localStorage`);
      logger.error(`Error loading messages for chat ${chatId}:`, error);
      return this.loadMessagesFromLocalStorage(chatId);
    }
  }

  // Load messages from localStorage
  loadMessagesFromLocalStorage(chatId) {
    try {
      const key = `chat_${chatId}_messages`;
      const stored = localStorage.getItem(key);
      if (stored) {
        const messages = JSON.parse(stored);
        return messages;
      }
    } catch (error) {
      logger.error(`Error loading messages from localStorage for chat ${chatId}:`, error);
    }
    return [];
  }

  // Save messages for a chat
  async saveChatMessages(chatId, messages) {
    // Always save to localStorage first (immediate backup)
    this.saveMessagesToLocalStorage(chatId, messages);

    // Then try to save to backend using ApiClient
    try {
      await this.apiClient.saveChatMessages(chatId, messages);
      return { status: 'success', location: 'backend' };
    } catch (error) {
      logger.error(`Error saving to backend for chat ${chatId}:`, error);
      return { status: 'success', location: 'localStorage' };
    }
  }

  // Save messages to localStorage
  saveMessagesToLocalStorage(chatId, messages) {
    try {
      const key = `chat_${chatId}_messages`;
      localStorage.setItem(key, JSON.stringify(messages));
    } catch (error) {
      logger.error(`Error saving to localStorage for chat ${chatId}:`, error);
    }
  }

  // Delete a chat
  async deleteChat(chatId) {
    // Validate chat ID first
    if (!chatId || chatId === 'undefined' || chatId === 'null' || chatId === null) {
      logger.error('Cannot delete chat: Invalid chat ID:', chatId);
      throw new Error(`Invalid chat ID for deletion: ${chatId}`);
    }


    try {
      // Try to delete from backend first using ApiClient
      await this.apiClient.deleteChat(chatId);
    } catch (error) {
      logger.error(`Error deleting chat ${chatId} from backend:`, error);
    }

    // Always clean up localStorage
    this.deleteFromLocalStorage(chatId);

    // If this was the current chat, clear it
    if (this.currentChatId === chatId) {
      this.currentChatId = null;
    }

    return { status: 'success' };
  }

  // Delete from localStorage
  deleteFromLocalStorage(chatId) {
    try {
      const key = `chat_${chatId}_messages`;
      localStorage.removeItem(key);
    } catch (error) {
      logger.error(`Error deleting chat ${chatId} from localStorage:`, error);
    }
  }

  // Reset a chat
  async resetChat(chatId) {
    try {
      await this.apiClient.resetChat();

      // Also reset in localStorage
      const initialMessage = [{
        sender: 'bot',
        text: 'Hello! How can I assist you today?',
        timestamp: new Date().toLocaleTimeString(),
        type: 'response'
      }];
      this.saveMessagesToLocalStorage(chatId, initialMessage);

      return { status: 'success' };
    } catch (error) {
      logger.error(`Error resetting chat ${chatId}:`, error);
      throw error;
    }
  }

  // Send a message to the chat API
  async sendMessage(message, options = {}) {
    try {
      const chatId = options.chatId || this.currentChatId || 'default';
      const requestBody = {
        content: message.trim(),
        role: "user",
        session_id: chatId,
        ...options
      };
      const response = await fetch(`${this.apiEndpoint}/api/chat/message`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      });

      if (response.ok) {
        const contentType = response.headers.get('content-type');

        if (contentType && contentType.includes('text/event-stream')) {
          // Handle streaming response
          return {
            type: 'streaming',
            response: response
          };
        } else {
          // Handle regular JSON response
          const data = await response.json();
          return {
            type: 'json',
            data: data
          };
        }
      } else {
        throw new Error(`Chat API failed: ${response.status} - ${response.statusText}`);
      }
    } catch (error) {
      logger.error('Error sending message:', error);
      throw error;
    }
  }

  // Get a preview of chat messages for display
  getChatPreview(chatId, messages = null) {
    if (!messages) {
      messages = this.loadMessagesFromLocalStorage(chatId);
    }

    if (messages && messages.length > 0) {
      // Find the first user message
      const userMessage = messages.find(msg => msg.sender === 'user');
      if (userMessage && userMessage.text) {
        return userMessage.text.substring(0, 50) + (userMessage.text.length > 50 ? '...' : '');
      }

      // If no user message, use the first message
      const firstMessage = messages[0];
      if (firstMessage && firstMessage.text) {
        return firstMessage.text.substring(0, 50) + (firstMessage.text.length > 50 ? '...' : '');
      }
    }

    return 'Empty chat';
  }

  // Check backend connection
  async checkBackendConnection() {
    try {
      const response = await fetch(`${this.apiEndpoint}/api/system/health`, {
        method: 'GET',
        timeout: 5000
      });

      return {
        connected: response.ok,
        status: response.status,
        statusText: response.statusText
      };
    } catch (error) {
      return {
        connected: false,
        error: error.message
      };
    }
  }

  // Cleanup old messages and files
  async cleanupMessages() {
    try {
      const response = await fetch(`${this.apiEndpoint}/api/chats/cleanup`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const result = await response.json();
        return result;
      } else {
        throw new Error(`Cleanup failed: ${response.statusText}`);
      }
    } catch (error) {
      logger.error('Error during cleanup:', error);
      throw error;
    }
  }

  // Get current chat ID
  getCurrentChatId() {
    return this.currentChatId;
  }

  // Set current chat ID
  setCurrentChatId(chatId) {
    this.currentChatId = chatId;
  }

  // Utility method to format timestamps
  formatTimestamp(timestamp) {
    if (!timestamp) return new Date().toLocaleTimeString();

    if (typeof timestamp === 'string') {
      // If it's already formatted, return as is
      if (timestamp.includes(':')) return timestamp;

      // If it's an ISO string, format it
      try {
        return new Date(timestamp).toLocaleTimeString();
      } catch (_error) {
        return timestamp;
      }
    }

    if (timestamp instanceof Date) {
      return timestamp.toLocaleTimeString();
    }

    return new Date().toLocaleTimeString();
  }

  // Validate message format
  validateMessage(message) {
    if (!message || typeof message !== 'object') {
      return false;
    }

    const requiredFields = ['sender', 'text', 'timestamp', 'type'];
    return requiredFields.every(field => field in message);
  }

  // Clean and validate messages array
  cleanMessages(messages) {
    if (!Array.isArray(messages)) {
      return [];
    }

    return messages.filter(msg => this.validateMessage(msg)).map(msg => ({
      sender: msg.sender || 'unknown',
      text: msg.text || '',
      timestamp: this.formatTimestamp(msg.timestamp),
      type: msg.type || 'message',
      ...(msg.final !== undefined && { final: msg.final })
    }));
  }
}

// Export as both default and named export
export default ChatManager;
export { ChatManager };
