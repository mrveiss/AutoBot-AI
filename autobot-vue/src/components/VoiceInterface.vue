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
        >
          {{ isListening ? 'Stop Listening' : 'Start Listening' }}
        </button>
        <button
          class="voice-btn secondary"
          @click="testTTS"
          :disabled="isListening || isProcessing"
        >
          Test Voice
        </button>
      </div>

      <!-- Voice Settings -->
      <div class="voice-settings glass-card">
        <h3>Voice Configuration</h3>
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
          <span style="color: #374151; font-weight: 500;">{{ settings.speech_rate }}x</span>
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
          <span style="color: #374151; font-weight: 500;">{{ settings.pitch }}x</span>
        </div>
        <div class="setting-group">
          <label>Auto-Listen After Response</label>
          <input type="checkbox" v-model="settings.auto_listen">
        </div>
      </div>

      <!-- Recent Voice Commands -->
      <div class="voice-history glass-card">
        <h3>Recent Voice Commands</h3>
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
      </div>

      <!-- Voice Status Display -->
      <div class="voice-status-display" v-if="currentTranscription || statusMessage">
        <div class="transcription" v-if="currentTranscription">
          <strong>Transcription:</strong> {{ currentTranscription }}
        </div>
        <div class="status-message" v-if="statusMessage">
          {{ statusMessage }}
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted } from 'vue';
import apiClient from '@/utils/ApiClient.js';

export default {
  name: 'VoiceInterface',
  setup() {
    const isListening = ref(false);
    const isProcessing = ref(false);
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
          console.error('Speech recognition error:', event.error);
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

    const processVoiceCommand = async (text, confidence) => {
      isProcessing.value = true;

      try {
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
        const response = await apiClient.post('/api/voice/listen', {
          text: text,
          confidence: confidence
        });

        if (response.response) {
          // Speak the response
          await speakText(response.response);
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

      } catch (error) {
        console.error('Error processing voice command:', error);
        statusMessage.value = 'Error processing command';
      } finally {
        isProcessing.value = false;
        currentTranscription.value = '';
      }
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
        console.error('TTS test error:', error);
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
          console.error('Error loading voice settings:', e);
        }
      }

      // Load voice history
      const savedHistory = localStorage.getItem('voice_history');
      if (savedHistory) {
        try {
          voiceHistory.value = JSON.parse(savedHistory);
        } catch (e) {
          console.error('Error loading voice history:', e);
        }
      }
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
      testTTS
    };
  }
};
</script>

<style scoped>
:root {
  --blue-gray-700: #374151;
}

.voice-interface {
  display: flex;
  flex-direction: column;
  height: 100%;
  color: #374151;
  background-color: white;
  overflow-y: auto;
  max-height: calc(100vh - 200px);
  padding: 20px;
}

.voice-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: auto auto auto;
  gap: 24px;
  height: 100%;
}

.voice-visualization {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  padding: 32px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.waveform-container {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 80px;
}

.wave-bar {
  width: 4px;
  background: linear-gradient(to top, #4facfe, #00f2fe);
  border-radius: 2px;
  height: 20px;
  transition: height 0.3s ease;
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
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.1);
  border: 3px solid rgba(99, 102, 241, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}

.voice-status-circle.listening {
  border-color: #10b981;
  background: rgba(16, 185, 129, 0.2);
  animation: listeningPulse 2s ease-in-out infinite;
}

.voice-status-circle.processing {
  border-color: #f59e0b;
  background: rgba(245, 158, 11, 0.2);
  animation: processingRotate 1s linear infinite;
}

.voice-status-circle.speaking {
  border-color: #3b82f6;
  background: rgba(59, 130, 246, 0.2);
  animation: speakingPulse 0.5s ease-in-out infinite;
}

@keyframes listeningPulse {
  0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); }
  50% { transform: scale(1.05); box-shadow: 0 0 0 20px rgba(16, 185, 129, 0); }
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
  font-size: 32px;
  z-index: 2;
}

.voice-controls {
  display: flex;
  gap: 16px;
  justify-content: center;
  grid-column: 1 / -1;
}

.voice-btn {
  padding: 16px 32px;
  border: none;
  border-radius: 16px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}

.voice-btn.primary {
  background: linear-gradient(135deg, #10b981, #34d399);
  color: white;
}

.voice-btn.secondary {
  background: rgba(99, 102, 241, 0.1);
  color: #374151;
  border: 1px solid rgba(99, 102, 241, 0.2);
}

.voice-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.2);
}

.voice-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.voice-settings {
  padding: 24px;
  background: rgba(248, 250, 252, 0.8);
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.voice-settings h3 {
  margin: 0 0 20px 0;
  font-size: 18px;
  font-weight: 600;
  color: #374151;
}

.setting-group {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.setting-group label {
  font-size: 14px;
  color: #374151;
  min-width: 120px;
  font-weight: 500;
}

.setting-group select {
  background: white;
  border: 1px solid rgba(148, 163, 184, 0.3);
  color: #374151;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 14px;
}

.voice-slider {
  flex: 1;
  max-width: 200px;
  accent-color: #10b981;
}

.voice-history {
  padding: 24px;
  background: rgba(248, 250, 252, 0.8);
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.voice-history h3 {
  margin: 0 0 20px 0;
  font-size: 18px;
  font-weight: 600;
  color: #374151;
}

.history-list {
  max-height: 300px;
  overflow-y: auto;
}

.history-item {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 12px;
  padding: 12px;
  background: rgba(148, 163, 184, 0.1);
  border-radius: 8px;
  margin-bottom: 8px;
  font-size: 14px;
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.command-time {
  color: #6b7280;
  font-size: 12px;
}

.command-text {
  color: #374151;
  font-weight: 500;
}

.command-confidence {
  color: #10b981;
  font-weight: 600;
  font-size: 12px;
}

.voice-status-display {
  grid-column: 1 / -1;
  background: rgba(248, 250, 252, 0.8);
  border-radius: 12px;
  padding: 20px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  color: #374151;
}

.transcription {
  margin-bottom: 12px;
  font-size: 16px;
  color: rgba(255, 255, 255, 0.9);
}

.status-message {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.7);
  font-style: italic;
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
    padding: 12px 24px;
    font-size: 14px;
  }
}
</style>
