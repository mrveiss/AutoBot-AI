// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, type Ref } from 'vue'

/** A single completion candidate. */
export interface CompletionItem {
  value: string
  type: 'command' | 'path' | 'history' | 'argument'
  description?: string
}

/** Options for the composable. */
export interface TabCompletionOptions {
  /** Extra commands to register beyond builtins. */
  extraCommands?: CompletionItem[]
  /** Command history array (reactive) for history-based suggestions. */
  commandHistory?: Ref<string[]>
}

/** Return type for the composable. */
export interface UseTabCompletionReturn {
  /** Visible suggestion list (empty when hidden). */
  suggestions: Ref<CompletionItem[]>
  /** Currently highlighted index (-1 = none). */
  selectedIndex: Ref<number>
  /** Whether the suggestion dropdown is visible. */
  isVisible: Ref<boolean>
  /** Call on Tab press. Returns new input string or null if no match. */
  complete: (input: string, cursorPos: number) => string | null
  /** Accept the currently selected suggestion. Returns new input. */
  acceptSelected: (input: string) => string | null
  /** Move selection up. */
  selectPrev: () => void
  /** Move selection down. */
  selectNext: () => void
  /** Hide the dropdown. */
  dismiss: () => void
  /** Register additional completions dynamically. */
  registerCommands: (cmds: CompletionItem[]) => void
}

/** Builtin slash-commands available in the terminal. */
const BUILTIN_COMMANDS: CompletionItem[] = [
  { value: '/help', type: 'command', description: 'Show available commands' },
  { value: '/clear', type: 'command', description: 'Clear terminal output' },
  { value: '/status', type: 'command', description: 'Show connection status' },
  { value: '/reconnect', type: 'command', description: 'Reconnect to terminal' },
  { value: '/history', type: 'command', description: 'Show command history' },
  { value: '/exit', type: 'command', description: 'Close terminal session' },
  { value: '/sessions', type: 'command', description: 'List active sessions' },
  { value: '/theme', type: 'command', description: 'Change terminal theme' },
  { value: '/export', type: 'command', description: 'Export terminal log' },
]

/** Common shell commands for general completion. */
const SHELL_COMMANDS: CompletionItem[] = [
  { value: 'ls', type: 'command', description: 'List directory contents' },
  { value: 'cd', type: 'command', description: 'Change directory' },
  { value: 'pwd', type: 'command', description: 'Print working directory' },
  { value: 'cat', type: 'command', description: 'Print file contents' },
  { value: 'grep', type: 'command', description: 'Search text patterns' },
  { value: 'find', type: 'command', description: 'Find files' },
  { value: 'echo', type: 'command', description: 'Print text' },
  { value: 'mkdir', type: 'command', description: 'Create directory' },
  { value: 'rm', type: 'command', description: 'Remove files' },
  { value: 'cp', type: 'command', description: 'Copy files' },
  { value: 'mv', type: 'command', description: 'Move files' },
  { value: 'chmod', type: 'command', description: 'Change permissions' },
  { value: 'chown', type: 'command', description: 'Change ownership' },
  { value: 'tail', type: 'command', description: 'View file tail' },
  { value: 'head', type: 'command', description: 'View file head' },
  { value: 'less', type: 'command', description: 'Page through file' },
  { value: 'top', type: 'command', description: 'Process monitor' },
  { value: 'htop', type: 'command', description: 'Interactive process viewer' },
  { value: 'ps', type: 'command', description: 'List processes' },
  { value: 'kill', type: 'command', description: 'Send signal to process' },
  { value: 'ssh', type: 'command', description: 'Secure shell' },
  { value: 'scp', type: 'command', description: 'Secure copy' },
  { value: 'rsync', type: 'command', description: 'Remote sync' },
  { value: 'curl', type: 'command', description: 'Transfer data from URL' },
  { value: 'wget', type: 'command', description: 'Download files' },
  { value: 'tar', type: 'command', description: 'Archive utility' },
  { value: 'git', type: 'command', description: 'Version control' },
  { value: 'docker', type: 'command', description: 'Container management' },
  { value: 'systemctl', type: 'command', description: 'Service management' },
  { value: 'journalctl', type: 'command', description: 'View system logs' },
  { value: 'apt', type: 'command', description: 'Package manager' },
  { value: 'pip', type: 'command', description: 'Python package manager' },
  { value: 'python3', type: 'command', description: 'Python interpreter' },
  { value: 'node', type: 'command', description: 'Node.js runtime' },
  { value: 'npm', type: 'command', description: 'Node package manager' },
]

/**
 * Find the longest common prefix among an array of strings.
 *
 * Helper for useTabCompletion (#503).
 */
function longestCommonPrefix(strings: string[]): string {
  if (strings.length === 0) return ''
  if (strings.length === 1) return strings[0]

  let prefix = strings[0]
  for (let i = 1; i < strings.length; i++) {
    while (!strings[i].startsWith(prefix)) {
      prefix = prefix.slice(0, -1)
      if (prefix === '') return ''
    }
  }
  return prefix
}

/**
 * Extract the word being completed at the cursor position.
 *
 * Helper for useTabCompletion (#503).
 */
function extractWordAtCursor(
  input: string,
  cursorPos: number,
): { word: string; start: number } {
  const beforeCursor = input.slice(0, cursorPos)
  const lastSpaceIdx = beforeCursor.lastIndexOf(' ')
  const start = lastSpaceIdx + 1
  return { word: beforeCursor.slice(start), start }
}

/**
 * Composable that provides tab-completion logic for terminal input.
 * Handles local command matching, history suggestions, and cycling.
 *
 * Issue #503 / #634.
 */
