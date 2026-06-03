import { ref, computed } from 'vue'
import { useApiClient } from '@/plugins/api'

export interface EngagementMetrics {
  timestamp: string
  metrics: Record<string, any>
  feature_popularity: Array<{ feature: string; count: number }>
  most_popular_feature: string | null
}

export function useEngagementMetrics() {
  const api = useApiClient()
  const loading = ref(false)
  const error = ref<string | null>(null)
  const data = ref<EngagementMetrics | null>(null)

  const fetch = async () => {
    loading.value = true
    error.value = null

    try {
      data.value = await api.get<EngagementMetrics>('/analytics/engagement-metrics')
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load engagement metrics'
    } finally {
      loading.value = false
    }
  }

  const totalInteractions = computed(() => {
    return data.value?.metrics?.total_interactions ?? 0
  })

  const avgInteractionsPerFeature = computed(() => {
    return data.value?.metrics?.average_interactions_per_feature ?? 0
  })

  return {
    loading,
    error,
    data,
    fetch,
    totalInteractions,
    avgInteractionsPerFeature
  }
}
