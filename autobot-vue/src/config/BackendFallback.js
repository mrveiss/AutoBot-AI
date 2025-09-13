/**
 * BackendFallbackService - Intelligent Backend Connection Management
 * 
 * Provides smart backend connection handling with multiple fallback strategies:
 * - Automatic backend discovery and health checking
 * - Mock mode for development when backend is unavailable
 * - Graceful degradation of frontend functionality
 * - Real-time connection recovery
 */

export class BackendFallbackService {
  constructor() {
    // SINGLE FRONTEND SERVER ARCHITECTURE:
    // Frontend VM (172.16.168.21) connects to Backend VM (172.16.168.20:8001)
    this.backendHosts = [
      '172.16.168.20:8001',  // Primary: Backend VM
      'localhost:8001',       // Fallback: Local development
      '127.0.0.1:8001'       // Final fallback
    ];
    
    this.currentBackend = null;
    this.connectionStatus = 'checking';
    this.mockMode = false;
    this.lastHealthCheck = 0;
    this.healthCheckInterval = 30000; // 30 seconds
    this.connectionListeners = [];
    
    // Mock data for development mode
    this.mockResponses = this.initializeMockResponses();
    
    this.log('BackendFallbackService initialized');
    this.startBackendDiscovery();
  }

  /**
   * Initialize mock responses for development mode
   */
  initializeMockResponses() {
    return {
      '/api/system/health': {
        status: 'ok',
        timestamp: new Date().toISOString(),
        services: {
          database: 'connected',
          llm: 'available',
          knowledge: 'ready'
        }
      },
      '/api/system/info': {
        version: '1.0.0-dev',
        mode: 'development',
        features: ['chat', 'knowledge', 'terminal', 'desktop']
      },
      '/api/chat/chats': [],
      '/api/knowledge_base/stats': {
        total_documents: 0,
        total_chunks: 0,
        total_facts: 0
      }
    };
  }

  /**
   * Start automatic backend discovery
   */
  async startBackendDiscovery() {
    this.log('Starting backend discovery...');
    
    for (const host of this.backendHosts) {
      const protocol = window.location.protocol === 'https:' ? 'https' : 'http';
      const backendUrl = `${protocol}://${host}`;
      
      try {
        this.log(`Testing backend: ${backendUrl}`);
        const isHealthy = await this.checkBackendHealth(backendUrl);
        
        if (isHealthy) {
          this.currentBackend = backendUrl;
          this.connectionStatus = 'connected';
          this.mockMode = false;
          this.log(`✅ Connected to backend: ${backendUrl}`);
          this.notifyConnectionChange('connected', backendUrl);
          this.startHealthMonitoring();
          return;
        }
      } catch (error) {
        this.log(`❌ Failed to connect to ${backendUrl}:`, error.message);
      }
    }
    
    // No backend available - enable mock mode
    this.enableMockMode();
  }

  /**
   * Enable mock mode for development
   */
  enableMockMode() {
    this.log('🔄 No backend available - enabling mock mode for development');
    this.mockMode = true;
    this.connectionStatus = 'mock';
    this.currentBackend = null;
    this.notifyConnectionChange('mock', null);
    
    // Show user notification
    this.showMockModeNotification();
    
    // Continue trying to reconnect in background
    setTimeout(() => this.startBackendDiscovery(), 10000);
  }

  /**
   * Check backend health
   */
  async checkBackendHealth(backendUrl, timeout = 5000) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
      const response = await fetch(`${backendUrl}/api/system/health`, {
        method: 'GET',
        signal: controller.signal,
        headers: {
          'Cache-Control': 'no-cache',
          'X-Health-Check': Date.now().toString()
        }
      });
      