export function useTabCompletion(
  options: TabCompletionOptions = {},
): UseTabCompletionReturn {
  const suggestions: Ref<CompletionItem[]> = ref([])
  const selectedIndex: Ref<number> = ref(-1)
  const isVisible: Ref<boolean> = ref(false)

  let registeredCommands: CompletionItem[] = [
    ...BUILTIN_COMMANDS,
    ...SHELL_COMMANDS,
    ...(options.extraCommands || []),
  ]

  // Track last completion for Tab-cycling
  let lastCompletionInput = ''
  let lastCycleIndex = -1

  const registerCommands = (cmds: CompletionItem[]): void => {
    registeredCommands = [...registeredCommands, ...cmds]
  }

  const dismiss = (): void => {
    suggestions.value = []
    selectedIndex.value = -1
    isVisible.value = false
    lastCompletionInput = ''
    lastCycleIndex = -1
  }

  const selectNext = (): void => {
    if (suggestions.value.length === 0) return
    selectedIndex.value =
      (selectedIndex.value + 1) % suggestions.value.length
  }

  const selectPrev = (): void => {
    if (suggestions.value.length === 0) return
    selectedIndex.value =
      selectedIndex.value <= 0
        ? suggestions.value.length - 1
        : selectedIndex.value - 1
  }

  /**
   * Build replacement string from selected suggestion.
   *
   * Helper for useTabCompletion (#503).
   */
  const buildReplacement = (
    input: string,
    wordStart: number,
    replacement: string,
  ): string => {
    const before = input.slice(0, wordStart)
    const afterCursor = input.slice(
      wordStart + extractWordAtCursor(input, input.length).word.length,
    )
    return before + replacement + afterCursor
  }

  const acceptSelected = (input: string): string | null => {
    if (
      selectedIndex.value < 0 ||
      selectedIndex.value >= suggestions.value.length
    ) {
      return null
    }
    const item = suggestions.value[selectedIndex.value]
    const { start } = extractWordAtCursor(input, input.length)
    const result = buildReplacement(input, start, item.value)
    dismiss()
    return result
  }

  const complete = (input: string, cursorPos: number): string | null => {
    if (!input.trim()) {
      dismiss()
      return null
    }

    const { word, start } = extractWordAtCursor(input, cursorPos)
    if (!word) {
      dismiss()
      return null
    }

    const isFirstWord = start === 0
    const lowerWord = word.toLowerCase()

    // Collect matching candidates
    let candidates: CompletionItem[] = []

    if (isFirstWord) {
      // Command position: match against registered commands
      candidates = registeredCommands.filter((cmd) =>
        cmd.value.toLowerCase().startsWith(lowerWord),
      )
    } else {
      // Argument position: match history-based tokens
      candidates = getHistoryTokens(lowerWord)
    }

    // Add history-based command matches regardless of position
    if (options.commandHistory?.value) {
      const historyMatches = options.commandHistory.value
        .filter(
          (h) =>
            h.toLowerCase().startsWith(lowerWord) && h !== input,
        )
        .slice(-5)
        .map((h) => ({
          value: h,
          type: 'history' as const,
          description: 'From history',
        }))
      // Add history matches that aren't already in candidates
      const existingValues = new Set(candidates.map((c) => c.value))
      for (const hm of historyMatches) {
        if (!existingValues.has(hm.value)) {
          candidates.push(hm)
        }
      }
    }

    if (candidates.length === 0) {
      dismiss()
      return null
    }

    // Tab-cycling: if same input pressed Tab again, cycle
    if (input === lastCompletionInput && candidates.length > 1) {
      lastCycleIndex = (lastCycleIndex + 1) % candidates.length
      const replacement = candidates[lastCycleIndex].value
      suggestions.value = candidates
      selectedIndex.value = lastCycleIndex
      isVisible.value = true

      if (isFirstWord) {
        return replacement
      }
      return buildReplacement(input, start, replacement)
    }

    // Reset cycling state
    lastCompletionInput = input
    lastCycleIndex = 0

    if (candidates.length === 1) {
      // Single match: auto-complete and add trailing space
      const single = candidates[0].value
      dismiss()
      if (isFirstWord) {
        return single + ' '
      }
      return buildReplacement(input, start, single) + ' '
    }

    // Multiple matches: complete common prefix + show suggestions
    const values = candidates.map((c) => c.value)
    const common = longestCommonPrefix(values)

    suggestions.value = candidates
    selectedIndex.value = 0
    isVisible.value = true

    if (common.length > word.length) {
      // Extend to common prefix
      if (isFirstWord) {
        return common
      }
      return buildReplacement(input, start, common)
    }

    // Already at common prefix, just show dropdown
    return null
  }

  /**
   * Get completion items from unique tokens in history.
   *
   * Helper for useTabCompletion (#503).
   */
  function getHistoryTokens(prefix: string): CompletionItem[] {
    if (!options.commandHistory?.value) return []

    const tokens = new Set<string>()
    for (const cmd of options.commandHistory.value) {
      for (const token of cmd.split(/\s+/)) {
        if (
          token.toLowerCase().startsWith(prefix) &&
          token.length > prefix.length
        ) {
          tokens.add(token)
        }
      }
    }

    return Array.from(tokens)
      .slice(0, 10)
      .map((t) => ({
        value: t,
        type: 'history' as const,
        description: 'From history',
      }))
  }

  return {
    suggestions,
    selectedIndex,
    isVisible,
    complete,
    acceptSelected,
    selectPrev,
    selectNext,
    dismiss,
    registerCommands,
  }
}
