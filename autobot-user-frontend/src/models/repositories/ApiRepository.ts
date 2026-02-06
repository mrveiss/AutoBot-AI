import type { ApiResponse, RequestOptions } from '@/types/models'

// Note: Window.rum type is defined in @/utils/RumAgent.ts

export interface ApiConfig {
  baseUrl: string
  timeout: number
  headers?: Record<string, string>
}

export interface CacheEntry {
  data: any
  expires: number
  endpoint: string
}

export class ApiRepository {
  private baseUrl: string
  private timeout: number
  private defaultHeaders: Record<string, string>
  private cache: Map<string, CacheEntry>
  private cacheConfig: {
    defaultTTL: number
    maxSize: number
    endpoints: Record<string, number>
  }

  constructor(config?: Partial<ApiConfig>) {
    this.baseUrl = config?.baseUrl || this.getDefaultBaseUrl()
    this.timeout = config?.timeout || 30000
    this.defaultHeaders = {
      'Content-Type': 'application/json',
      ...config?.headers
    }

    // Initialize cache
    this.cache = new Map()
    this.cacheConfig = {
      defaultTTL: 5 * 60 * 1000, // 5 minutes
      maxSize: 100,
      endpoints: {
        '/api/settings/': 10 * 60 * 1000, // 10 minutes
        '/api/system/health': 30 * 1000,   // 30 seconds
        '/api/prompts/': 15 * 60 * 1000,   // 15 minutes
        '/api/chats': 2 * 60 * 1000,       // 2 minutes
      }
    }
  }

  private getDefaultBaseUrl(): string {
    // CRITICAL FIX: When VITE_BACKEND_HOST is empty, use empty string for proxy mode
    // This prevents fallback to host.docker.internal which doesn't work in this environment
    const backendHost = import.meta.env.VITE_BACKEND_HOST;
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL;

    if (apiBaseUrl) {
      return apiBaseUrl;
    }

    if (!backendHost) {
      // Empty backend host = proxy mode (use relative URLs)
      return '';
    }

    return `${import.meta.env.VITE_HTTP_PROTOCOL || 'http'}://${backendHost}:${import.meta.env.VITE_BACKEND_PORT || '8001'}`;
  }

  // Cache management
  private getCacheKey(endpoint: string, params?: Record<string, any>): string {
    return `${endpoint}:${JSON.stringify(params || {})}`
  }

  private getCachedData(cacheKey: string): any | null {
    const entry = this.cache.get(cacheKey)
    if (!entry) return null

    if (Date.now() > entry.expires) {
      this.cache.delete(cacheKey)
      return null
    }

    return entry.data
  }

  private setCachedData(cacheKey: string, data: any, endpoint: string): void {
    const ttl = this.cacheConfig.endpoints[endpoint] || this.cacheConfig.defaultTTL
    const expires = Date.now() + ttl

    // Manage cache size - fix TypeScript error with proper key handling
    if (this.cache.size >= this.cacheConfig.maxSize) {
      const firstEntry = this.cache.keys().next()
      if (firstEntry.value) {
        this.cache.delete(firstEntry.value)
      }
    }

    this.cache.set(cacheKey, { data, expires, endpoint })
  }

  private trackApiCall(method: string, endpoint: string, startTime: number, endTime: number, status: number | string, error?: Error): void {
    // Fix TypeScript error with proper window.rum type checking
    if (typeof window !== 'undefined' && (window as any).rum && typeof (window as any).rum.trackApiCall === 'function') {
      (window as any).rum.trackApiCall(method, endpoint, startTime, endTime, status, error)
    }
  }

