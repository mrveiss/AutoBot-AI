<template>
  <div class="voice-interface">
    <div class="voice-container">
      <!-- Voice Visualization -->
      <div class="voice-visualization">
        <div class="waveform-container">
          <div
            v-for="i in 20"
            :key="i"
            class="wave-bar"
            :class="{ active: isListening }"
            :style="{ animationDelay: `${i * 0.1}s` }"
          ></div>
        </div>
        <div class="voice-status-circle" :class="{
          listening: isListening,
          processing: isProcessing,
          speaking: isSpeaking
        }">
          <div class="status-icon">
            <span v-if="!isListening && !isProcessing && !isSpeaking">🎤</span>
            <span v-else-if="isListening">🔊</span>
            <span v-else-if="isProcessing">⚡</span>
            <span v-else-if="isSpeaking">🔈</span>
          </div>
        </div>
      </div>

      <!-- Voice Controls -->
      <div class="voice-controls">
        <button
          class="voice-btn primary"
          @click="toggleListening"
          :disabled="isProcessing"
          :class="{ 'disabled': isProcessing }"
          :aria-label="isListening ? 'Stop listening' : 'Start listening'">
          <i v-if="isProcessing" class="fas fa-spinner fa-spin mr-2"></i>
          {{ isListening ? 'Stop Listening' : 'Start Listening' }}
        </button>
        <button
          class="voice-btn secondary"
          @click="testTTS"
          :disabled="isListening || isProcessing"
          :class="{ 'disabled': isListening || isProcessing }"
          aria-label="Test voice">
          <i class="fas mr-2" :class="isProcessing ? 'fa-spinner fa-spin' : 'fa-volume-up'"></i>
          Test Voice
        </button>
      </div>

      <!-- Voice Settings -->
      <BasePanel variant="bordered" size="medium">
        <template #header>
          <h3>Voice Configuration</h3>
        </template>
        <div class="setting-group">
          <label>Speech Recognition Language</label>
          <select v-model="settings.stt_language">
            <option value="en-US">English (US)</option>
            <option value="en-GB">English (UK)</option>
            <option value="es-ES">Spanish</option>
            <option value="fr-FR">French</option>
            <option value="de-DE">German</option>
          </select>
        </div>
        <div class="setting-group">
          <label>Voice Speed</label>
          <input
            type="range"
            min="0.5"
            max="2"
            step="0.1"
            v-model="settings.speech_rate"
            class="voice-slider"
          >
          <span class="slider-value">{{ settings.speech_rate }}x</span>
        </div>
        <div class="setting-group">
          <label>Voice Pitch</label>
          <input
            type="range"
            min="0.5"
            max="2"
            step="0.1"
            v-model="settings.pitch"
            class="voice-slider"
          >
          <span class="slider-value">{{ settings.pitch }}x</span>
        </div>
        <div class="setting-group">
          <label>Auto-Listen After Response</label>
          <input type="checkbox" v-model="settings.auto_listen">
        </div>
      </BasePanel>

      <!-- Wake Word Settings -->
      <BasePanel variant="bordered" size="medium">
        <template #header>
          <h3>Wake Word Detection</h3>
        </template>
        <div class="setting-group">
          <label>Enable Wake Words</label>
          <input type="checkbox" v-model="wakeWordSettings.enabled" @change="toggleWakeWordDetection">
        </div>
        <div class="setting-group">
          <label>Confidence Threshold</label>
          <input
            type="range"
            min="0.5"
            max="0.95"
            step="0.05"
            v-model="wakeWordSettings.confidence_threshold"
            class="voice-slider"
            @change="updateWakeWordConfig"
          >
          <span class="slider-value">{{ (wakeWordSettings.confidence_threshold * 100).toFixed(0) }}%</span>
        </div>
        <div class="setting-group wake-words-list">
          <label>Active Wake Words</label>
          <div class="wake-words-container">
            <div
              v-for="word in wakeWordSettings.wake_words"
              :key="word"
              class="wake-word-tag"
            >
              {{ word }}
              <button
                class="remove-wake-word"
                @click="removeWakeWord(word)"
                :disabled="wakeWordSettings.wake_words.length <= 1"
              >×</button>
            </div>
          </div>
        </div>
        <div class="setting-group">
          <label>Add Wake Word</label>
          <div class="add-wake-word-input">
            <input
              type="text"
              v-model="newWakeWord"
              placeholder="e.g., hello assistant"
              @keyup.enter="addWakeWord"
            >
            <button class="add-btn" @click="addWakeWord">Add</button>
          </div>
        </div>
        <div class="wake-word-stats" v-if="wakeWordStats.total_detections > 0">
          <div class="stat-item">
            <span class="stat-label">Total Detections:</span>
            <span class="stat-value">{{ wakeWordStats.total_detections }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Accuracy:</span>
            <span class="stat-value">{{ wakeWordStats.accuracy.toFixed(1) }}%</span>
          </div>
        </div>
      </BasePanel>

      <!-- Recent Voice Commands -->
      <BasePanel variant="bordered" size="medium">
        <template #header>
          <h3>Recent Voice Commands</h3>
        </template>
        <div class="history-list">
          <div
            v-for="(command, index) in voiceHistory"
            :key="index"
            class="history-item"
          >
            <div class="command-time">{{ command.timestamp }}</div>
            <div class="command-text">{{ command.text }}</div>
            <div class="command-confidence">{{ Math.round(command.confidence * 100) }}%</div>
          </div>
        </div>
      </BasePanel>

      <!-- Voice Status Display -->
      <div class="voice-status-display" v-if="currentTranscription || statusMessage || isProcessing">
        <div class="transcription" v-if="currentTranscription">
          <strong>Transcription:</strong> {{ currentTranscription }}
        </div>
        <div class="status-message" v-if="statusMessage || isProcessing">
          <i v-if="isProcessing" class="fas fa-spinner fa-spin mr-2"></i>
          {{ statusMessage || (isProcessing ? 'Processing command...' : '') }}
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted } from 'vue';
import apiClient from '@/utils/ApiClient.js';
import { useAsyncHandler } from '@/composables/useErrorHandler';
import BasePanel from '@/components/base/BasePanel.vue';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for VoiceInterface
const logger = createLogger('VoiceInterface');

