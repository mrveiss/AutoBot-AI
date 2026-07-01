<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ImageCell.vue - AI-generated image display component
  Renders images from DALL-E 3, Flux, or Stable Diffusion with
  lightbox, download, and copy-URL actions.
  GH#9015
-->
<template>
  <div class="image-cell">
    <!-- Empty state -->
    <div v-if="!richPayload" class="image-placeholder">
      <div class="placeholder-content">
        <Icon name="image" />
        <span>{{ $t('imageCell.placeholder', 'Image') }}</span>
      </div>
    </div>

    <!-- Content -->
    <div v-else class="image-content">
      <!-- Provider badge -->
      <div v-if="provider" class="image-meta">
        <span class="provider-badge">{{ providerLabel }}</span>
        <span v-if="imageSize" class="size-badge">{{ imageSize }}</span>
      </div>

      <!-- Image grid -->
      <div class="image-grid" :class="`grid-${images.length}`">
        <div
          v-for="(img, index) in images"
          :key="index"
          class="image-wrapper"
          @click="openLightbox(index)"
          :aria-label="$t('imageCell.viewFull', 'View full size')"
          role="button"
          tabindex="0"
          @keydown.enter="openLightbox(index)"
          @keydown.space.prevent="openLightbox(index)"
        >
          <img
            :src="img.url"
            :alt="img.revised_prompt || promptText || $t('imageCell.generated', 'AI generated image')"
            class="generated-image"
            loading="lazy"
            @error="onImageError(index)"
          />
          <div v-if="imageErrors[index]" class="image-error-overlay">
            <Icon name="exclamation-circle" />
            <span>{{ $t('imageCell.loadError', 'Failed to load') }}</span>
          </div>
          <div class="image-overlay">
            <Icon name="search-plus" />
          </div>
        </div>
      </div>

      <!-- Prompt caption -->
      <p v-if="promptText" class="image-prompt">
        <Icon name="pencil" />
        <span>{{ promptText }}</span>
      </p>

      <!-- Actions -->
      <div class="image-actions">
        <button
          v-for="(img, index) in images"
          :key="`dl-${index}`"
          class="action-btn"
          @click.stop="downloadImage(img.url, index)"
          :title="$t('imageCell.download', 'Download image')"
          :aria-label="$t('imageCell.downloadLabel', { n: (index as number) + 1 })"
        >
          <Icon name="download" />
          <span v-if="images.length > 1">{{ (index as number) + 1 }}</span>
        </button>
        <button
          v-if="images.length === 1"
          class="action-btn"
          @click.stop="copyImageUrl(images[0].url)"
          :title="$t('imageCell.copyUrl', 'Copy URL')"
        >
          <Icon :name="copied ? 'check' : 'copy'" />
        </button>
      </div>
    </div>

    <!-- Lightbox -->
    <Teleport to="body">
      <div
        v-if="lightboxOpen"
        class="image-lightbox"
        @click.self="closeLightbox"
        @keydown.escape="closeLightbox"
        role="dialog"
        :aria-label="$t('imageCell.lightbox', 'Image viewer')"
        tabindex="-1"
        ref="lightboxRef"
      >
        <button class="lightbox-close" @click="closeLightbox" :aria-label="$t('common.close', 'Close')">
          <Icon name="x" />
        </button>
        <div class="lightbox-content">
          <img
            :src="images[lightboxIndex]?.url"
            :alt="images[lightboxIndex]?.revised_prompt || promptText || ''"
            class="lightbox-image"
          />
          <p v-if="images[lightboxIndex]?.revised_prompt" class="lightbox-caption">
            {{ images[lightboxIndex].revised_prompt }}
          </p>
        </div>
        <button
          v-if="images.length > 1"
          class="lightbox-nav prev"
          @click="lightboxIndex = (lightboxIndex - 1 + images.length) % images.length"
          :aria-label="$t('common.previous', 'Previous')"
        >
          <Icon name="chevron-left" />
        </button>
        <button
          v-if="images.length > 1"
          class="lightbox-nav next"
          @click="lightboxIndex = (lightboxIndex + 1) % images.length"
          :aria-label="$t('common.next', 'Next')"
        >
          <Icon name="chevron-right" />
        </button>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

interface GeneratedImage {
  url: string
  revised_prompt?: string | null
}

interface ImageCellProps {
  richPayload?: Record<string, unknown> | null
}

const props = withDefaults(defineProps<ImageCellProps>(), {
  richPayload: null,
})

// Derived data from richPayload
const images = computed<GeneratedImage[]>(() => {
  const raw = (props.richPayload?.images as GeneratedImage[] | undefined) ?? []
  return raw.filter((img) => img?.url)
})

const provider = computed<string>(() => (props.richPayload?.provider as string) ?? '')
const imageSize = computed<string>(() => (props.richPayload?.size as string) ?? '')
const promptText = computed<string>(() => (props.richPayload?.prompt as string) ?? '')

