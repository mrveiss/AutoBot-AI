import { ref, type Ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useMCPResources')

export interface MCPResource {
  uri: string
  name: string
  description?: string
  mime_type?: string
}

export interface MCPResourcesResponse {
  success: boolean
  resources: MCPResource[]
  total: number
}

export interface MCPResourceContent {
  success: boolean
  uri: string
  content: string
  mime_type?: string
  size_bytes: number
}

export interface MCPPromptTemplate {
  name: string
  description?: string
  arguments: Array<Record<string, unknown>>
}

export interface MCPPromptsResponse {
  success: boolean
  prompts: MCPPromptTemplate[]
  total: number
}

export interface MCPPromptMessages {
  success: boolean
  name: string
  description?: string
  messages: Array<{ role: string; content: string }>
}

/**
 * Composable for MCP Resources API
 * Provides methods to list and read MCP resources from filesystem, git, and knowledge bridges
 */
export function useMCPResources() {
  const { get, post } = useApiClient()

  const resources: Ref<MCPResource[]> = ref([])
  const loading = ref(false)
  const error: Ref<string | null> = ref(null)

  /**
   * List all available MCP resources from filesystem bridge
   */
  async function listResources(): Promise<MCPResource[]> {
    loading.value = true
    error.value = null

    try {
      const response = await get<MCPResourcesResponse>('/api/filesystem/mcp/resources')

      if (response.success) {
        resources.value = response.resources
        return response.resources
      } else {
        throw new Error('Failed to fetch MCP resources')
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      logger.error('Failed to list MCP resources:', message)
      error.value = message
      return []
    } finally {
      loading.value = false
    }
  }

  /**
   * Read content of a specific MCP resource by URI
   */
  async function readResource(uri: string): Promise<MCPResourceContent | null> {
    loading.value = true
    error.value = null

    try {
      const response = await post<MCPResourceContent>('/api/filesystem/mcp/resources/read', {
        uri
      })

      if (response.success) {
        return response
      } else {
        throw new Error('Failed to read MCP resource')
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      logger.error('Failed to read MCP resource:', message)
      error.value = message
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * List all available MCP prompt templates
   */
  async function listPromptTemplates(): Promise<MCPPromptTemplate[]> {
    loading.value = true
    error.value = null

    try {
      const response = await get<MCPPromptsResponse>('/api/filesystem/mcp/prompts')

      if (response.success) {
        return response.prompts
      } else {
        throw new Error('Failed to fetch MCP prompt templates')
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      logger.error('Failed to list MCP prompt templates:', message)
      error.value = message
      return []
    } finally {
      loading.value = false
    }
  }

  /**
   * Get a specific prompt template with arguments filled in
   */
  async function getPromptTemplate(
    name: string,
    args: Record<string, string>
  ): Promise<MCPPromptMessages | null> {
    loading.value = true
    error.value = null

    try {
      const response = await post<MCPPromptMessages>('/api/filesystem/mcp/prompts/get', {
        name,
        arguments: args
      })

      if (response.success) {
        return response
      } else {
        throw new Error('Failed to get MCP prompt template')
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      logger.error('Failed to get MCP prompt template:', message)
      error.value = message
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    resources,
    loading,
    error,
    listResources,
    readResource,
    listPromptTemplates,
    getPromptTemplate
  }
}
