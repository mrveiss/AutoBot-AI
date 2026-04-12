<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition ease-out duration-100"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition ease-in duration-100"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="isOpen"
        @click="closeModal"
        class="fixed inset-0 z-50 bg-black/50 overflow-y-auto"
      >
        <!-- Prevent close when clicking inside the palette -->
        <div class="flex items-start justify-center min-h-screen pt-16" @click.stop>
          <div
            @click.stop
            @keydown.escape="closeModal"
            class="w-full max-w-2xl bg-autobot-bg-card rounded-lg shadow-2xl border border-autobot-border overflow-hidden"
          >
            <!-- Search Input -->
            <div class="p-4 border-b border-autobot-border">
              <input
                ref="searchInput"
                v-model="searchQuery"
                type="text"
                :placeholder="$t('commands.search', 'Search commands...')"
                class="w-full px-4 py-3 bg-autobot-bg-secondary text-autobot-text-primary rounded-lg border border-autobot-border focus:outline-hidden focus:ring-2 focus:ring-autobot-primary placeholder-autobot-text-muted"
                @keydown.arrow-down="moveDown"
                @keydown.arrow-up="moveUp"
                @keydown.enter="executeCommand"
              />
            </div>

            <!-- Commands List -->
            <div class="max-h-96 overflow-y-auto">
              <div v-if="filteredCommands.length === 0" class="p-8 text-center">
                <p class="text-autobot-text-muted">{{ $t('commands.noResults', 'No commands found') }}</p>
              </div>

              <div v-else class="py-2">
                <div
                  v-for="(command, index) in filteredCommands"
                  :key="command.id"
                  @click="selectCommand(index)"
                  @mouseenter="selectedIndex = index"
                  :class="{
                    'bg-autobot-primary/10': selectedIndex === index
                  }"
                  class="px-4 py-3 border-l-4 transition-colors cursor-pointer hover:bg-autobot-primary/5"
                  :style="{ borderLeftColor: getAgentColor(command.type) }"
                >
                  <div class="flex items-center gap-3">
                    <!-- Agent Avatar -->
                    <div
                      class="w-10 h-10 rounded-lg flex items-center justify-center text-lg shrink-0"
                      :style="{ backgroundColor: getAgentColor(command.type) + '20' }"
                    >
                      {{ getAgentEmoji(command.type) }}
                    </div>

                    <!-- Command Info -->
                    <div class="flex-1 min-w-0">
                      <div class="flex items-center gap-2 mb-1">
                        <p class="font-medium text-autobot-text-primary">{{ command.label }}</p>
                        <span
                          class="px-2 py-0.5 text-xs font-medium rounded-full"
                          :style="{ backgroundColor: getAgentColor(command.type) + '30', color: getAgentColor(command.type) }"
                        >
                          {{ command.type }}
                        </span>
                      </div>
                      <p class="text-sm text-autobot-text-secondary line-clamp-1">{{ command.description }}</p>
                    </div>

                    <!-- Keyboard Shortcut -->
                    <div class="ml-4 shrink-0">
                      <kbd class="px-2 py-1 text-xs rounded border border-autobot-border bg-autobot-bg-secondary text-autobot-text-muted">
                        {{ getShortcutText(command) }}
                      </kbd>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Footer with hints -->
            <div class="p-3 border-t border-autobot-border bg-autobot-bg-secondary text-xs text-autobot-text-muted flex items-center justify-between">
              <div class="flex gap-4">
                <span><kbd class="px-1 border border-autobot-border rounded">↑↓</kbd> navigate</span>
                <span><kbd class="px-1 border border-autobot-border rounded">↵</kbd> select</span>
                <span><kbd class="px-1 border border-autobot-border rounded">esc</kbd> close</span>
              </div>
              <span>{{ selectedIndex + 1 }} / {{ filteredCommands.length }}</span>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/useChatStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CommandPalette')
const { t } = useI18n()