const providerLabel = computed<string>(() => {
  const map: Record<string, string> = {
    dalle: 'DALL·E 3',
    flux: 'Flux',
    stable_diffusion: 'Stable Diffusion',
  }
  return map[provider.value] ?? provider.value
})

// Image load errors per index
const imageErrors = ref<Record<number, boolean>>({})
const onImageError = (index: number) => {
  imageErrors.value[index] = true
}

// Lightbox
const lightboxOpen = ref(false)
const lightboxIndex = ref(0)
const lightboxRef = ref<HTMLElement | null>(null)

const openLightbox = async (index: number) => {
  lightboxIndex.value = index
  lightboxOpen.value = true
  await nextTick()
  lightboxRef.value?.focus()
}

const closeLightbox = () => {
  lightboxOpen.value = false
}

// Actions
const copied = ref(false)

const copyImageUrl = async (url: string) => {
  try {
    await navigator.clipboard.writeText(url)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    // fallback: silent fail
  }
}

const downloadImage = (url: string, index: number) => {
  const ext = url.startsWith('data:image/') ? url.split(';')[0].split('/')[1] : 'png'
  const filename = `generated-image-${index + 1}.${ext}`
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener noreferrer'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
</script>

<style scoped>
.image-cell {
  width: 100%;
}

.image-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  border: 1px dashed var(--border-default, #e5e7eb);
  border-radius: 0.5rem;
  color: var(--text-muted, #6b7280);
}

.placeholder-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.image-content {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.image-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.provider-badge,
.size-badge {
  font-size: 0.75rem;
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  background: var(--color-surface-2, #f3f4f6);
  color: var(--text-muted, #6b7280);
  font-weight: 500;
}

/* Grid layouts */
.image-grid {
  display: grid;
  gap: 0.5rem;
  width: 100%;
}

.image-grid.grid-1 {
  grid-template-columns: 1fr;
  max-width: 512px;
}

.image-grid.grid-2 {
  grid-template-columns: repeat(2, 1fr);
}

.image-grid.grid-3,
.image-grid.grid-4 {
  grid-template-columns: repeat(2, 1fr);
}

.image-wrapper {
  position: relative;
  cursor: pointer;
  border-radius: 0.5rem;
  overflow: hidden;
  aspect-ratio: 1 / 1;
  background: var(--color-surface-2, #f3f4f6);
}

.image-wrapper:focus-visible {
  outline: 2px solid var(--color-primary, #3b82f6);
  outline-offset: 2px;
}

.generated-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.2s ease;
}

.image-wrapper:hover .generated-image {
  transform: scale(1.02);
}

.image-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.3);
  color: white;
  opacity: 0;
  transition: opacity 0.2s ease;
  font-size: 1.5rem;
}

.image-wrapper:hover .image-overlay,
.image-wrapper:focus-visible .image-overlay {
  opacity: 1;
}

.image-error-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--color-surface-2, #f3f4f6);
  color: var(--text-muted, #6b7280);
  gap: 0.5rem;
  font-size: 0.875rem;
}

.image-prompt {
  display: flex;
  align-items: flex-start;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--text-muted, #6b7280);
  font-style: italic;
  line-height: 1.4;
  margin: 0;
}

.image-actions {
  display: flex;
  gap: 0.375rem;
  flex-wrap: wrap;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.625rem;
  font-size: 0.75rem;
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: 0.375rem;
  background: var(--bg-surface, #fff);
  color: var(--text-primary, #374151);
  cursor: pointer;
  transition: background 0.15s;
}

.action-btn:hover {
  background: var(--color-surface-2, #f3f4f6);
}

/* Lightbox */
.image-lightbox {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.lightbox-content {
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.lightbox-image {
  max-width: 100%;
  max-height: 80vh;
  object-fit: contain;
  border-radius: 0.5rem;
}

.lightbox-caption {
  color: rgba(255, 255, 255, 0.8);
  font-size: 0.875rem;
  text-align: center;
  max-width: 60ch;
  margin: 0;
}

.lightbox-close {
  position: absolute;
  top: 1rem;
  right: 1rem;
  background: rgba(255, 255, 255, 0.15);
  border: none;
  color: white;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 1.25rem;
  transition: background 0.15s;
}

.lightbox-close:hover {
  background: rgba(255, 255, 255, 0.25);
}

.lightbox-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(255, 255, 255, 0.15);
  border: none;
  color: white;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 1.25rem;
  transition: background 0.15s;
}

.lightbox-nav:hover {
  background: rgba(255, 255, 255, 0.25);
}

.lightbox-nav.prev {
  left: 1rem;
}

.lightbox-nav.next {
  right: 1rem;
}

@media (prefers-reduced-motion: reduce) {
  .generated-image,
  .image-overlay,
  .action-btn,
  .lightbox-close,
  .lightbox-nav {
    transition: none;
  }
}
</style>
