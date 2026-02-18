/**
 * Vue API Client Plugin
 *
 * This plugin provides a centralized, pre-configured API client instance
 * that can be injected throughout the Vue application, ensuring consistent
 * configuration and eliminating duplicate API client instantiation.
 */

import type { App } from 'vue'
import apiClient from '@/utils/ApiClient'

// Re-export the type from our declaration file
export type ApiClientType = typeof apiClient

// Configuration interface for the API plugin
interface ApiPluginOptions {
  baseURL?: string
  timeout?: number
}

// Global API client instance (using the existing singleton)
const apiClientInstance: ApiClientType = apiClient

// Configure the existing API client
function configureApiClient(options: ApiPluginOptions = {}) {
  if (options.baseURL) {
    apiClientInstance.setBaseUrl(options.baseURL)
  }

  if (options.timeout) {
    apiClientInstance.setTimeout(options.timeout)
  }

  return apiClientInstance
}

// Vue plugin definition
export default {
  install(app: App, options: ApiPluginOptions = {}) {
    // Configure the existing API client instance
    configureApiClient(options)

    // Provide the API client globally
    app.provide('apiClient', apiClientInstance)

    // Add to global properties for Options API compatibility
    app.config.globalProperties.$api = apiClientInstance
    app.config.globalProperties.$getApiClient = () => apiClientInstance
  }
}

// Export function to get API client instance outside of Vue components
export function useApiClient(): ApiClientType {
  return apiClientInstance
}

// Type declarations for global properties
declare module '@vue/runtime-core' {
  interface ComponentCustomProperties {
    $api: ApiClientType
    $getApiClient: () => ApiClientType
  }
}
