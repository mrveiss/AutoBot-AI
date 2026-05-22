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

import Icon from '@/components/ui/Icon.vue'
import { ref, computed, toRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  useRegionMarking,
  type PageRegion,
  type SelectedRegion,
} from '@/composables/browser/useRegionMarking'

const { t } = useI18n()

interface Props {
  screenshot: string | null
  loading?: boolean
  interactive?: boolean
  viewportWidth?: number
  viewportHeight?: number
  regions?: PageRegion[]
  markRegionsMode?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  interactive: true,
  viewportWidth: 1280,
  viewportHeight: 720,
  regions: () => [],
  markRegionsMode: false,
})

const emit = defineEmits<{
  interact: [payload: { action: string; params: Record<string, unknown> }]
  regionsSelected: [regions: SelectedRegion[]]
}>()

const showTypeOverlay = ref(false)
const typeText = ref('')
const imgRef = ref<HTMLImageElement | null>(null)

// Region-marking state (#5136) — extracted to composable (#6447)
const { hoveredRegion, popupRegionIndex, popupLabel, regionStyle, popupStyle, openPopup, saveRegion } =
  useRegionMarking({
    regions: toRef(props, 'regions') as Ref<PageRegion[]>,
    imgRef,
    viewportWidth: toRef(props, 'viewportWidth') as Ref<number>,
    viewportHeight: toRef(props, 'viewportHeight') as Ref<number>,
    onRegionsSelected: (regions) => emit('regionsSelected', regions),
  })

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
        loading="lazy"
        @click="handleClick"
      />
      <div v-if="loading" class="loading-overlay">
        <div class="loading-spinner" />
      </div>

      <!-- Region-marking overlay (#5136) -->
      <template v-if="markRegionsMode && regions && regions.length > 0">
        <div
          v-for="(region, i) in regions"
          :key="i"
          class="region-overlay"
          :class="{ 'region-hovered': hoveredRegion === i }"
          :style="regionStyle(region.rect)"
          @mouseenter="hoveredRegion = i"
          @mouseleave="hoveredRegion = null"
          @click.stop="openPopup(i)"
        />
        <div
          v-if="popupRegionIndex !== null"
          class="region-popup"
          :style="popupStyle(regions[popupRegionIndex].rect)"
          @click.stop
        >
          <div class="region-popup-selector">{{ regions[popupRegionIndex].selector }}</div>
          <input
            v-model="popupLabel"
            placeholder="Label (e.g. title, price)"
            class="region-popup-input"
          />
          <button class="region-popup-save" @click="saveRegion(popupRegionIndex)">Save</button>
          <button class="region-popup-cancel" @click="popupRegionIndex = null">Cancel</button>
        </div>
      </template>
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
        <Icon name="chevron-up" />
      </button>
      <button
        class="toolbar-btn"
        :disabled="loading"
        :title="t('browser.interactive.scrollDown')"
        @click="scrollBy(300)"
      >
        <Icon name="chevron-down" />
      </button>
      <button
        class="toolbar-btn"
        :disabled="loading"
        :title="t('browser.interactive.pageUp')"
        @click="scrollBy(-720)"
      >
        <Icon name="chevron-up" />
      </button>
      <button
        class="toolbar-btn"
        :disabled="loading"
        :title="t('browser.interactive.pageDown')"
        @click="scrollBy(720)"
      >
        <Icon name="chevron-down" />
      </button>
      <button
        class="toolbar-btn"
        :disabled="loading"
        :title="t('browser.interactive.typeLabel')"
        @click="showTypeOverlay = !showTypeOverlay"
      >
        <Icon name="keyboard" />
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
      <button class="type-submit" :aria-label="t('common.submit')" @click="submitType">
        <Icon name="paper-plane" />
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
  transition: opacity var(--duration-200) var(--ease-out);
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
  font-size: var(--text-sm);
}

.toolbar {
  display: flex;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
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
  border-radius: var(--radius-default);
  background: transparent;
  color: var(--color-text-secondary, #a1a1aa);
  cursor: pointer;
  font-size: var(--text-xs);
  transition: background var(--duration-150), color var(--duration-150);
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
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--color-surface, #1e1e2e);
  border-top: 1px solid var(--color-border, #333);
}

.type-input {
  flex: 1;
  padding: var(--spacing-1) var(--spacing-2);
  border: 1px solid var(--color-border, #333);
  border-radius: var(--radius-default);
  background: var(--color-bg, #121212);
  color: var(--color-text, #e4e4e7);
  font-size: 0.8rem;
  outline: none;
}

.type-input:focus {
  border-color: var(--color-primary, #3b82f6);
}
.type-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.type-submit {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--radius-default);
  background: var(--color-primary, #3b82f6);
  color: white;
  cursor: pointer;
  font-size: var(--text-xs);
}

/* Region-marking overlay (#5136) */
.region-overlay {
  position: absolute;
  border: 2px solid transparent;
  transition: border-color 0.1s;
}

.region-overlay.region-hovered {
  border-color: rgba(59, 130, 246, 0.8);
  background: rgba(59, 130, 246, 0.1);
}

.region-popup {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 8px;
  min-width: 200px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
}

.region-popup-selector {
  font-size: 0.7rem;
  color: #94a3b8;
  margin-bottom: 6px;
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.region-popup-input {
  width: 100%;
  background: #0f172a;
  border: 1px solid #475569;
  border-radius: 4px;
  padding: 4px 6px;
  color: #e2e8f0;
  font-size: 0.8rem;
  margin-bottom: 6px;
  box-sizing: border-box;
}

.region-popup-save,
.region-popup-cancel {
  font-size: 0.75rem;
  padding: 3px 8px;
  border-radius: 4px;
  cursor: pointer;
}

.region-popup-save {
  background: #3b82f6;
  color: white;
  border: none;
  margin-right: 4px;
}

.region-popup-cancel {
  background: transparent;
  color: #94a3b8;
  border: 1px solid #475569;
}
</style>
