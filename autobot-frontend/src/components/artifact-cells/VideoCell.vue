<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  VideoCell.vue - AI-generated video display component
  Renders a generated video clip inline (Runway ML, Sora, or Kling) with a
  progress indicator while generation is in flight, plus download / copy-URL.
  GH#9016
-->
<template>
  <div class="video-cell">
    <!-- Empty state -->
    <div v-if="!richPayload" class="video-placeholder">
      <div class="placeholder-content">
        <Icon name="video" />
        <span>{{ $t('videoCell.placeholder', 'Video') }}</span>
      </div>
    </div>

    <!-- Content -->
    <div v-else class="video-content">
      <!-- Provider badge -->
      <div v-if="provider" class="video-meta">
        <span class="provider-badge">{{ providerLabel }}</span>
        <span v-if="durationLabel" class="size-badge">{{ durationLabel }}</span>
      </div>

      <!-- In-progress indicator -->
      <div v-if="isGenerating" class="video-progress" role="status" aria-live="polite">
        <div class="spinner" aria-hidden="true"></div>
        <div class="progress-track">
          <div class="progress-bar" :style="{ width: `${progressPct}%` }"></div>
        </div>
        <span class="progress-label">
          {{ $t('videoCell.generating', 'Generating video…') }} {{ progressPct }}%
        </span>
      </div>

      <!-- Failed state -->
      <div v-else-if="hasError" class="video-error">
        <Icon name="exclamation-circle" />
        <span>{{ errorText || $t('videoCell.failed', 'Video generation failed') }}</span>
      </div>

      <!-- Playable video -->
      <div v-else-if="videoUrl" class="video-wrapper">
        <video
          :src="videoUrl"
          class="generated-video"
          controls
          playsinline
          preload="metadata"
          @error="onVideoError"
        ></video>
      </div>

      <!-- Prompt caption -->
      <p v-if="promptText" class="video-prompt">
        <Icon name="pencil" />
        <span>{{ promptText }}</span>
      </p>

      <!-- Actions -->
      <div v-if="videoUrl" class="video-actions">
        <a
          class="action-btn"
          :href="videoUrl"
          :download="downloadName"
          rel="noopener noreferrer"
          :title="$t('videoCell.download', 'Download video')"
        >
          <Icon name="download" />
        </a>
        <button
          class="action-btn"
          @click.stop="copyVideoUrl(videoUrl)"
          :title="$t('videoCell.copyUrl', 'Copy URL')"
        >
          <Icon :name="copied ? 'check' : 'copy'" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { computed, ref } from 'vue'


interface VideoCellProps {
  richPayload?: Record<string, unknown> | null
}

const props = withDefaults(defineProps<VideoCellProps>(), {
  richPayload: null,
})

const videoUrl = computed<string | null>(() => (props.richPayload?.video_url as string) ?? null)
const provider = computed<string>(() => (props.richPayload?.provider as string) ?? '')
const promptText = computed<string>(() => (props.richPayload?.prompt as string) ?? '')
const statusValue = computed<string>(() => (props.richPayload?.status as string) ?? '')
const errorText = computed<string>(() => (props.richPayload?.error as string) ?? '')

const duration = computed<number | null>(() => {
  const d = props.richPayload?.duration
  return typeof d === 'number' ? d : null
})
const durationLabel = computed<string>(() => (duration.value ? `${duration.value}s` : ''))

const progressPct = computed<number>(() => {
  const raw = Number(props.richPayload?.progress ?? 0)
  const pct = raw > 1 ? raw : raw * 100
  return Math.max(0, Math.min(100, Math.round(pct)))
})

const localError = ref(false)
const hasError = computed<boolean>(() => statusValue.value === 'failed' || !!errorText.value || localError.value)
const isGenerating = computed<boolean>(
  () => !videoUrl.value && !hasError.value && ['pending', 'running'].includes(statusValue.value),
)

const providerLabel = computed<string>(() => {
  const map: Record<string, string> = { runway: 'Runway ML', sora: 'Sora', kling: 'Kling AI' }
  return map[provider.value] ?? provider.value
})

const downloadName = computed<string>(() => `generated-video.${guessExt(videoUrl.value)}`)

function guessExt(url: string | null): string {
  if (!url) return 'mp4'
  const m = url.split('?')[0].match(/\.(mp4|webm|mov)$/i)
  return m ? m[1].toLowerCase() : 'mp4'
}

const onVideoError = () => {
  localError.value = true
}

const copied = ref(false)
const copyVideoUrl = async (url: string) => {
  try {
    await navigator.clipboard.writeText(url)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    // silent fail
  }
}
</script>

<style scoped>
.video-cell {
  width: 100%;
}

.video-placeholder {
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

.video-content {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.video-meta {
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

.video-wrapper {
  width: 100%;
  max-width: 640px;
  border-radius: 0.5rem;
  overflow: hidden;
  background: #000;
}

.generated-video {
  width: 100%;
  display: block;
  border-radius: 0.5rem;
}

.video-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 1.5rem;
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: 0.5rem;
  max-width: 640px;
}

.spinner {
  width: 1.75rem;
  height: 1.75rem;
  border: 3px solid var(--color-surface-2, #f3f4f6);
  border-top-color: var(--color-primary, #3b82f6);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.progress-track {
  width: 100%;
  height: 0.375rem;
  background: var(--color-surface-2, #f3f4f6);
  border-radius: 9999px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: var(--color-primary, #3b82f6);
  transition: width 0.3s ease;
}

.progress-label {
  font-size: 0.8125rem;
  color: var(--text-muted, #6b7280);
}

.video-error {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 1rem;
  border-radius: 0.5rem;
  background: var(--color-surface-2, #f3f4f6);
  color: var(--color-error, #dc2626);
  font-size: 0.875rem;
  max-width: 640px;
}

.video-prompt {
  display: flex;
  align-items: flex-start;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--text-muted, #6b7280);
  font-style: italic;
  line-height: 1.4;
  margin: 0;
}

.video-actions {
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
  text-decoration: none;
  transition: background 0.15s;
}

.action-btn:hover {
  background: var(--color-surface-2, #f3f4f6);
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
  }
  .generated-video,
  .action-btn,
  .progress-bar {
    transition: none;
  }
}
</style>
