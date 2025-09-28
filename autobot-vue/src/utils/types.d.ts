// Type declarations for JavaScript modules

declare module '@/composables/useGlobalWebSocket.js' {
  export function useGlobalWebSocket(): {
    isConnected: import('vue').Ref<boolean>
    send: (data: any) => boolean
    on: (handler: (data: any) => void) => () => void
    state: import('vue').Ref<Record<string, any>>
  } | undefined
}

declare module '@/utils/ChatIdGenerator.js' {
  export function generateChatId(): string
  export function generateMessageId(): string
}

declare module '@/utils/ApiClient.js' {
  interface ApiClient {
    get(endpoint: string): Promise<Response>
    post(endpoint: string, data?: any): Promise<Response>
    put(endpoint: string, data?: any): Promise<Response>
    delete(endpoint: string): Promise<Response>
    uploadFile(file: File, options?: { metadata?: any }): Promise<Response>
    createNewChat(): Promise<{ chatId: string; [key: string]: any }>
    sendChatMessage(message: string, options?: any): Promise<any>
    getChatMessages(chatId: string): Promise<any>
    request(endpoint: string, options?: any): Promise<Response>
  }

  const apiClient: ApiClient
  export default apiClient
}

// System status indicator type enhancement
interface SystemStatusIndicator {
  status: string;
  text: string;
  pulse: boolean;
  statusDetails?: {
    lastCheck: number;
    consecutiveFailures?: number;
    error?: string;
  };
}

// Service info types for proper compatibility
interface ServiceInfo {
  name: string;
  status: string;
  statusText: string;
  version?: string;
  responseTime?: number;
}