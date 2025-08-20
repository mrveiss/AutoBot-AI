// ApiClient.js - Unified API client for all backend operations
// RumAgent is accessed via window.rum global

class ApiClient {
  constructor() {
    this.baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001';
    this.timeout = 30000; // 30 seconds default timeout
    this.settings = this.loadSettings();

    // Update baseUrl from settings if available
    if (this.settings?.backend?.api_endpoint) {
      this.baseUrl = this.settings.backend.api_endpoint;
    }
  }

  // Load settings from localStorage
  loadSettings() {
    try {
      const savedSettings = localStorage.getItem('chat_settings');
      return savedSettings ? JSON.parse(savedSettings) : {};
    } catch (error) {
      console.error('Error loading settings:', error);
      return {};
    }
  }


  // Generic request method with error handling and timeout
  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const method = options.method || 'GET';
    const startTime = performance.now();

    // Track API call start
    if (window.rum) {
      window.rum.trackUserInteraction('api_call_initiated', null, {
        method,
        endpoint,
        url
      });
    }

    const config = {
      timeout: this.timeout,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      ...options
    };

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.timeout);

      const response = await fetch(url, {
        ...config,
        signal: controller.signal
      });

      clearTimeout(timeoutId);
      const endTime = performance.now();

      if (!response.ok) {
        // Track failed response
        if (window.rum) {
          window.rum.trackApiCall(method, endpoint, startTime, endTime, response.status);
        }
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      // Track successful response
      if (window.rum) {
        window.rum.trackApiCall(method, endpoint, startTime, endTime, response.status);
      }
      return response;

    } catch (error) {
      const endTime = performance.now();

      if (error.name === 'AbortError') {
        const timeoutError = new Error(`Request timeout after ${this.timeout}ms`);
        if (window.rum) {
          window.rum.trackApiCall(method, endpoint, startTime, endTime, 'timeout', timeoutError);
          window.rum.reportCriticalIssue('api_timeout', {
            method,
            endpoint,
            url,
            duration: endTime - startTime,
            timeout: this.timeout
          });
        }
        throw timeoutError;
      }

      // Track other errors
      if (window.rum) {
        window.rum.trackApiCall(method, endpoint, startTime, endTime, 'error', error);
      }
      throw error;
    }
  }

  // GET request
  async get(endpoint, options = {}) {
    return this.request(endpoint, { method: 'GET', ...options });
  }

  // POST request
  async post(endpoint, data = null, options = {}) {
    const config = { method: 'POST', ...options };

    if (data) {
      if (data instanceof FormData) {
        // Don't set Content-Type for FormData, let browser handle it
        delete config.headers['Content-Type'];
        config.body = data;
      } else {
        config.body = JSON.stringify(data);
      }
    }

    return this.request(endpoint, config);
  }

  // PUT request
  async put(endpoint, data = null, options = {}) {
    const config = { method: 'PUT', ...options };
    if (data) {
      config.body = JSON.stringify(data);
    }
    return this.request(endpoint, config);
  }

  // DELETE request
  async delete(endpoint, options = {}) {
    return this.request(endpoint, { method: 'DELETE', ...options });
  }

  // Chat API methods
  async sendChatMessage(message, options = {}) {
    const response = await this.post('/api/chat', { message, ...options });

    // Check if it's a streaming response
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('text/event-stream')) {
      return {
        type: 'streaming',
        response: response
      };
    } else {
      const data = await response.json();
      return {
        type: 'json',
        data: data
      };
    }
  }

  async createNewChat() {
    const response = await this.post('/api/chats/new');
    return response.json();
  }

  async getChatList() {
    const response = await this.get('/api/chats');
    return response.json();
  }

  async getChatMessages(chatId) {
    const response = await this.get(`/api/chats/${chatId}`);
    return response.json();
  }

  async saveChatMessages(chatId, messages) {
    const response = await this.post(`/api/chats/${chatId}/save`, { messages });
    return response.json();
  }

  async deleteChat(chatId) {
    const response = await this.delete(`/api/chats/${chatId}`);
    return response.json();
  }

  async resetChat() {
    const response = await this.post('/api/reset');
    return response.json();
  }

  // Settings API methods
  async getSettings() {
    const response = await this.get('/api/settings/');
    return response.json();
  }

  async saveSettings(settings) {
    const response = await this.post('/api/settings/', settings);
    const result = await response.json();

    // Update local settings
    this.saveSettingsLocally(settings);

    return result;
  }

  // Save settings to localStorage only (renamed to avoid recursion)
  saveSettingsLocally(settings) {
    try {
      localStorage.setItem('chat_settings', JSON.stringify(settings));
      this.settings = settings;

      // Update baseUrl if it changed
      if (settings?.backend?.api_endpoint) {
        this.baseUrl = settings.backend.api_endpoint;
      }
    } catch (error) {
      console.error('Error saving settings locally:', error);
    }
  }

  async getBackendSettings() {
    const response = await this.get('/api/settings/backend');
    return response.json();
  }

  async saveBackendSettings(backendSettings) {
    const response = await this.post('/api/settings/backend', { settings: backendSettings });
    return response.json();
  }

  // Knowledge Base API methods
  async searchKnowledge(query, limit = 10) {
    const response = await this.post('/api/knowledge_base/search', { query, limit });
    return response.json();
  }

  async addTextToKnowledge(text, title = '', source = 'Manual Entry') {
    const response = await this.post('/api/knowledge_base/add_text', { text, title, source });
    return response.json();
  }

  async addUrlToKnowledge(url, method = 'fetch') {
    const response = await this.post('/api/knowledge_base/add_url', { url, method });
    return response.json();
  }

  async addFileToKnowledge(file) {
    const formData = new FormData();
    formData.append('file', file);
    const response = await this.post('/api/knowledge_base/add_file', formData);
    return response.json();
  }

  async exportKnowledge() {
    const response = await this.get('/api/knowledge_base/export');
    return response.blob();
  }

  async cleanupKnowledge() {
    const response = await this.post('/api/knowledge_base/cleanup');
    return response.json();
  }

  async getKnowledgeStats() {
    const response = await this.get('/api/knowledge_base/stats');
    return response.json();
  }

  async getDetailedKnowledgeStats() {
    const response = await this.get('/api/knowledge_base/detailed_stats');
    return response.json();
  }

  // Prompts API methods
  async getPrompts() {
    const response = await this.get('/api/prompts/');
    return response.json();
  }

  async savePrompt(promptId, content) {
    const response = await this.post(`/api/prompts/${promptId}`, { content });
    return response.json();
  }

  async revertPrompt(promptId) {
    const response = await this.post(`/api/prompts/${promptId}/revert`);
    return response.json();
  }

  // Health and status methods
  async checkHealth() {
    const response = await this.get('/api/system/health');
    return response.json();
  }

  async restartBackend() {
    const response = await this.post('/api/system/restart');
    return response.json();
  }

  // Cleanup methods (integrating chat_api functionality)
  async cleanupMessages() {
    const response = await this.post('/api/chats/cleanup_messages');
    return response.json();
  }

  async cleanupAllChatData() {
    const response = await this.post('/api/chats/cleanup_all');
    return response.json();
  }

  // File Management API methods
  async listFiles(path = '') {
    const response = await this.get(`/api/files/list?path=${encodeURIComponent(path)}`);
    return response.json();
  }

  async uploadFile(file, path = '', overwrite = false) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('path', path);
    formData.append('overwrite', overwrite.toString());

    const response = await this.post('/api/files/upload', formData);
    return response.json();
  }

  async viewFile(path) {
    const response = await this.get(`/api/files/view/${encodeURIComponent(path)}`);
    return response.json();
  }

  async deleteFile(path) {
    const response = await this.delete('/api/files/delete', {
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    return response.json();
  }

  async downloadFile(path) {
    const response = await this.get(`/api/files/download/${encodeURIComponent(path)}`);
    return response.blob();
  }

  async createDirectory(path = '', name) {
    const formData = new FormData();
    formData.append('path', path);
    formData.append('name', name);

    const response = await this.post('/api/files/create_directory', formData);
    return response.json();
  }

  async getFileStats() {
    const response = await this.get('/api/files/stats');
    return response.json();
  }

  // Utility methods
  async uploadFileToEndpoint(endpoint, file, additionalData = {}) {
    const formData = new FormData();
    formData.append('file', file);

    // Add any additional data to the form
    Object.keys(additionalData).forEach(key => {
      formData.append(key, additionalData[key]);
    });

    const response = await this.post(endpoint, formData);
    return response.json();
  }

  async downloadFileFromEndpoint(endpoint, filename = null) {
    const response = await this.get(endpoint);
    const blob = await response.blob();

    if (filename) {
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    }

    return blob;
  }

  // Connection testing
  async testConnection() {
    try {
      const start = Date.now();
      await this.checkHealth();
      const latency = Date.now() - start;

      return {
        connected: true,
        latency: latency,
        message: `Connected (${latency}ms)`
      };
    } catch (error) {
      return {
        connected: false,
        error: error.message,
        message: `Connection failed: ${error.message}`
      };
    }
  }

  // Batch operations
  async batchRequest(requests) {
    const results = [];

    for (const request of requests) {
      try {
        const result = await this.request(request.endpoint, request.options);
        results.push({
          success: true,
          data: await result.json(),
          request: request
        });
      } catch (error) {
        results.push({
          success: false,
          error: error.message,
          request: request
        });
      }
    }

    return results;
  }

  // Set custom timeout
  setTimeout(timeout) {
    this.timeout = timeout;
  }

  // Get current timeout
  getTimeout() {
    return this.timeout;
  }

  // Update base URL
  setBaseUrl(url) {
    this.baseUrl = url;

    // Also update in settings
    if (this.settings.backend) {
      this.settings.backend.api_endpoint = url;
    } else {
      this.settings.backend = { api_endpoint: url };
    }

    this.saveSettingsLocally(this.settings);
  }

  // Get current base URL
  getBaseUrl() {
    return this.baseUrl;
  }

  // Error handling helper
  handleApiError(error, context = '') {
    console.error(`API Error${context ? ` in ${context}` : ''}:`, error);

    let userMessage = 'An unexpected error occurred.';

    if (error.message.includes('timeout')) {
      userMessage = 'Request timed out. Please check your connection and try again.';
    } else if (error.message.includes('HTTP 404')) {
      userMessage = 'The requested resource was not found.';
    } else if (error.message.includes('HTTP 403')) {
      userMessage = 'Access denied. Please check your permissions.';
    } else if (error.message.includes('HTTP 500')) {
      userMessage = 'Server error. Please try again later.';
    } else if (error.message.includes('Failed to fetch')) {
      userMessage = 'Cannot connect to the server. Please check if the backend is running.';
    }

    return {
      error: error.message,
      userMessage: userMessage,
      context: context
    };
  }

  // Check if endpoint is available
  async isEndpointAvailable(endpoint) {
    try {
      await this.get(endpoint);
      return true;
    } catch (error) {
      return false;
    }
  }

  // Get API status summary
  async getApiStatus() {
    const endpoints = [
      '/api/health',
      '/api/chats',
      '/api/settings/',
      '/api/prompts'
    ];

    const status = {
      baseUrl: this.baseUrl,
      timestamp: new Date().toISOString(),
      endpoints: {}
    };

    for (const endpoint of endpoints) {
      try {
        const start = Date.now();
        await this.get(endpoint);
        status.endpoints[endpoint] = {
          available: true,
          latency: Date.now() - start
        };
      } catch (error) {
        status.endpoints[endpoint] = {
          available: false,
          error: error.message
        };
      }
    }

    return status;
  }
}

// Create and export a singleton instance
const apiClient = new ApiClient();

export default apiClient;
export { ApiClient };
