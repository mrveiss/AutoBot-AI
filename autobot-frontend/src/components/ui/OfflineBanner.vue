<template>
  <!-- Offline mode banner — shown when network is unavailable (#3275) -->
  <Transition
    enter-active-class="transition duration-300 ease-out"
    enter-from-class="-translate-y-full opacity-0"
    enter-to-class="translate-y-0 opacity-100"
    leave-active-class="transition duration-200 ease-in"
    leave-from-class="translate-y-0 opacity-100"
    leave-to-class="-translate-y-full opacity-0"
  >
    <div
      v-if="!isOnline"
      role="alert"
      aria-live="assertive"
      class="w-full bg-amber-500 text-amber-950 px-4 py-2 flex items-center justify-between text-sm font-medium z-50"
    >
      <div class="flex items-center gap-2">
        <!-- Offline icon -->
        <svg
          class="w-4 h-4 shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M18.364 5.636a9 9 0 010 12.728M15.536 8.464a5 5 0 010 7.072M12 12h.01M3 3l18 18"
          />
        </svg>
        <span>
          Offline mode — local Ollama inference and knowledge base are available.
          Web research and cloud LLMs are disabled.
          <span v-if="pendingCount > 0">
            {{ pendingCount }} action{{ pendingCount === 1 ? '' : 's' }} queued for retry.
          </span>
        </span>
      </div>
      <button
        class="ml-4 shrink-0 underline hover:no-underline focus:outline-none focus:ring-2 focus:ring-amber-950/50 rounded"
        @click="retryNow"
        :disabled="isChecking"
      >
        {{ isChecking ? 'Checking…' : 'Retry' }}
      </button>
    </div>
  </Transition>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { useNetworkStatus } from '@/composables/useNetworkStatus'
import { useActionQueue } from '@/composables/useActionQueue'

const { isOnline, isChecking } = useNetworkStatus()
const { queue } = useActionQueue()

const pendingCount = computed(() => queue.value.length)

function retryNow(): void {
  // Trigger a page-level connectivity re-check by loading a tiny resource.
  // The useNetworkStatus probe loop handles the state update automatically.
  const img = new Image()
  img.src = `/favicon.ico?_nc=${Date.now()}`
}
</script>
