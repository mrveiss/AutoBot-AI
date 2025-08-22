// ApiClient.ts - Unified API client for all backend operations
// RumAgent is accessed via window.rum global

// Type declarations for window.rum (extending existing interface)
interface RumApi {
  trackUserInteraction(event: string, element: any, data?: any): void;
  trackApiCall(method: string, endpoint: string, startTime: number, endTime: number, status: number | string, error?: Error): void;
  reportCriticalIssue(type: string, data: any): void;
}

declare global {
  interface Window {
    rum?: RumApi;
  }
}

export interface ApiResponse {
  json(): Promise<any>;
  text(): Promise<string>;
  blob(): Promise<Blob>;
  ok: boolean;
  status: number;
  statusText: string;
  headers: Headers;
}

export interface RequestOptions {
  method?: string;
  headers?: Record<string, string>;
  body?: string | FormData;
  signal?: AbortSignal;
  timeout?: number;
}

export class ApiClient {
  baseUrl: string;
  timeout: number;
  settings: any;

  constructor() {
    this.baseUrl = import.meta.env.VITE_API_BASE_URL ||
      `${import.meta.env.VITE_HTTP_PROTOCOL || 'http'}://${import.meta.env.VITE_BACKEND_HOST || '127.0.0.3'}:${import.meta.env.VITE_BACKEND_PORT || '8001'}`;
    this.timeout = 30000; // 30 seconds default timeout
    this.settings = this.loadSettings();

    // Update baseUrl from settings if available
    if (this.settings?.backend?.api_endpoint) {
      this.baseUrl = this.settings.backend.api_endpoint;
    }
  }

  // Load settings from localStorage
  loadSettings(): any {
    try {
      const savedSettings = localStorage.getItem('chat_settings');
      return savedSettings ? JSON.parse(savedSettings) : {};
    } catch (error) {
      console.error('Error loading settings:', error);
      return {};
    }
  }

  // Generic request method with error handling and timeout
  async request(endpoint: string, options: RequestOptions = {}): Promise<ApiResponse> {
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

    const config: RequestInit = {
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
      return response as ApiResponse;

    } catch (error: any) {
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
  async get(endpoint: string, options: RequestOptions = {}): Promise<ApiResponse> {
    return this.request(endpoint, { method: 'GET', ...options });
  }

  // POST request
  async post(endpoint: string, data: any = null, options: RequestOptions = {}): Promise<ApiResponse> {
    const config: RequestOptions = { method: 'POST', ...options };

    if (data) {
      if (data instanceof FormData) {
        // Don't set Content-Type for FormData, let browser handle it
        if (config.headers && config.headers['Content-Type']) {
          delete config.headers['Content-Type'];
        }
        config.body = data;
      } else {
        config.body = JSON.stringify(data);
      }
    }

    return this.request(endpoint, config);
  }

  // PUT request
  async put(endpoint: string, data: any = null, options: RequestOptions = {}): Promise<ApiResponse> {
    const config: RequestOptions = { method: 'PUT', ...options };
    if (data) {
      config.body = JSON.stringify(data);
    }
    return this.request(endpoint, config);
  }

  // DELETE request
  async delete(endpoint: string, options: RequestOptions = {}): Promise<ApiResponse> {
    return this.request(endpoint, { method: 'DELETE', ...options });
  }

  // Chat API methods
  async sendChatMessage(message: string, options: any = {}): Promise<any> {
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

  async createNewChat(): Promise<any> {
    const response = await this.post('/api/chats/new');
    return response.json();
  }

  async getChatList(): Promise<any> {
    const response = await this.get('/api/chats');
    return response.json();
  }

  async getChatMessages(chatId: string): Promise<any> {
    const response = await this.get(`/api/chats/${chatId}`);
    return response.json();
  }

  async saveChatMessages(chatId: string, messages: any[]): Promise<any> {
    const response = await this.post(`/api/chats/${chatId}/save`, { messages });
    return response.json();
  }

  async deleteChat(chatId: string): Promise<any> {
    const response = await this.delete(`/api/chats/${chatId}`);
    return response.json();
  }

  async resetChat(): Promise<any> {
    const response = await this.post('/api/reset');
    return response.json();
  }

  // Settings API methods
  async getSettings(): Promise<any> {
    const response = await this.get('/api/settings/');
    return response.json();
  }

  async saveSettings(settings: any): Promise<any> {
    const response = await this.post('/api/settings/', settings);
    const result = await response.json();

    // Update local settings
    this.saveSettingsLocally(settings);

    return result;
  }

  // Save settings to localStorage only (renamed to avoid recursion)
  saveSettingsLocally(settings: any): void {
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

  async getBackendSettings(): Promise<any> {
    const response = await this.get('/api/settings/backend');
    return response.json();
  }

  async saveBackendSettings(backendSettings: any): Promise<any> {
    const response = await this.post('/api/settings/backend', { settings: backendSettings });
    return response.json();
  }

  // Knowledge Base API methods
  async searchKnowledge(query: string, limit: number = 10): Promise<any> {
    const response = await this.post('/api/knowledge_base/search', { query, limit });
    return response.json();
  }

  async addTextToKnowledge(text: string, title: string = '', source: string = 'Manual Entry'): Promise<any> {
    const response = await this.post('/api/knowledge_base/add_text', { text, title, source });
    return response.json();
  }

  async addUrlToKnowledge(url: string, method: string = 'fetch'): Promise<any> {
    const response = await this.post('/api/knowledge_base/add_url', { url, method });
    return response.json();
  }

  async addFileToKnowledge(file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    const response = await this.post('/api/knowledge_base/add_file', formData);
    return response.json();
  }

  async exportKnowledge(): Promise<Blob> {
    const response = await this.get('/api/knowledge_base/export');
    return response.blob();
  }

  async cleanupKnowledge(): Promise<any> {
    const response = await this.post('/api/knowledge_base/cleanup');
    return response.json();
  }

  async getKnowledgeStats(): Promise<any> {
    const response = await this.get('/api/knowledge_base/stats');
    return response.json();
  }

  async getDetailedKnowledgeStats(): Promise<any> {
    const response = await this.get('/api/knowledge_base/detailed_stats');
    return response.json();
  }

  // Additional methods would continue here following the same pattern...
  // For brevity, I'll add the key ones the component uses

  // Health and status methods
  async checkHealth(): Promise<any> {
    const response = await this.get('/api/system/health');
    return response.json();
  }

  // Connection testing
  async testConnection(): Promise<{ connected: boolean; latency?: number; error?: string; message: string }> {
    try {
      const start = Date.now();
      await this.checkHealth();
      const latency = Date.now() - start;

      return {
        connected: true,
        latency: latency,
        message: `Connected (${latency}ms)`
      };
    } catch (error: any) {
      return {
        connected: false,
        error: error.message,
        message: `Connection failed: ${error.message}`
      };
    }
  }
}

// Create and export a singleton instance
const apiClient = new ApiClient();

export default apiClient;