export default {
  name: 'VoiceInterface',
  components: {
    BasePanel
  },
  setup() {
    const isListening = ref(false);
    const isSpeaking = ref(false);
    const currentTranscription = ref('');
    const statusMessage = ref('');
    const voiceHistory = ref([]);

    const settings = ref({
      stt_language: 'en-US',
      speech_rate: 1.0,
      pitch: 1.0,
      auto_listen: false
    });

    // Wake word settings
    const wakeWordSettings = ref({
      enabled: true,
      wake_words: ['hey autobot', 'ok autobot', 'autobot'],
      confidence_threshold: 0.7,
      cooldown_seconds: 2.0,
      adaptive_threshold: true
    });

    const wakeWordStats = ref({
      total_detections: 0,
      true_positives: 0,
      false_positives: 0,
      accuracy: 0
    });

    const newWakeWord = ref('');

    let recognition = null;
    let speechSynthesis = null;

    const initializeSpeechRecognition = () => {
      if ('webkitSpeechRecognition' in window) {
        recognition = new webkitSpeechRecognition();
      } else if ('SpeechRecognition' in window) {
        recognition = new SpeechRecognition();
      }

      if (recognition) {
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = settings.value.stt_language;

        recognition.onstart = () => {
          isListening.value = true;
          statusMessage.value = 'Listening...';
        };

        recognition.onresult = (event) => {
          let finalTranscript = '';
          let interimTranscript = '';

          for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
              finalTranscript += transcript;
            } else {
              interimTranscript += transcript;
            }
          }

          currentTranscription.value = finalTranscript + interimTranscript;

          if (finalTranscript) {
            processVoiceCommand(finalTranscript, event.results[event.results.length - 1][0].confidence);
          }
        };

        recognition.onerror = (event) => {
          logger.error('Speech recognition error:', event.error);
          statusMessage.value = `Error: ${event.error}`;
          isListening.value = false;
        };

        recognition.onend = () => {
          isListening.value = false;
          if (currentTranscription.value && !statusMessage.value.includes('Error')) {
            statusMessage.value = 'Processing...';
          }
        };
      }
    };

    const initializeSpeechSynthesis = () => {
      if ('speechSynthesis' in window) {
        speechSynthesis = window.speechSynthesis;
      }
    };

    const toggleListening = () => {
      if (!recognition) {
        statusMessage.value = 'Speech recognition not supported in this browser';
        return;
      }

      if (isListening.value) {
        recognition.stop();
        statusMessage.value = 'Stopped listening';
      } else {
        recognition.lang = settings.value.stt_language;
        recognition.start();
        currentTranscription.value = '';
        statusMessage.value = '';
      }
    };

    const { execute: processVoiceCommandInternal, loading: isProcessing } = useAsyncHandler(
      async (text, confidence) => {
        // Add to history
        voiceHistory.value.unshift({
          text,
          confidence,
          timestamp: new Date().toLocaleTimeString()
        });

        // Keep only last 10 commands
        if (voiceHistory.value.length > 10) {
          voiceHistory.value = voiceHistory.value.slice(0, 10);
        }

        // Send to backend for processing
        // ApiClient.post() returns parsed JSON directly
        return await apiClient.post('/api/voice/listen', {
          text: text,
          confidence: confidence
        });
      },
      {
        onSuccess: async (data) => {
          if (data.response) {
            // Speak the response
            await speakText(data.response);
            statusMessage.value = 'Response completed';
          }

          // Auto-listen if enabled
          if (settings.value.auto_listen && !isListening.value) {
            setTimeout(() => {
              if (recognition && !isListening.value) {
                recognition.start();
              }
            }, 1000);
          }
        },
        onError: () => {
          statusMessage.value = 'Error processing command';
        },
        onFinally: () => {
          currentTranscription.value = '';
        },
        logErrors: true,
        errorPrefix: '[VoiceInterface]'
      }
    );

    const processVoiceCommand = (text, confidence) => {
      processVoiceCommandInternal(text, confidence);
    };

    const speakText = async (text) => {
      return new Promise((resolve, reject) => {
        if (!speechSynthesis) {
          reject(new Error('Speech synthesis not supported'));
          return;
        }

        isSpeaking.value = true;

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = settings.value.speech_rate;
        utterance.pitch = settings.value.pitch;
        utterance.lang = settings.value.stt_language;

        utterance.onend = () => {
          isSpeaking.value = false;
          resolve();
        };

        utterance.onerror = (error) => {
          isSpeaking.value = false;
          reject(error);
        };

        speechSynthesis.speak(utterance);
      });
    };

    const testTTS = async () => {
      const testMessage = "Hello! This is a test of the text-to-speech system. Your voice interface is working correctly.";
      try {
        await speakText(testMessage);
        statusMessage.value = 'Voice test completed';
      } catch (error) {
        statusMessage.value = 'Voice test failed';
        logger.error('TTS test error:', error);
      }
    };

    // Wake word management methods
    const loadWakeWordSettings = async () => {
      try {
        // ApiClient.get() returns parsed JSON directly
        const data = await apiClient.get('/api/wake_word/config');
        if (data) {
          wakeWordSettings.value = {
            ...wakeWordSettings.value,
            ...data
          };
        }
      } catch (error) {
        logger.error('Failed to load wake word settings:', error);
      }
    };

    const loadWakeWordStats = async () => {
      try {
        // ApiClient.get() returns parsed JSON directly
        const data = await apiClient.get('/api/wake_word/stats');
        if (data) {
          wakeWordStats.value = {
            total_detections: data.total_detections || 0,
            true_positives: data.true_positives || 0,
            false_positives: data.false_positives || 0,
            accuracy: data.accuracy || 0
          };
        }
      } catch (error) {
        logger.error('Failed to load wake word stats:', error);
      }
    };

    const toggleWakeWordDetection = async () => {
      try {
        if (wakeWordSettings.value.enabled) {
          await apiClient.post('/api/wake_word/enable');
          statusMessage.value = 'Wake word detection enabled';
        } else {
          await apiClient.post('/api/wake_word/disable');
          statusMessage.value = 'Wake word detection disabled';
        }
      } catch (error) {
        logger.error('Failed to toggle wake word detection:', error);
        statusMessage.value = 'Failed to toggle wake word detection';
      }
    };

    const updateWakeWordConfig = async () => {
      try {
        await apiClient.put('/api/wake_word/config', {
          confidence_threshold: parseFloat(wakeWordSettings.value.confidence_threshold),
          cooldown_seconds: wakeWordSettings.value.cooldown_seconds,
          adaptive_threshold: wakeWordSettings.value.adaptive_threshold
        });
        statusMessage.value = 'Wake word config updated';
      } catch (error) {
        logger.error('Failed to update wake word config:', error);
        statusMessage.value = 'Failed to update config';
      }
    };

    const addWakeWord = async () => {
      if (!newWakeWord.value.trim()) return;

      try {
        // ApiClient.post() returns parsed JSON directly
        const data = await apiClient.post('/api/wake_word/words', {
          wake_word: newWakeWord.value.trim()
        });
        if (data.success) {
          wakeWordSettings.value.wake_words = data.wake_words;
          newWakeWord.value = '';
          statusMessage.value = `Wake word "${data.wake_words[data.wake_words.length - 1]}" added`;
        } else {
          statusMessage.value = data.message || 'Wake word already exists';
        }
      } catch (error) {
        logger.error('Failed to add wake word:', error);
        statusMessage.value = 'Failed to add wake word';
      }
    };

    const removeWakeWord = async (word) => {
      try {
        // ApiClient.delete() returns parsed JSON directly
        const data = await apiClient.delete(`/api/wake_word/words/${encodeURIComponent(word)}`);
        if (data.success) {
          wakeWordSettings.value.wake_words = data.wake_words;
          statusMessage.value = `Wake word "${word}" removed`;
        }
      } catch (error) {
        logger.error('Failed to remove wake word:', error);
        statusMessage.value = error.message || 'Failed to remove wake word';
      }
    };

    onMounted(() => {
      initializeSpeechRecognition();
      initializeSpeechSynthesis();

      // Load settings from localStorage
      const savedSettings = localStorage.getItem('voice_settings');
      if (savedSettings) {
        try {
          settings.value = { ...settings.value, ...JSON.parse(savedSettings) };
        } catch (e) {
          logger.error('Error loading voice settings:', e);
        }
      }

      // Load voice history
      const savedHistory = localStorage.getItem('voice_history');
      if (savedHistory) {
        try {
          voiceHistory.value = JSON.parse(savedHistory);
        } catch (e) {
          logger.error('Error loading voice history:', e);
        }
      }

      // Load wake word settings from backend
      loadWakeWordSettings();
      loadWakeWordStats();
    });

    onUnmounted(() => {
      if (recognition && isListening.value) {
        recognition.stop();
      }
      if (speechSynthesis) {
        speechSynthesis.cancel();
      }

      // Save settings and history
      localStorage.setItem('voice_settings', JSON.stringify(settings.value));
      localStorage.setItem('voice_history', JSON.stringify(voiceHistory.value));
    });

    return {
      isListening,
      isProcessing,
      isSpeaking,
      currentTranscription,
      statusMessage,
      voiceHistory,
      settings,
      toggleListening,
      testTTS,
      // Wake word exports
      wakeWordSettings,
      wakeWordStats,
      newWakeWord,
      toggleWakeWordDetection,
      updateWakeWordConfig,
      addWakeWord,
      removeWakeWord
    };
  }
};
</script>

