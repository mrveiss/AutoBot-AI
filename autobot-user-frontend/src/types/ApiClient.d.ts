/**
 * TypeScript declarations for the existing JavaScript ApiClient
 * Issue #701: Complete type definitions for all ApiClient methods
 */

// Response types for browser session operations
interface BrowserSessionResponse {
  session_id?: string
  current_url?: string | null
  interaction_required?: boolean
  browser_status?: string
  status?: string
  [key: string]: unknown
}

// Response types for file operations
interface FileListResponse {
  files?: Array<{ name: string; path: string; type: string; size?: number }>
  tree?: unknown
  [key: string]: unknown
}

interface FileContentResponse {
  content?: string
  [key: string]: unknown
}

// Generic API response type
interface ApiResponse {
  success?: boolean
  data?: unknown
  error?: string
  message?: string
  [key: string]: unknown
}

declare module '@/utils/ApiClient.js' {
  interface ApiClient {
    baseUrl: string
    timeout: number
    settings: any

    // Request methods
    request(endpoint: string, options?: any): Promise<Response>
    get(endpoint: string, options?: any): Promise<ApiResponse>
    post(endpoint: string, data?: any, options?: any): Promise<ApiResponse>
    put(endpoint: string, data?: any, options?: any): Promise<ApiResponse>
    delete(endpoint: string, options?: any): Promise<ApiResponse>

    // Chat methods
    sendChatMessage(message: string, options?: any): Promise<any>
    createNewChat(): Promise<any>
    getChatList(): Promise<any>
    getChatMessages(chatId: string): Promise<any>
    saveChatMessages(chatId: string, messages: any[]): Promise<any>
    deleteChat(chatId: string): Promise<any>
    resetChat(): Promise<any>

    // Chat Browser Session methods (Issue #701)
    getOrCreateChatBrowserSession(config?: {
      conversation_id?: string
      headless?: boolean
    }): Promise<BrowserSessionResponse>
    getChatBrowserSession(conversationId: string): Promise<BrowserSessionResponse>
    deleteChatBrowserSession(conversationId: string): Promise<ApiResponse>

    // Settings methods
    getSettings(): Promise<any>
    saveSettings(settings: any): Promise<any>
    getBackendSettings(): Promise<any>
    saveBackendSettings(backendSettings: any): Promise<any>

    // Knowledge base methods
    searchKnowledge(query: string, limit?: number): Promise<any>
    addTextToKnowledge(text: string, title?: string, source?: string): Promise<any>
    addUrlToKnowledge(url: string, method?: string): Promise<any>
    addFileToKnowledge(file: File): Promise<any>

    // File Management methods
    listFiles(path?: string): Promise<FileListResponse>
    uploadFile(file: File, path?: string, overwrite?: boolean): Promise<any>
    viewFile(path: string): Promise<FileContentResponse>
    deleteFile(path: string): Promise<any>
    downloadFile(path: string): Promise<Blob>
    createDirectory(path?: string, name: string): Promise<any>
    getFileStats(): Promise<any>

    // Terminal Session methods (Issue #701)
    createTerminalSession(options?: any): Promise<any>
    deleteTerminalSession(sessionId: string): Promise<any>
    getTerminalSessions(): Promise<any>
    getTerminalSessionInfo(sessionId: string): Promise<any>
    executeTerminalCommand(sessionId: string, command: string): Promise<any>

    // Agent Terminal Session methods (Issue #701)
    createAgentTerminalSession(options?: any): Promise<any>
    deleteAgentTerminalSession(sessionId: string): Promise<any>
    getAgentTerminalSessions(): Promise<any>

    // Utility methods
    setTimeout(timeout: number): void
    setBaseUrl(url: string): void
    getBaseUrl(): string
    getApiUrl(): string
    invalidateCache(): void
    testConnection(): Promise<any>
    checkHealth(): Promise<any>
    validateConnection(): Promise<boolean>
    initializeConfiguration(): Promise<void>
  }

  const apiClient: ApiClient
  export default apiClient
  export { ApiClient, ApiResponse, BrowserSessionResponse, FileListResponse, FileContentResponse }
}