      clearTimeout(timeoutId);
      return response.ok;
    } catch (error) {
      clearTimeout(timeoutId);
      return false;
    }
  }

  /**
   * Start health monitoring for connected backend
   */
  startHealthMonitoring() {
    if (this.healthMonitorInterval) {
      clearInterval(this.healthMonitorInterval);
    }
    
    this.healthMonitorInterval = setInterval(async () => {
      if (this.currentBackend) {
        const isHealthy = await this.checkBackendHealth(this.currentBackend);
        
        if (!isHealthy && this.connectionStatus === 'connected') {
          this.log('❌ Backend health check failed - switching to mock mode');
          this.enableMockMode();
        }
      }
    }, this.healthCheckInterval);
  }

  /**
   * Enhanced fetch with automatic fallback
   */
  async fetchWithFallback(endpoint, options = {}) {
    // If in mock mode, return mock response
    if (this.mockMode) {
      return this.handleMockRequest(endpoint, options);
    }
    
    // If no backend available, enable mock mode
    if (!this.currentBackend) {
      this.enableMockMode();
      return this.handleMockRequest(endpoint, options);
    }
    
    const url = `${this.currentBackend}${endpoint}`;
    const fetchOptions = {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-Frontend-Version': '1.0.0',
        ...options.headers
      }
    };
    
    try {
      this.log(`🌐 API Request: ${options.method || 'GET'} ${url}`);
      const response = await fetch(url, fetchOptions);
      
      if (response.ok) {
        this.log(`✅ API Response: ${response.status}`);
        return response;
      } else {
        this.log(`⚠️ API Response: ${response.status} ${response.statusText}`);
        return response; // Let caller handle non-200 responses
      }
    } catch (error) {
      this.log(`❌ API Request failed:`, error.message);
      
      // If network error, try to reconnect
      if (error.message.includes('Failed to fetch') || error.name === 'AbortError') {
        this.log('🔄 Network error detected - attempting backend rediscovery');
        setTimeout(() => this.startBackendDiscovery(), 1000);
        
        // Return mock response for immediate UX
        return this.handleMockRequest(endpoint, options);
      }
      
      throw error;
    }
  }

  /**
   * Handle mock requests for development mode
   */
  async handleMockRequest(endpoint, options = {}) {
    this.log(`🎭 Mock Request: ${options.method || 'GET'} ${endpoint}`);
    
    // Simulate network delay
    await new Promise(resolve => setTimeout(resolve, 200 + Math.random() * 300));
    
    const mockData = this.mockResponses[endpoint];
    if (mockData) {
      return new Response(JSON.stringify(mockData), {
        status: 200,
        statusText: 'OK (Mock)',
        headers: {
          'Content-Type': 'application/json',
          'X-Mock-Mode': 'true'
        }
      });
    }
    
    // Default mock response
    return new Response(JSON.stringify({
      status: 'mock',
      message: `Mock response for ${endpoint}`,
      data: null
    }), {
      status: 200,
      statusText: 'OK (Mock)',
      headers: {
        'Content-Type': 'application/json',
        'X-Mock-Mode': 'true'
      }
    });
  }

  /**
   * Get WebSocket URL with fallback
   */
  getWebSocketUrl() {
    if (this.mockMode || !this.currentBackend) {
      // Return mock WebSocket URL (won't actually connect)
      return 'ws://mock-websocket/ws';
    }
    
    const wsProtocol = this.currentBackend.startsWith('https') ? 'wss' : 'ws';
    const wsUrl = this.currentBackend.replace(/^https?/, wsProtocol);
    return `${wsUrl}/ws`;
  }

  /**
   * Add connection change listener
   */
  addConnectionListener(listener) {
    this.connectionListeners.push(listener);
  }

  /**
   * Remove connection change listener
   */
  removeConnectionListener(listener) {
    const index = this.connectionListeners.indexOf(listener);
    if (index > -1) {
      this.connectionListeners.splice(index, 1);
    }
  }

  /**
   * Notify listeners of connection changes
   */
  notifyConnectionChange(status, backendUrl) {
    this.connectionListeners.forEach(listener => {
      try {
        listener({ status, backendUrl, mockMode: this.mockMode });
      } catch (error) {
        this.log('Error notifying connection listener:', error);
      }
    });
  }

  /**
   * Show mock mode notification to user
   */
  showMockModeNotification() {
    // Create a temporary notification
    const notification = document.createElement('div');
    notification.className = 'fixed top-4 right-4 bg-yellow-500 text-white px-4 py-2 rounded shadow-lg z-50';
    notification.innerHTML = `
      <div class="flex items-center">
        <svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
        </svg>
        <span>Development Mode: Backend unavailable, using mock data</span>
        <button onclick="this.parentElement.parentElement.remove()" class="ml-2 text-white hover:text-gray-200">×</button>
      </div>
    `;
    
    document.body.appendChild(notification);
    
    // Auto-remove after 10 seconds
    setTimeout(() => {
      if (document.body.contains(notification)) {
        document.body.removeChild(notification);
      }
    }, 10000);
  }

  /**
   * Force backend reconnection attempt
   */
  async forceReconnect() {
    this.log('🔄 Force reconnect requested');
    clearInterval(this.healthMonitorInterval);
    await this.startBackendDiscovery();
  }

  /**
   * Get current connection status
   */
  getConnectionStatus() {
    return {
      status: this.connectionStatus,
      backend: this.currentBackend,
      mockMode: this.mockMode,
      lastCheck: this.lastHealthCheck
    };
  }

  /**
   * Debug logging
   */
  log(...args) {
    if (import.meta.env.DEV || import.meta.env.VITE_ENABLE_DEBUG === 'true') {
      console.log('[AutoBot Backend Fallback]', ...args);
    }
  }

  /**
   * Clean up resources
   */
  destroy() {
    if (this.healthMonitorInterval) {
      clearInterval(this.healthMonitorInterval);
    }
    this.connectionListeners = [];
  }
}

// Singleton instance
const backendFallback = new BackendFallbackService();

export default backendFallback;