<template>
  <div ref="triggerRef" class="relative">
    <button
      :aria-expanded="open"
      aria-haspopup="true"
      :aria-label="$t('nav.moreItems')"
      :class="[
        'px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 flex items-center space-x-1',
        hasActiveItem
          ? 'bg-autobot-primary text-white'
          : 'text-autobot-text-primary hover:bg-autobot-bg-tertiary'
      ]"
      @click="toggle"
      @keydown.escape="close"
    >
      <span>{{ $t('nav.more') }}</span>
      <svg
        class="w-3 h-3 transition-transform duration-150"
        :class="open ? 'rotate-180' : ''"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 20 20"
        aria-hidden="true"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8l5 5 5-5" />
      </svg>
    </button>

    <Teleport to="body">
      <div
        v-if="open"
        ref="dropdownRef"
        :style="dropdownStyle"
        class="fixed z-50 bg-autobot-bg-secondary border border-autobot-border rounded-md shadow-lg py-1 min-w-40"
        role="menu"
        :aria-label="$t('nav.moreItems')"
        @keydown.escape="close"
      >
        <router-link
          v-for="item in items"
          :key="item.to"
          :to="item.to"
          role="menuitem"
          class="flex items-center space-x-2 px-3 py-2 text-sm transition-colors duration-150 hover:bg-autobot-bg-tertiary"
          :class="$route.path.startsWith(item.to) ? 'text-autobot-primary' : 'text-autobot-text-primary'"
          @click="close"
        >
          <svg
            class="w-4 h-4 shrink-0"
            :fill="item.iconStroke ? 'none' : 'currentColor'"
            :stroke="item.iconStroke ? 'currentColor' : undefined"
            viewBox="0 0 20 20"
            aria-hidden="true"
          >
            <template v-if="item.iconPaths">
              <path
                v-for="(p, pi) in item.iconPaths"
                :key="pi"
                :d="p"
                :fill-rule="item.iconRule"
                :clip-rule="item.iconRule"
              />
            </template>
            <path
              v-else
              :d="item.icon"
              :fill-rule="item.iconRule"
              :clip-rule="item.iconRule"
              :stroke-linecap="item.iconStroke ? 'round' : undefined"
              :stroke-linejoin="item.iconStroke ? 'round' : undefined"
              :stroke-width="item.iconStroke ? '2' : undefined"
            />
          </svg>
          <span>{{ $t(item.labelKey) }}</span>
        </router-link>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'

type SvgFillRule = 'evenodd' | 'nonzero' | 'inherit'

interface NavItem {
  to: string
  labelKey: string
  icon?: string
  iconPaths?: string[]
  iconRule?: SvgFillRule
  iconStroke?: boolean
}

const props = defineProps<{ items: NavItem[] }>()

const route = useRoute()
const open = ref(false)
const triggerRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<HTMLElement | null>(null)
const dropdownStyle = ref<Record<string, string>>({})

const hasActiveItem = computed(() =>
  props.items.some(item => route.path.startsWith(item.to))
)

function positionDropdown() {
  if (!triggerRef.value) return
  const rect = triggerRef.value.getBoundingClientRect()
  dropdownStyle.value = {
    top: `${rect.bottom + 4}px`,
    left: `${rect.left}px`,
  }
}

function toggle() {
  if (!open.value) positionDropdown()
  open.value = !open.value
}

function close() {
  open.value = false
}

function onClickOutside(event: MouseEvent) {
  const target = event.target as Node
  if (!triggerRef.value?.contains(target) && !dropdownRef.value?.contains(target)) {
    close()
  }
}

onMounted(() => document.addEventListener('click', onClickOutside, true))
onUnmounted(() => document.removeEventListener('click', onClickOutside, true))
</script>