<style scoped>
/* VoiceInterface - Migrated to Design Tokens
 * Issue #704: CSS Design System - Centralized Theming & SSOT Styles
 */

.voice-interface {
  display: flex;
  flex-direction: column;
  height: 100%;
  color: var(--text-primary);
  background-color: var(--bg-card);
  overflow-y: auto;
  max-height: calc(100vh - 200px);
  padding: var(--spacing-5);
}

.voice-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: auto auto auto;
  gap: var(--spacing-6);
  height: 100%;
}

.voice-visualization {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-6);
  padding: var(--spacing-8);
  background: var(--bg-hover);
  border-radius: var(--radius-2xl);
  border: 1px solid var(--border-subtle);
}

.waveform-container {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  height: 80px;
}

.wave-bar {
  width: 4px;
  background: linear-gradient(to top, var(--chart-cyan), var(--chart-cyan-light));
  border-radius: var(--radius-xs);
  height: 20px;
  transition: height var(--duration-300) var(--ease-in-out);
}

.wave-bar.active {
  animation: waveform 0.8s ease-in-out infinite alternate;
}

@keyframes waveform {
  0% { height: 20px; }
  100% { height: 60px; }
}

.voice-status-circle {
  width: 120px;
  height: 120px;
  border-radius: var(--radius-full);
  background: var(--color-primary-bg);
  border: 3px solid var(--color-primary-bg-hover);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-300) var(--ease-in-out);
  position: relative;
  overflow: hidden;
}

