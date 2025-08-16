/**
 * TypeScript declarations for the existing JavaScript ApiClient
 */

declare module '@/utils/ApiClient' {
  interface ApiClient {
    baseUrl: string
    timeout: number
    settings: any

    // Request methods
    request(endpoint: string, options?: any): Promise<Response>
    get(endpoint: string, options?: any): Promise<Response>
    post(endpoint: string, data?: any, options?: any): Promise<Response>
    put(endpoint: string, data?: any, options?: any): Promise<Response>
    delete(endpoint: string, options?: any): Promise<Response>

    // Chat methods
    sendChatMessage(message: string, options?: any): Promise<any>
    createNewChat(): Promise<any>
    getChatList(): Promise<any>
    getChatMessages(chatId: string): Promise<any>
    saveChatMessages(chatId: string, messages: any[]): Promise<any>
    deleteChat(chatId: string): Promise<any>
    resetChat(): Promise<any>

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
    listFiles(path?: string): Promise<any>
    uploadFile(file: File, path?: string, overwrite?: boolean): Promise<any>
    viewFile(path: string): Promise<any>
    deleteFile(path: string): Promise<any>
    downloadFile(path: string): Promise<Blob>
    createDirectory(path?: string, name: string): Promise<any>
    getFileStats(): Promise<any>

    // Utility methods
    setTimeout(timeout: number): void
    setBaseUrl(url: string): void
    getBaseUrl(): string
    testConnection(): Promise<any>
    checkHealth(): Promise<any>
  }

  const apiClient: ApiClient
  export default apiClient
  export { ApiClient }
}
