import { ref, watch } from 'vue'

const DISPLAY_SETTINGS_KEY = 'autobot_display_settings'

export interface DisplaySettings {
  showThoughts: boolean
  showJson: boolean
  showUtility: boolean
  showPlanning: boolean
  showDebug: boolean
  showSources: boolean
  autoScroll: boolean
}

const getDefaultSettings = (): DisplaySettings => ({
  showThoughts: true,
  showJson: true,
  showUtility: false,
  showPlanning: false,
  showDebug: false,
  showSources: false,
  autoScroll: true
})

const loadDisplaySettings = (): DisplaySettings => {
  try {
    const saved = localStorage.getItem(DISPLAY_SETTINGS_KEY)
    if (saved) {
      return { ...getDefaultSettings(), ...JSON.parse(saved) }
    }
  } catch (error) {
    console.warn('[DisplaySettings] Failed to load settings:', error)
  }
  return getDefaultSettings()
}

const saveDisplaySettings = (settings: DisplaySettings) => {
  try {
    localStorage.setItem(DISPLAY_SETTINGS_KEY, JSON.stringify(settings))
  } catch (error) {
    console.warn('[DisplaySettings] Failed to save settings:', error)
  }
}

// Shared reactive state
const displaySettings = ref<DisplaySettings>(loadDisplaySettings())

// Watch for changes and save to localStorage
watch(displaySettings, (newSettings) => {
  saveDisplaySettings(newSettings)
}, { deep: true })

export function useDisplaySettings() {
  const getSetting = (key: keyof DisplaySettings): boolean => {
    return displaySettings.value[key] ?? false
  }

  const setSetting = (key: keyof DisplaySettings, value: boolean) => {
    displaySettings.value[key] = value
  }

  const toggleSetting = (key: keyof DisplaySettings) => {
    displaySettings.value[key] = !displaySettings.value[key]
  }

  const resetSettings = () => {
    displaySettings.value = getDefaultSettings()
  }

  return {
    displaySettings,
    getSetting,
    setSetting,
    toggleSetting,
    resetSettings
  }
}