.voice-status-circle.listening {
  border-color: var(--color-success);
  background: var(--color-success-bg-hover);
  animation: listeningPulse 2s ease-in-out infinite;
}

.voice-status-circle.processing {
  border-color: var(--color-warning);
  background: var(--color-warning-bg-hover);
  animation: processingRotate 1s linear infinite;
}

.voice-status-circle.speaking {
  border-color: var(--color-info);
  background: var(--color-info-bg-hover);
  animation: speakingPulse 0.5s ease-in-out infinite;
}

@keyframes listeningPulse {
  0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 var(--color-success-bg); }
  50% { transform: scale(1.05); box-shadow: 0 0 0 20px transparent; }
}

@keyframes processingRotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes speakingPulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.1); }
}

.status-icon {
  font-size: var(--text-4xl);
  z-index: var(--z-10);
}

.voice-controls {
  display: flex;
  gap: var(--spacing-4);
  justify-content: center;
  grid-column: 1 / -1;
}

.voice-btn {
  padding: var(--spacing-4) var(--spacing-8);
  border: none;
  border-radius: var(--radius-xl);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: all var(--duration-300) var(--ease-in-out);
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
}

.voice-btn.primary {
  background: linear-gradient(135deg, var(--color-success), var(--color-success-light));
  color: var(--text-on-success);
}