interface Command {
  id: string
  label: string
  description: string
  type: 'task' | 'research' | 'code' | 'analysis'
  action: () => void
  shortcut?: string
}

const isOpen = ref(false)
const searchQuery = ref('')
const selectedIndex = ref(0)
const searchInput = ref<HTMLInputElement | null>(null)

const chatStore = useChatStore()

const commands = computed<Command[]>(() => [
  {
    id: 'new-task',
    label: t('commands.newTask', 'New Task'),
    description: t('commands.newTaskDesc', 'Create a new task agent'),
    type: 'task',
    action: () => startAgent('task'),
    shortcut: 'Cmd+T'
  },
  {
    id: 'new-research',
    label: t('commands.newResearch', 'New Research'),
    description: t('commands.newResearchDesc', 'Start a research session'),
    type: 'research',
    action: () => startAgent('research'),
    shortcut: 'Cmd+R'
  },
  {
    id: 'new-code',
    label: t('commands.newCode', 'New Code Agent'),
    description: t('commands.newCodeDesc', 'Start a code analysis session'),
    type: 'code',
    action: () => startAgent('code'),
    shortcut: 'Cmd+C'
  },
  {
    id: 'new-analysis',
    label: t('commands.newAnalysis', 'New Analysis'),
    description: t('commands.newAnalysisDesc', 'Start an analysis session'),
    type: 'analysis',
    action: () => startAgent('analysis'),
    shortcut: 'Cmd+A'
  }
])

const filteredCommands = computed<Command[]>(() => {
  if (!searchQuery.value.trim()) {
    return commands.value
  }

  const query = searchQuery.value.toLowerCase()
  return commands.value.filter(cmd =>
    cmd.label.toLowerCase().includes(query) ||
    cmd.description.toLowerCase().includes(query) ||
    cmd.type.toLowerCase().includes(query)
  )
})

const getAgentColor = (type: string): string => {
  const colors: Record<string, string> = {
    task: '#3b82f6',      // blue
    research: '#8b5cf6',  // purple
    code: '#10b981',      // green
    analysis: '#f59e0b'   // amber
  }
  return colors[type] || '#6b7280'
}

const getAgentEmoji = (type: string): string => {
  const emojis: Record<string, string> = {
    task: '✓',
    research: '🔍',
    code: '</',
    analysis: '📊'
  }
  return emojis[type] || '◆'
}

const getShortcutText = (command: Command): string => {
  if (!command.shortcut) return 'Enter'
  // Show OS-specific shortcut
  const isMac = /Mac/.test(navigator.platform)
  return command.shortcut.replace('Cmd', isMac ? '⌘' : 'Ctrl')
}

const open = (): void => {
  isOpen.value = true
  selectedIndex.value = 0
  searchQuery.value = ''
  nextTick(() => {
    searchInput.value?.focus()
  })
}

const closeModal = (): void => {
  isOpen.value = false
  searchQuery.value = ''
  selectedIndex.value = 0
}

const moveUp = (): void => {
  if (selectedIndex.value > 0) {
    selectedIndex.value--
  }
}

const moveDown = (): void => {
  if (selectedIndex.value < filteredCommands.value.length - 1) {
    selectedIndex.value++
  }
}

const selectCommand = (index: number): void => {
  selectedIndex.value = index
}

const executeCommand = (): void => {
  if (filteredCommands.value.length === 0) return

  const command = filteredCommands.value[selectedIndex.value]
  if (command) {
    logger.debug('Executing command:', command.id)
    command.action()
    closeModal()
  }
}

const startAgent = (type: string): void => {
  logger.debug('Starting agent:', type)
  // Store agent metadata for personality display
  chatStore.setCurrentAgentType(type)
}

watch(searchQuery, () => {
  selectedIndex.value = 0
})

defineExpose({
  open,
  close: closeModal
})
</script>

<style scoped>
::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--autobot-border);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--autobot-text-muted);
}
</style>
