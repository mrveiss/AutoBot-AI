// GH#8993: Thinking mode composable — manages extended thinking toggle and budget
// Persists to server API when available; falls back to localStorage.
import { ref, watch } from 'vue'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useThinkingMode')

export interface ThinkingPreferences {
  enabled: boolean
  budget_tokens: number
}

export const BUDGET_STEPS = [1000, 5000, 10000, 32000, 128000] as const
export const BUDGET_STEP_LABELS: Record<number, string> = {
  1000: '1k',
  5000: '5k',
  10000: '10k',
  32000: '32k',
  128000: 'max',
}

const STORAGE_KEY = 'autobot_thinking_preferences'

function readLocalPrefs(): ThinkingPreferences | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function writeLocalPrefs(prefs: ThinkingPreferences): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
  } catch {
    // ignore storage errors
  }
}

async function fetchServerPrefs(sessionId: string): Promise<ThinkingPreferences | null> {
  try {
    const res = await fetch(`${getApiBase()}/sessions/${sessionId}/thinking-preferences`, {
      credentials: 'include',
    })
    if (!res.ok) return null
    const data = await res.json()
    return data?.data ?? data ?? null
  } catch {
    return null
  }
}

async function putServerPrefs(sessionId: string, prefs: ThinkingPreferences): Promise<void> {
  try {
    await fetch(`${getApiBase()}/sessions/${sessionId}/thinking-preferences`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(prefs),
    })
  } catch (err) {
    logger.warn('Could not persist thinking preferences to server:', err)
  }
}

export function useThinkingMode(sessionId: () => string | null) {
  const enabled = ref(false)
  const budgetTokens = ref<number>(10000)

  async function load(): Promise<void> {
    const sid = sessionId()
    const serverPrefs = sid ? await fetchServerPrefs(sid) : null
    const prefs = serverPrefs ?? readLocalPrefs()
    if (prefs) {
      enabled.value = prefs.enabled
      budgetTokens.value = BUDGET_STEPS.includes(prefs.budget_tokens as typeof BUDGET_STEPS[number])
        ? prefs.budget_tokens
        : 10000
    }
  }

  async function persist(): Promise<void> {
    const prefs: ThinkingPreferences = { enabled: enabled.value, budget_tokens: budgetTokens.value }
    writeLocalPrefs(prefs)
    const sid = sessionId()
    if (sid) await putServerPrefs(sid, prefs)
  }

  watch([enabled, budgetTokens], persist, { flush: 'post' })

  function toggle(): void {
    enabled.value = !enabled.value
  }

  function setBudget(tokens: number): void {
    budgetTokens.value = tokens
  }

  return { enabled, budgetTokens, load, toggle, setBudget }
}
