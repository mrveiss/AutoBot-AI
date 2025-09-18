// ApiClient.ts - Unified API client for all backend operations
// RumAgent is accessed via window.rum global
// MIGRATION: Now uses AppConfig.js for centralized configuration

import appConfig from '../config/AppConfig.js';

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
    // Use synchronous fallback for constructor, but recommend async getBaseUrl() method
    this.baseUrl = this.getSyncBaseUrl();
    this.timeout = 30000; // 30 seconds default timeout (balance between functionality and responsiveness)
    this.settings = this.loadSettings();

    // Update baseUrl from settings if available
    if (this.settings?.backend?.api_endpoint) {
      // Ensure we don't get URL duplication from corrupted settings
      let settingsUrl = this.settings.backend.api_endpoint;

      // Clean up any existing protocol prefixes in settings URL to avoid duplication
      if (settingsUrl.startsWith('http://http://') || settingsUrl.startsWith('https://https://')) {
        // Fix double protocol issue
        settingsUrl = settingsUrl.replace(/^https?:\/\//, '');
      }

      if (!settingsUrl.startsWith('http')) {
        // Relative URL or partial URL, prepend base only if not already included
        if (settingsUrl.startsWith('/')) {
          this.baseUrl = `${this.baseUrl}${settingsUrl}`;
        } else {
          this.baseUrl = `${this.baseUrl}/${settingsUrl}`;
        }
      } else {
        // Absolute URL, use as-is
        this.baseUrl = settingsUrl;
      }
    }
  }

  // Get synchronous base URL for constructor (fallback only)
  getSyncBaseUrl(): string {
    const backendHost = import.meta.env.VITE_BACKEND_HOST;
    const backendPort = import.meta.env.VITE_BACKEND_PORT || '8001';
    const protocol = import.meta.env.VITE_HTTP_PROTOCOL || 'http';
    
    if (backendHost) {
      return `${protocol}://${backendHost}:${backendPort}`;
    }
    
    // Fallback to localhost for development
    return `${protocol}://localhost:${backendPort}`;
  }

  // Get base URL using AppConfig service (recommended)
  async getBaseUrl(): Promise<string> {
    try {
      return await appConfig.getServiceUrl('backend');
    } catch (error) {
      console.warn('Failed to get backend URL from AppConfig, using fallback:', error);
      return this.baseUrl;
    }
  }

  // Enhanced request method that uses AppConfig when possible
  async requestWithConfig(endpoint: string, options: RequestOptions = {}): Promise<ApiResponse> {
    const baseUrl = await this.getBaseUrl();

    // Clean URL construction to prevent double protocols
    let url: string;
    if (endpoint.startsWith('http')) {
      url = endpoint;
    } else {
      // Ensure endpoint starts with / for proper concatenation
      const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
      url = `${baseUrl}${cleanEndpoint}`;
    }

    // Validate URL to catch double protocol issues
    if (url.includes('http://http://') || url.includes('https://https://')) {
      console.error('MALFORMED URL DETECTED:', url);
      // Fix by removing the duplicate protocol
      url = url.replace(/^(https?:\/\/)(https?:\/\/)/, '$1');
    }

    return this._makeRequest(url, options);
  }

  // Private method for making the actual request
  private async _makeRequest(url: string, options: RequestOptions = {}): Promise<ApiResponse> {
    const method = options.method || 'GET';
    
    // Debug URL construction
    if (url.includes('http://') && url.lastIndexOf('http://') > 0) {
      console.error('DUPLICATE URL DETECTED:', url);
    }
    
    const startTime = performance.now();
    
    // Set up headers
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers
    };
    
    // Set up timeout
    const controller = new AbortController();
    const timeout = options.timeout || this.timeout;
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
      const fetchOptions = {
        method,
        headers,
        body: options.body,
        signal: controller.signal
      };
      
      const response = await fetch(url, fetchOptions);
      const endTime = performance.now();
      
      // Track API call if RUM is available
      if (window.rum) {
        window.rum.trackApiCall(method, url, startTime, endTime, response.status);
      }
      
      clearTimeout(timeoutId);
      return response as ApiResponse;
      
    } catch (error) {
      clearTimeout(timeoutId);
      const endTime = performance.now();
      
      // Track API call failure if RUM is available
      if (window.rum) {
        window.rum.trackApiCall(method, url, startTime, endTime, 'error', error as Error);
      }
      
      console.error(`[ApiClient] ${method} ${url} failed:`, error);
      throw error;
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

  // Generic request method with error handling and timeout (legacy - use requestWithConfig for new code)
  async request(endpoint: string, options: RequestOptions = {}): Promise<ApiResponse> {
    // Handle absolute URLs vs relative endpoints with clean URL construction
    let url: string;
    if (endpoint.startsWith('http')) {
      url = endpoint;
    } else {
      // Ensure endpoint starts with / for proper concatenation
      const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
      url = `${this.baseUrl}${cleanEndpoint}`;
    }

    // Validate URL to catch double protocol issues
    if (url.includes('http://http://') || url.includes('https://https://')) {
      console.error('MALFORMED URL DETECTED in legacy request:', url);
      // Fix by removing the duplicate protocol
      url = url.replace(/^(https?:\/\/)(https?:\/\/)/, '$1');
    }

    return this._makeRequest(url, options);
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
    const response = await this.post('/api/chat/chats/new');
    return response.json();
  }

  async getChatList(): Promise<any> {
    const response = await this.get('/api/chat/chats');
    return response.json();
  }

  async getChatMessages(chatId: string): Promise<any> {
    const response = await this.get(`/api/chat/chats/${chatId}`);
    return response.json();
  }

  async saveChatMessages(chatId: string, messages: any[]): Promise<any> {
    const response = await this.post(`/api/chat/chats/${chatId}/save`, { messages });
    return response.json();
  }

  async deleteChat(chatId: string): Promise<any> {
    const response = await this.delete(`/api/chat/chats/${chatId}`);
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
    const response = await this.get('/api/health');
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