  // Core request method
  async request<T = any>(endpoint: string, options: RequestOptions = {}): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${endpoint}`
    const method = options.method || 'GET'
    const startTime = performance.now()

    // Check cache for GET requests
    if (method === 'GET' && !options.skipCache) {
      const cacheKey = this.getCacheKey(endpoint, options.params)
      const cachedData = this.getCachedData(cacheKey)

      if (cachedData) {
        return {
          data: cachedData,
          ok: true,
          status: 200,
          statusText: 'OK',
          headers: new Headers({ 'x-cache': 'hit' })
        } as ApiResponse<T>
      }
    }

    const config: RequestInit = {
      method,
      headers: {
        ...this.defaultHeaders,
        ...options.headers
      },
      ...options
    }

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), this.timeout)

    try {
      const response = await fetch(url, {
        ...config,
        signal: controller.signal
      })

      clearTimeout(timeoutId)
      const endTime = performance.now()

      if (!response.ok) {
        this.trackApiCall(method, endpoint, startTime, endTime, response.status)
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const contentType = response.headers.get('content-type')

      // CRITICAL FIX: For streaming responses, return raw Response without consuming body
      if (contentType?.includes('text/event-stream')) {
        this.trackApiCall(method, endpoint, startTime, endTime, response.status)
        return {
          data: response as unknown as T, // Return raw response for streaming
          ok: response.ok,
          status: response.status,
          statusText: response.statusText,
          headers: response.headers
        } as ApiResponse<T>
      }

      // Parse response data for non-streaming responses
      let data: T

      if (contentType?.includes('application/json')) {
        data = await response.json()
      } else if (contentType?.includes('text/')) {
        data = await response.text() as T
      } else {
        data = await response.blob() as T
      }

      // Cache successful GET responses
      if (method === 'GET' && !options.skipCache) {
        const cacheKey = this.getCacheKey(endpoint, options.params)
        this.setCachedData(cacheKey, data, endpoint)
      }

      this.trackApiCall(method, endpoint, startTime, endTime, response.status)

      return {
        data,
        ok: response.ok,
        status: response.status,
        statusText: response.statusText,
        headers: response.headers
      } as ApiResponse<T>

    } catch (error: any) {
      const endTime = performance.now()
      clearTimeout(timeoutId)

      if (error.name === 'AbortError') {
        const timeoutError = new Error(`Request timeout: ${method} ${endpoint} took longer than ${this.timeout}ms`)
        this.trackApiCall(method, endpoint, startTime, endTime, 'timeout', timeoutError)
        throw timeoutError
      }

      if (error.message === 'Failed to fetch') {
        const networkError = new Error(`Network error: Cannot connect to ${this.baseUrl}`)
        this.trackApiCall(method, endpoint, startTime, endTime, 'network_error', networkError)
        throw networkError
      }

      this.trackApiCall(method, endpoint, startTime, endTime, 'error', error)
      throw error
    }
  }

  // HTTP methods
  async get<T = any>(endpoint: string, options: Omit<RequestOptions, 'method'> = {}): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: 'GET' })
  }

  async post<T = any>(endpoint: string, data?: any, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<ApiResponse<T>> {
    const config: RequestOptions = { ...options, method: 'POST' }

    if (data) {
      if (data instanceof FormData) {
        // Remove content-type header for FormData
        const headers = { ...config.headers }
        delete headers['Content-Type']
        config.headers = headers
        config.body = data
      } else {
        config.body = JSON.stringify(data)
      }
    }

    return this.request<T>(endpoint, config)
  }

  async put<T = any>(endpoint: string, data?: any, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<ApiResponse<T>> {
    const config: RequestOptions = { ...options, method: 'PUT' }
    if (data) {
      config.body = JSON.stringify(data)
    }
    return this.request<T>(endpoint, config)
  }

  async delete<T = any>(endpoint: string, options: Omit<RequestOptions, 'method'> = {}): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' })
  }

  // Utility methods
  setBaseUrl(url: string): void {
    this.baseUrl = url
  }

  getBaseUrl(): string {
    return this.baseUrl
  }

  setTimeout(timeout: number): void {
    this.timeout = timeout
  }

  clearCache(pattern?: string): void {
    if (pattern) {
      for (const [key] of this.cache.entries()) {
        if (key.includes(pattern)) {
          this.cache.delete(key)
        }
      }
    } else {
      this.cache.clear()
    }
  }

  getCacheStats() {
    return {
      size: this.cache.size,
      maxSize: this.cacheConfig.maxSize,
      entries: Array.from(this.cache.entries()).map(([key, entry]) => ({
        key,
        endpoint: entry.endpoint,
        expiresIn: Math.max(0, entry.expires - Date.now()),
        size: JSON.stringify(entry.data).length
      }))
    }
  }

  async testConnection(): Promise<{ connected: boolean; latency?: number; message: string }> {
    try {
      const start = Date.now()
      await this.get('/api/system/health')
      const latency = Date.now() - start

      return {
        connected: true,
        latency,
        message: `Connected (${latency}ms)`
      }
    } catch (error: any) {
      return {
        connected: false,
        message: `Connection failed: ${error.message}`
      }
    }
  }
}
