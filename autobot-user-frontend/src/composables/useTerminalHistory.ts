// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useTerminalHistory Composable
 *
 * Provides terminal command history navigation and persistence functionality.
 * Supports Up/Down arrow key navigation and Ctrl+R reverse search.
 *
 * Features:
 * - Navigate through command history with Up/Down arrows
 * - Sync history with backend via WebSocket
 * - Ctrl+R reverse incremental search
 * - Per-session history tracking
 * - Automatic cleanup on unmount
 *
 * Usage:
 * ```typescript
 * import { useTerminalHistory } from '@/composables/useTerminalHistory'
 *
 * const {
 *   history,
 *   historyIndex,
 *   navigateHistory,
 *   resetHistoryIndex,
 *   syncHistory
 * } = useTerminalHistory(sessionId)
 *
 * // Navigate to previous command
 * const previousCmd = navigateHistory('up')
 *
 * // Navigate to next command
 * const nextCmd = navigateHistory('down')
 * ```
 */

import { ref, onUnmounted, computed } from 'vue'
import terminalService from '@/services/TerminalService.js'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useTerminalHistory')

/**
 * Terminal history composable for command history navigation
 *
 * @param sessionId - The terminal session ID to track history for
 * @returns History state and navigation methods
 */
export function useTerminalHistory(sessionId: string) {
  // History state
  const history = ref<string[]>([])
  const historyIndex = ref(-1)

  // Reverse search state
  const searchMode = ref(false)
  const searchQuery = ref('')
  const searchMatches = ref<string[]>([])
  const searchMatchIndex = ref(-1)

  // Computed: current history command based on index
  const currentHistoryCommand = computed(() => {
    if (historyIndex.value < 0 || historyIndex.value >= history.value.length) {
      return ''
    }
    return history.value[history.value.length - 1 - historyIndex.value]
  })

  /**
   * Sync history from backend via WebSocket
   * Requests history list from the server
   */
  const syncHistory = (): void => {
    if (!sessionId) {
      logger.warn('[HISTORY] Cannot sync history: no session ID')
      return
    }

    logger.debug('[HISTORY] Requesting history sync for session', { sessionId })
    terminalService.sendHistoryGet(sessionId)
  }

  /**
   * Navigate through command history
   *
   * @param direction - 'up' for previous command, 'down' for next command
   * @returns The command at the new history index, or empty string if at prompt
   */
  const navigateHistory = (direction: 'up' | 'down'): string => {
    if (history.value.length === 0) {
      logger.debug('[HISTORY] No history to navigate')
      return ''
    }

    if (direction === 'up') {
      // Move to older command (increase index)
      if (historyIndex.value < history.value.length - 1) {
        historyIndex.value++
        logger.debug('[HISTORY] Navigate up', { index: historyIndex.value })
      }
    } else {
      // Move to newer command (decrease index)
      if (historyIndex.value > -1) {
        historyIndex.value--
        logger.debug('[HISTORY] Navigate down', { index: historyIndex.value })
      }
    }

    // Return empty string if at prompt position (-1)
    if (historyIndex.value === -1) {
      return ''
    }

    // Return command from history (reversed: newest at end, oldest at start)
    const commandIndex = history.value.length - 1 - historyIndex.value
    return history.value[commandIndex] || ''
  }

  /**
   * Reset history navigation index to prompt position
   * Called after command execution or when starting fresh input
   */
  const resetHistoryIndex = (): void => {
    historyIndex.value = -1
    logger.debug('[HISTORY] Reset history index')
  }

  /**
   * Set the history array with commands from backend
   *
   * @param commands - Array of commands to set as history
   */
  const setHistory = (commands: string[]): void => {
    history.value = commands
    historyIndex.value = -1
    logger.debug('[HISTORY] Set history', { count: commands.length })
  }

  /**
   * Add a command to local history
   *
   * @param command - Command to add
   */
  const addToHistory = (command: string): void => {
    if (!command.trim()) {
      return
    }

    // Avoid duplicates - don't add if same as last command
    const lastCommand = history.value[history.value.length - 1]
    if (lastCommand !== command) {
      history.value.push(command)
      logger.debug('[HISTORY] Added command to history', { command })
    }

    // Limit local history size
    if (history.value.length > 1000) {
      history.value = history.value.slice(-1000)
    }

    // Reset index when adding new command
    resetHistoryIndex()
  }

  /**
   * Enter reverse search mode (Ctrl+R)
   */
  const enterSearchMode = (): void => {
    searchMode.value = true
    searchQuery.value = ''
    searchMatches.value = []
    searchMatchIndex.value = -1
    logger.debug('[HISTORY] Entered reverse search mode')
  }

  /**
   * Exit reverse search mode
   */
  const exitSearchMode = (): void => {
    searchMode.value = false
    searchQuery.value = ''
    searchMatches.value = []
    searchMatchIndex.value = -1
    logger.debug('[HISTORY] Exited reverse search mode')
  }

  /**
   * Perform reverse search through history
   *
   * @param query - Search query string
   * @returns Matching commands array
   */
  const reverseSearch = (query: string): string[] => {
    searchQuery.value = query

    if (!query) {
      searchMatches.value = []
      searchMatchIndex.value = -1
      return []
    }

    // Search history from newest to oldest
    const matches: string[] = []
    for (let i = history.value.length - 1; i >= 0; i--) {
      if (history.value[i].includes(query)) {
        matches.push(history.value[i])
      }
    }

    searchMatches.value = matches
    searchMatchIndex.value = matches.length > 0 ? 0 : -1

    logger.debug('[HISTORY] Reverse search', { query, foundCount: matches.length })
    return matches
  }

  /**
   * Navigate through search matches
   *
   * @param direction - 'up' for older match, 'down' for newer match
   * @returns The match at the new index, or empty string
   */
  const navigateSearchMatches = (direction: 'up' | 'down'): string => {
    if (searchMatches.value.length === 0) {
      return ''
    }

    if (direction === 'up') {
      if (searchMatchIndex.value < searchMatches.value.length - 1) {
        searchMatchIndex.value++
      }
    } else {
      if (searchMatchIndex.value > 0) {
        searchMatchIndex.value--
      }
    }

    return searchMatches.value[searchMatchIndex.value] || ''
  }

  /**
   * Get current search match
   *
   * @returns Current search match or empty string
   */
  const getCurrentSearchMatch = (): string => {
    if (searchMatchIndex.value < 0 || searchMatchIndex.value >= searchMatches.value.length) {
      return ''
    }
    return searchMatches.value[searchMatchIndex.value]
  }

  /**
   * Handle history response from backend
   *
   * @param data - History data from backend
   */
  const handleHistoryResponse = (data: { commands: string[] }): void => {
    setHistory(data.commands || [])
    logger.debug('[HISTORY] Received history from backend', { count: data.commands?.length || 0 })
  }

  /**
   * Handle history search response from backend
   *
   * @param data - Search results from backend
   */
  const handleHistorySearchResponse = (data: { matches: string[]; query: string }): void => {
    searchMatches.value = data.matches || []
    searchQuery.value = data.query || ''
    searchMatchIndex.value = searchMatches.value.length > 0 ? 0 : -1
    logger.debug('[HISTORY] Received search results', { matchCount: searchMatches.value.length })
  }

  // Cleanup on unmount
  onUnmounted(() => {
    history.value = []
    historyIndex.value = -1
    exitSearchMode()
  })

  return {
    // State
    history,
    historyIndex,
    searchMode,
    searchQuery,
    searchMatches,
    searchMatchIndex,

    // Computed
    currentHistoryCommand,

    // Methods
    syncHistory,
    navigateHistory,
    resetHistoryIndex,
    setHistory,
    addToHistory,
    enterSearchMode,
    exitSearchMode,
    reverseSearch,
    navigateSearchMatches,
    getCurrentSearchMatch,
    handleHistoryResponse,
    handleHistorySearchResponse
  }
}
