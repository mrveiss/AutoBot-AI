// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * InteractiveScreenshot — Shared interactive browser screenshot component (#1416)
 *
 * Renders a browser screenshot with click/scroll/type/hover interaction.
 * Used by both VisualBrowserPanel (chat) and KnowledgeResearchPanel (knowledge).
 *
 * Emits @interact({ action, params }) for the parent to proxy to the backend.
 */

import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

interface Props {
  screenshot: string | null
  loading?: boolean
  interactive?: boolean
  viewportWidth?: number
  viewportHeight?: number
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  interactive: true,
  viewportWidth: 1280,
  viewportHeight: 720,
})

const emit = defineEmits<{
  interact: [payload: { action: string; params: Record<string, unknown> }]
}>()

const showTypeOverlay = ref(false)
const typeText = ref('')
const imgRef = ref<HTMLImageElement | null>(null)

const screenshotSrc = computed(() =>
  props.screenshot ? `data:image/png;base64,${props.screenshot}` : null
)

function mapCoordinates(event: MouseEvent): { x: number; y: number } | null {
  const img = imgRef.value
  if (!img) return null
  const rect = img.getBoundingClientRect()
  const clickX = event.clientX - rect.left
  const clickY = event.clientY - rect.top
  return {
    x: (clickX / rect.width) * props.viewportWidth,
    y: (clickY / rect.height) * props.viewportHeight,
  }
}

function handleClick(event: MouseEvent) {
  if (!props.interactive || props.loading) return
  const coords = mapCoordinates(event)
  if (coords) {
    emit('interact', { action: 'click', params: coords })
  }
}

let scrollTimer: ReturnType<typeof setTimeout> | null = null

function handleWheel(event: WheelEvent) {
  if (!props.interactive || props.loading) return
  event.preventDefault()
  if (scrollTimer) clearTimeout(scrollTimer)
  scrollTimer = setTimeout(() => {
    emit('interact', {
      action: 'scroll',
      params: { deltaX: 0, deltaY: event.deltaY > 0 ? 300 : -300 },
    })
  }, 100)
}

function scrollBy(deltaY: number) {
  if (!props.interactive || props.loading) return
  emit('interact', { action: 'scroll', params: { deltaX: 0, deltaY } })
}

function submitType() {
  if (!typeText.value.trim()) return
  emit('interact', { action: 'type', params: { text: typeText.value } })
  typeText.value = ''
  showTypeOverlay.value = false
}
</script>

<template>
  <div class="interactive-screenshot" :class="{ 'interactive-screenshot--active': interactive }">
    <!-- Screenshot image -->
    <div v-if="screenshotSrc" class="screenshot-wrapper" @wheel.prevent="handleWheel">
      <img
        ref="imgRef"
        :src="screenshotSrc"
        :alt="t('browser.interactive.screenshotAlt')"
        class="screenshot-img"
        :class="{ 'screenshot-img--loading': loading, 'screenshot-img--clickable': interactive }"
        @click="handleClick"
      />
      <div v-if="loading" class="loading-overlay">
        <div class="loading-spinner" />
      </div>
    </div>

    <!-- No screenshot placeholder -->
    <div v-else class="no-screenshot">
      <p>{{ t('browser.interactive.noScreenshot') }}</p>
    </div>

    <!-- Scroll + Type toolbar -->
    <div v-if="interactive && screenshotSrc" class="toolbar">
      <button
        class="toolbar-btn"
        :disabled="loading"
        :title="t('browser.interactive.scrollUp')"
        @click="scrollBy(-300)"
      >
        <i class="fas fa-chevron-up" />
      </button>
      <button
        class="toolbar-btn"
        :disabled="loading"
        :title="t('browser.interactive.scrollDown')"
        @click="scrollBy(300)"
      >
        <i class="fas fa-chevron-down" />
      </button>
      <button
        class="toolbar-btn"
        :disabled="loading"
        :title="t('browser.interactive.pageUp')"
        @click="scrollBy(-720)"
      >
        <i class="fas fa-angles-up" />
      </button>
      <button
        class="toolbar-btn"
        :disabled="loading"
        :title="t('browser.interactive.pageDown')"
        @click="scrollBy(720)"
      >
        <i class="fas fa-angles-down" />
      </button>
      <button
        class="toolbar-btn"
        :disabled="loading"
        :title="t('browser.interactive.typeLabel')"
        @click="showTypeOverlay = !showTypeOverlay"
      >
        <i class="fas fa-keyboard" />
      </button>
    </div>

    <!-- Type overlay -->
    <div v-if="showTypeOverlay" class="type-overlay">
      <input
        v-model="typeText"
        class="type-input"
        :placeholder="t('browser.interactive.typePlaceholder')"
        @keydown.enter="submitType"
        @keydown.escape="showTypeOverlay = false"
      />
      <button class="type-submit" @click="submitType">
        <i class="fas fa-paper-plane" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.interactive-screenshot {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

.screenshot-wrapper {
  position: relative;
  flex: 1;
  overflow: hidden;
}

.screenshot-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  transition: opacity 0.2s ease;
}

.screenshot-img--loading {
  opacity: 0.6;
}

.screenshot-img--clickable {
  cursor: crosshair;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.15);
  pointer-events: none;
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(255, 255, 255, 0.3);
  border-top-color: var(--color-primary, #3b82f6);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.no-screenshot {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-muted, #9ca3af);
  font-size: 0.875rem;
}

.toolbar {
  display: flex;
  gap: 4px;
  padding: 4px 8px;
  background: var(--color-surface, #1e1e2e);
  border-top: 1px solid var(--color-border, #333);
}

.toolbar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-secondary, #a1a1aa);
  cursor: pointer;
  font-size: 0.75rem;
  transition: background 0.15s, color 0.15s;
}

.toolbar-btn:hover:not(:disabled) {
  background: var(--color-hover, rgba(255, 255, 255, 0.1));
  color: var(--color-text, #e4e4e7);
}

.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.type-overlay {
  display: flex;
  gap: 4px;
  padding: 4px 8px;
  background: var(--color-surface, #1e1e2e);
  border-top: 1px solid var(--color-border, #333);
}

.type-input {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid var(--color-border, #333);
  border-radius: 4px;
  background: var(--color-bg, #121212);
  color: var(--color-text, #e4e4e7);
  font-size: 0.8rem;
  outline: none;
}

.type-input:focus {
  border-color: var(--color-primary, #3b82f6);
}

.type-submit {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 4px;
  background: var(--color-primary, #3b82f6);
  color: white;
  cursor: pointer;
  font-size: 0.75rem;
}
</style>