.voice-btn.secondary {
  background: var(--color-primary-bg);
  color: var(--text-primary);
  border: 1px solid var(--color-primary-bg-hover);
}

.voice-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: var(--shadow-xl);
}

.voice-btn:disabled,
.voice-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}


.setting-group {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
  flex-wrap: wrap;
}

.setting-group label {
  font-size: var(--text-sm);
  color: var(--text-primary);
  min-width: 120px;
  font-weight: var(--font-medium);
}

.setting-group select {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  color: var(--text-primary);
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
}

.voice-slider {
  flex: 1;
  max-width: 200px;
  accent-color: var(--color-success);
}

.slider-value {
  color: var(--text-primary);
  font-weight: var(--font-medium);
}

.history-list {
  max-height: 300px;
  overflow-y: auto;
}

.history-item {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--bg-hover);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-2);
  font-size: var(--text-sm);
  border: 1px solid var(--border-subtle);
}

.command-time {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

.command-text {
  color: var(--text-primary);
  font-weight: var(--font-medium);
}

.command-confidence {
  color: var(--color-success);
  font-weight: var(--font-semibold);
  font-size: var(--text-xs);
}

.voice-status-display {
  grid-column: 1 / -1;
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
  border: 1px solid var(--border-subtle);
  color: var(--text-primary);
}

.transcription {
  margin-bottom: var(--spacing-3);
  font-size: var(--text-base);
  color: var(--text-primary);
}

.status-message {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  font-style: italic;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

/* Wake word styles */
.wake-words-list {
  flex-direction: column;
  align-items: flex-start;
}

.wake-words-container {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
  margin-top: var(--spacing-2);
}

.wake-word-tag {
  background: linear-gradient(135deg, var(--color-success), var(--color-success-light));
  color: var(--text-on-success);
  padding: var(--spacing-1-5) var(--spacing-3);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.remove-wake-word {
  background: rgba(255, 255, 255, 0.2);
  border: none;
  color: var(--text-on-success);
  width: 20px;
  height: 20px;
  border-radius: var(--radius-full);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: var(--font-bold);
  font-size: var(--text-sm);
  transition: background var(--duration-200);
}

.remove-wake-word:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.4);
}

.remove-wake-word:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.add-wake-word-input {
  display: flex;
  gap: var(--spacing-2);
  flex: 1;
}

.add-wake-word-input input {
  flex: 1;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  background: var(--bg-card);
  color: var(--text-primary);
}

.add-btn {
  background: linear-gradient(135deg, var(--color-primary), var(--chart-purple));
  color: var(--text-on-primary);
  border: none;
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-lg);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: transform var(--duration-200), box-shadow var(--duration-200);
}

.add-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary);
}

.wake-word-stats {
  margin-top: var(--spacing-4);
  padding: var(--spacing-3);
  background: var(--color-primary-bg);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-primary-bg-hover);
}

.stat-item {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--spacing-2);
}

.stat-item:last-child {
  margin-bottom: 0;
}

.stat-label {
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}

.stat-value {
  color: var(--text-primary);
  font-weight: var(--font-semibold);
  font-size: var(--text-sm);
}

@media (max-width: 768px) {
  .voice-container {
    grid-template-columns: 1fr;
    grid-template-rows: auto auto auto auto;
  }

  .voice-controls {
    flex-direction: column;
  }

  .voice-btn {
    padding: var(--spacing-3) var(--spacing-6);
    font-size: var(--text-sm);
  }
}
</style>
