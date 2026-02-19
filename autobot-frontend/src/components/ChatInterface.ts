// ChatInterface TypeScript definitions and setup
import { ref, computed, onUnmounted, nextTick } from 'vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for ChatInterface
const logger = createLogger('ChatInterface')
import type {
  ChatMessage,
  ChatSession,
  WebSocketMessage,
  LLMResponse,
  AppSettings,
  KnowledgeBaseStatus,
  FileUploadResponse
} from '@/types/api'
import { useGlobalWebSocket } from '@/composables/useGlobalWebSocket'
import { generateChatId } from '@/utils/ChatIdGenerator.js'
import { apiService } from '@/services/api'
import apiClient from '@/utils/ApiClient'

// Chat Interface Composable
export function useChatInterface() {
  // WebSocket integration
  const wsService = useGlobalWebSocket()
  const wsConnected = wsService?.isConnected || ref(false)
  const _wsOn = wsService?.on || (() => () => {})  // Reserved for future use
  const wsSend = wsService?.send || (() => false)
  const wsState = wsService?.state || ref({})

  // Core reactive state
  const sidebarCollapsed = ref(false)
  const activeTab = ref<'chat' | 'terminal' | 'computer' | 'browser'>('chat')
  const inputMessage = ref('')
  const messages = ref<ChatMessage[]>([])
  const chatList = ref<ChatSession[]>([])
  const currentChatId = ref<string | null>(null)
  const attachedFiles = ref<File[]>([])

  // UI state
  const systemReloading = ref(false)
  const reloadNeeded = ref(false)
  const chatMessages = ref<HTMLElement | null>(null)

  // Knowledge base state with proper typing
  const kbStatus = ref<KnowledgeBaseStatus>({
    status: 'loading',
    message: 'Loading knowledge base status...',
    progress: 0,
    current_operation: null,
    documents_processed: 0,
    documents_total: 0,
    last_updated: null
  })

  // Chat settings with proper typing
  const settings = ref<AppSettings>({
    message_display: {
      show_json: false,
      show_planning: true,
      show_debug: false,
      show_thoughts: true,
      show_utility: false,
      show_sources: true
    },
    browser_integration: {
      enabled: false,
      auto_search: false,
      auto_screenshot: false,
      show_browser_actions: true
    },
    chat: {
      auto_scroll: true
    }
  })

  // Workflow state
  const activeWorkflowId = ref<string | null>(null)
  const showWorkflowApproval = ref(false)

  // Knowledge management state
  const showKnowledgeDialog = ref(false)
  const currentChatContext = ref<any>(null)
  const chatFileAssociations = ref<Record<string, any[]>>({})

  // Command permission state
  const showCommandDialog = ref(false)
  const pendingCommand = ref({
    command: '',
    purpose: '',
    riskLevel: 'LOW' as 'LOW' | 'MEDIUM' | 'HIGH',
    originalMessage: ''
  })

  // Research browser state
  const currentResearchSession = ref<string | null>(null)
  const researchResults = ref<any>(null)

  // Computed properties
  const filteredMessages = computed(() => {
    return messages.value.filter(message => {
      if (message.type === 'thought' && !settings.value.message_display.show_thoughts) return false
      if (message.type === 'json' && !settings.value.message_display.show_json) return false
      if (message.type === 'utility' && !settings.value.message_display.show_utility) return false
      if (message.type === 'planning' && !settings.value.message_display.show_planning) return false
      if (message.type === 'debug' && !settings.value.message_display.show_debug) return false
      if (message.type === 'sources' && !settings.value.message_display.show_sources) return false
      return true
    })
  })

  // Message formatting functions
  const formatMessage = (text: string, type?: string): string => {
    const cleanedText = escapeJsonChars(text)
    const parsedContent = parseStructuredMessage(cleanedText)

    if (parsedContent.length > 0) {
      return parsedContent.map(item => formatSingleMessage(item.text, item.type)).join('')
    }

    return formatSingleMessage(cleanedText, type || 'response')
  }

  const escapeJsonChars = (text: string): string => {
    if (!text) return ''
    return text
      .replace(/\\"/g, '"')
      .replace(/\\n/g, '\n')
      .replace(/\\r/g, '\r')
      .replace(/\\t/g, '\t')
      .replace(/\\\\/g, '\\')
      .replace(/^\{|\}$/g, '')
      .replace(/^\[|\]$/g, '')
      .replace(/^"|"$/g, '')
  }

  const parseStructuredMessage = (text: string): Array<{ type: string; text: string; order: number }> => {
    const messages: Array<{ type: string; text: string; order: number }> = []

    // Parse tool output patterns
    const toolPattern = /Tool Used: ([^\n]+)[\n\s]*Output: (.*?)(?=\n\d{2}:\d{2}:\d{2}|\nTool Used:|$)/gis
    let toolMatch

    while ((toolMatch = toolPattern.exec(text)) !== null) {
      messages.push({
        type: 'tool_output',
        text: `<strong>${toolMatch[1].trim()}</strong>`,
        order: toolMatch.index
      })

      const outputContent = toolMatch[2].trim()
      if (outputContent.startsWith('{') || outputContent.startsWith("{'")) {
        try {
          let jsonContent = outputContent
          if (outputContent.startsWith("{'")) {
            jsonContent = outputContent.replace(/'/g, '"')
          }
          const parsed = JSON.parse(jsonContent)
          messages.push({
            type: 'json',
            text: JSON.stringify(parsed, null, 2),
            order: toolMatch.index + 1
          })
        } catch {
          messages.push({
            type: 'utility',
            text: outputContent,
            order: toolMatch.index + 1
          })
        }
      } else {
        messages.push({
          type: 'utility',
          text: outputContent,
          order: toolMatch.index + 1
        })
      }
    }

    return messages.sort((a, b) => a.order - b.order)
  }

  const formatSingleMessage = (text: string, type: string): string => {
    const escapedText = text.replace(/</g, '&lt;').replace(/>/g, '&gt;')

    switch (type) {
      case 'thought':
        return `<div class="thought-message">
          <div class="message-header">💭 Thoughts</div>
          <div class="message-content">${escapedText}</div>
        </div>`
      case 'planning':
        return `<div class="planning-message">
          <div class="message-header">📋 Planning</div>
          <div class="message-content">${escapedText}</div>
        </div>`
      case 'utility':
        return `<div class="utility-message">
          <div class="message-header">⚙️ Utility</div>
          <div class="message-content">${escapedText}</div>
        </div>`
      case 'debug':
        return `<div class="debug-message">
          <div class="message-header">🐛 Debug</div>
          <div class="message-content"><pre>${escapedText}</pre></div>
        </div>`
      case 'json':
        return `<div class="json-message">
          <div class="message-header">📊 JSON Output</div>
          <div class="message-content"><pre>${escapedText}</pre></div>
        </div>`
      case 'tool_output':
        return `<div class="tool-output-message">
          <div class="message-header">🔧 Tool Output</div>
          <div class="message-content">${escapedText}</div>
        </div>`
      case 'sources':
        return `<div class="source-attribution-message">
          <div class="message-header">📋 Sources</div>
          <div class="message-content">${escapedText}</div>
        </div>`
      default:
        return `<div class="regular-message">${escapedText}</div>`
    }
  }

  // Helper function to ensure sender is valid type
  const normalizeSender = (sender: string | undefined): "user" | "assistant" | "system" => {
    if (!sender) return 'system'

    // Normalize terminal-related senders to 'system'
    if (sender === 'agent_terminal' || sender === 'terminal') {
      return 'system'
    }

    if (sender === 'user' || sender === 'assistant' || sender === 'system') {
      return sender
    }

    return 'assistant' // Default fallback
  }

  // API interaction functions
  const sendMessage = async (): Promise<void> => {
    if (!inputMessage.value.trim() && attachedFiles.value.length === 0) return

    // Add user message
    let messageText = inputMessage.value
    if (attachedFiles.value.length > 0) {
      const fileNames = attachedFiles.value.map(f => f.name).join(', ')
      messageText += `\n\n📎 Attached files: ${fileNames}`
    }

    messages.value.push({
      id: generateChatId(),
      sender: 'user',
      content: messageText,
      timestamp: new Date().toISOString(),
      type: 'message'
    })

    const userInput = inputMessage.value
    const filesToUpload = [...attachedFiles.value]
    inputMessage.value = ''
    attachedFiles.value = []

    try {
      // Upload files in parallel - eliminates N+1 sequential uploads
      const uploadResults = await Promise.allSettled(
        filesToUpload.map(async (file) => {
          const result = (await apiClient.uploadFile('/api/files/upload', file)) as unknown as FileUploadResponse
          const filePath = result.path || result.filename || file.name
          await associateFileWithChat(filePath, file.name)
          return filePath
        })
      )

      // Process results and collect successful uploads
      const uploadedFilePaths: string[] = []
      uploadResults.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          uploadedFilePaths.push(result.value)
        } else {
          const file = filesToUpload[index]
          logger.error('File upload failed:', result.reason)
          messages.value.push({
            id: generateChatId(),
            sender: 'system',
            content: `📎 ❌ Failed to upload file "${file.name}": ${result.reason instanceof Error ? result.reason.message : String(result.reason)}`,
            timestamp: new Date().toISOString(),
            type: 'error'
          })
        }
      })

      // Send message to backend using the new API
      const messageData = {
        message: userInput,
        attachments: uploadedFilePaths.length > 0 ? uploadedFilePaths : undefined
      }

      const chatResponse = await apiService.sendMessage(userInput, {
        chatId: currentChatId.value || 'default',
        ...messageData
      })

      // Process response
      if (chatResponse && chatResponse.data) {
        const responseText = chatResponse.data.response || 'No response received'
        const messageType = determineMessageType(responseText)

        messages.value.push({
          id: generateChatId(),
          sender: 'assistant',
          content: responseText,
          timestamp: new Date().toISOString(),
          type: messageType
        })
      }
    } catch (error) {
      logger.error('Chat interface error:', error)
      messages.value.push({
        id: generateChatId(),
        sender: 'assistant',
        content: `Error: ${error instanceof Error ? error.message : String(error)}`,
        timestamp: new Date().toISOString(),
        type: 'error'
      })
    }

    // Auto-scroll
    nextTick(() => {
      if (chatMessages.value && settings.value.chat.auto_scroll) {
        chatMessages.value.scrollTop = chatMessages.value.scrollHeight
      }
    })
  }

  const determineMessageType = (text: string): string => {
    if (!text) return 'response'

    if (text.includes('response_text') || (text.startsWith('{') && text.includes('"status"'))) {
      return 'json'
    }

    if (text.includes('Tool Used:') && text.includes('Output:')) {
      return 'tool_output'
    }

    if (text.includes('[THOUGHT]') || text.includes('[PLANNING]') ||
        text.includes('[UTILITY]') || text.includes('[DEBUG]')) {
      return 'structured'
    }

    return 'response'
  }

  // Chat management functions
  const newChat = async (): Promise<void> => {
    try {
      const data = await apiClient.createNewChat()
      const newChatId = data.chatId || generateChatId()

      currentChatId.value = newChatId
      messages.value = []

      localStorage.setItem('lastChatId', newChatId)

      chatList.value.unshift({
        id: newChatId,
        chatId: newChatId,
        name: undefined,
        title: `Chat ${chatList.value.length + 1}`,
        messages: [],
        lastMessage: undefined,
        timestamp: new Date()
      })
    } catch (error) {
      logger.error('Error creating new chat:', error)
      const newChatId = generateChatId()
      currentChatId.value = newChatId
      messages.value = []
      localStorage.setItem('lastChatId', newChatId)
    }
  }

  const switchChat = async (chatId: string): Promise<void> => {
    currentChatId.value = chatId
    localStorage.setItem('lastChatId', chatId)
    await loadChatMessages(chatId)
    await loadChatContext(chatId)

    // Start polling for real-time message updates
    startMessagePolling(chatId)
  }

  // Cleanup on unmount
  onUnmounted(() => {
    stopMessagePolling()
  })

  // Message polling for real-time updates
  let messagePollingInterval: number | null = null
  let _lastMessageCount = 0  // Tracks count for future deduplication optimization

  const loadChatMessages = async (chatId: string, silent: boolean = false): Promise<void> => {
    try {
      const data = await apiService.getChatMessages(chatId)
      // Backend returns 'history' field with ChatMessage[]
      const history = data.data?.history || []

      // Transform backend message format to frontend format
      const newMessages = history.map((message: any) => ({
        id: message.id || generateChatId(),
        sender: normalizeSender(message.sender),
        content: message.text || message.content || '', // Backend uses 'text', frontend uses 'content'
        timestamp: message.timestamp || new Date().toISOString(),
        type: message.messageType || message.type || 'default'
      }))

      // Only update if messages changed (prevents unnecessary re-renders)
      if (newMessages.length !== messages.value.length || !silent) {
        const previousLength = messages.value.length
        messages.value = newMessages
        _lastMessageCount = newMessages.length

        // Auto-scroll only if new messages appeared
        if (newMessages.length > previousLength) {
          await nextTick()
          if (chatMessages.value && settings.value.chat.auto_scroll) {
            chatMessages.value.scrollTop = chatMessages.value.scrollHeight
          }
        }
      }
    } catch (error: any) {
      // On 401, stop polling immediately to prevent retry storm (#967)
      if (error?.response?.status === 401 || error?.status === 401) {
        stopMessagePolling()
        return
      }
      if (!silent) {
        logger.error('Error loading chat messages:', error)
        messages.value = [{
          id: generateChatId(),
          sender: 'system',
          content: 'Failed to load chat messages',
          timestamp: new Date().toISOString(),
          type: 'error'
        }]
      }
    }
  }

  const startMessagePolling = (chatId: string) => {
    // Clear any existing polling
    stopMessagePolling()

    // Poll every 2 seconds for new messages
    messagePollingInterval = window.setInterval(async () => {
      if (currentChatId.value === chatId) {
        await loadChatMessages(chatId, true) // silent=true to avoid error spam
      } else {
        // Chat switched, stop polling
        stopMessagePolling()
      }
    }, 2000)

    logger.debug(`Started message polling for chat ${chatId}`)
  }

  const stopMessagePolling = () => {
    if (messagePollingInterval) {
      clearInterval(messagePollingInterval)
      messagePollingInterval = null
      logger.debug('Stopped message polling')
    }
  }

  const loadChatContext = async (chatId: string): Promise<void> => {
    try {
      currentChatContext.value = { chatId }
    } catch (error) {
      logger.error('Failed to load chat context:', error)
    }
  }

  const associateFileWithChat = async (filePath: string, fileName: string): Promise<void> => {
    try {
      await apiService.associateFileWithChat({
        chat_id: currentChatId.value || 'default',
        file_path: filePath,
        association_type: 'upload',
        metadata: { original_filename: fileName }
      })

      if (!chatFileAssociations.value[currentChatId.value || 'default']) {
        chatFileAssociations.value[currentChatId.value || 'default'] = []
      }
      chatFileAssociations.value[currentChatId.value || 'default'].push({
        file_path: filePath,
        file_name: fileName,
        type: 'upload'
      })
    } catch (error) {
      logger.error('Failed to associate file with chat:', error)
    }
  }

  // File handling functions
  const handleFileAttachment = (event: Event): void => {
    const target = event.target as HTMLInputElement
    if (target.files) {
      const files = Array.from(target.files)
      attachedFiles.value.push(...files)
    }
  }

  const removeAttachment = (index: number): void => {
    attachedFiles.value.splice(index, 1)
  }

  const getFileIcon = (file: File): string => {
    const extension = file.name.split('.').pop()?.toLowerCase()
    const iconMap: Record<string, string> = {
      'txt': '📄', 'pdf': '📕', 'doc': '📘', 'docx': '📘',
      'md': '📝', 'json': '📊', 'xml': '📋', 'csv': '📊',
      'py': '🐍', 'js': '📜', 'html': '🌐', 'css': '🎨',
      'img': '🖼️', 'png': '🖼️', 'jpg': '🖼️', 'jpeg': '🖼️', 'gif': '🖼️'
    }
    return iconMap[extension || ''] || '📎'
  }

  // WebSocket event handlers
  const handleWebSocketEvent = (eventData: WebSocketMessage): void => {
    const eventType = eventData.type
    const payload = eventData.payload

    if (eventType === 'ping') {
      wsSend({ type: 'pong' })
      return
    }

    if (eventType === 'llm_response') {
      const response = payload as LLMResponse
      messages.value.push({
        id: generateChatId(),
        sender: normalizeSender(response.sender),
        content: response.response || response.content || 'No response content',
        timestamp: new Date().toISOString(),
        type: response.message_type || 'response'
      })

      nextTick(() => {
        if (chatMessages.value && settings.value.chat.auto_scroll) {
          chatMessages.value.scrollTop = chatMessages.value.scrollHeight
        }
      })
    }

    // Handle workflow events
    if (eventType.startsWith('workflow_')) {
      let workflowMessage = ''
      switch (eventType) {
        case 'workflow_step_started':
          workflowMessage = `🔄 Started: ${payload.description}`
          break
        case 'workflow_step_completed':
          workflowMessage = `✅ Completed: ${payload.description}`
          break
        case 'workflow_approval_required':
          activeWorkflowId.value = payload.workflow_id
          workflowMessage = `⏸️ Approval Required: ${payload.description}`
          break
        case 'workflow_completed':
          workflowMessage = `🎉 Workflow completed successfully! (${payload.total_steps} steps)`
          if (activeWorkflowId.value === payload.workflow_id) {
            activeWorkflowId.value = null
          }
          break
        case 'workflow_failed':
          workflowMessage = `❌ Workflow failed: ${payload.error}`
          if (activeWorkflowId.value === payload.workflow_id) {
            activeWorkflowId.value = null
          }
          break
      }

      if (workflowMessage) {
        messages.value.push({
          id: generateChatId(),
          sender: 'system',
          content: workflowMessage,
          timestamp: new Date().toISOString(),
          type: 'workflow'
        })

        nextTick(() => {
          if (chatMessages.value && settings.value.chat.auto_scroll) {
            chatMessages.value.scrollTop = chatMessages.value.scrollHeight
          }
        })
      }
    }
  }

  // Return composable interface
  return {
    // Reactive state
    sidebarCollapsed,
    activeTab,
    inputMessage,
    messages,
    chatList,
    currentChatId,
    attachedFiles,
    systemReloading,
    reloadNeeded,
    chatMessages,
    kbStatus,
    settings,
    activeWorkflowId,
    showWorkflowApproval,
    showKnowledgeDialog,
    currentChatContext,
    chatFileAssociations,
    showCommandDialog,
    pendingCommand,
    currentResearchSession,
    researchResults,

    // Computed
    filteredMessages,

    // WebSocket
    wsConnected,
    wsState,
    handleWebSocketEvent,

    // Methods
    formatMessage,
    sendMessage,
    newChat,
    switchChat,
    loadChatMessages,
    loadChatContext,
    handleFileAttachment,
    removeAttachment,
    getFileIcon,
    associateFileWithChat,
    determineMessageType
  }
}
