import { describe, it, expect } from 'vitest'
import FlagChangeHistory from '../FlagChangeHistory.vue'
import { renderComponent } from '@/test/utils/test-utils'
import type { EnforcementMode } from '@/utils/FeatureFlagsApiClient'

interface HistoryEntry {
  timestamp: string
  mode: EnforcementMode
  changed_by: string
}

describe('FlagChangeHistory', () => {
  const mockHistory: HistoryEntry[] = [
    {
      timestamp: new Date(Date.now() - 3600000).toISOString(),
      mode: 'enforced',
      changed_by: 'admin@example.com',
    },
    {
      timestamp: new Date(Date.now() - 86400000).toISOString(),
      mode: 'log_only',
      changed_by: 'moderator@example.com',
    },
    {
      timestamp: new Date(Date.now() - 604800000).toISOString(),
      mode: 'disabled',
      changed_by: 'developer@example.com',
    },
  ]

  function renderHistory(props = {}) {
    return renderComponent(FlagChangeHistory, {
      props: {
        history: [],
        loading: false,
        ...props,
      },
    })
  }

  describe('Rendering', () => {
    it('renders the component layout', () => {
      renderHistory()
      const container = document.querySelector('.flag-change-history')
      expect(container).not.toBeNull()
    })

    it('renders section header with icon and title', () => {
      renderHistory()
      const header = document.querySelector('.section-header')
      expect(header).not.toBeNull()

      const icon = header?.querySelector('i.fa-history')
      expect(icon).not.toBeNull()
    })
  })

  describe('Empty State', () => {
    it('shows empty state when history is empty', () => {
      renderHistory({ history: [] })
      const emptyState = document.querySelector('.empty-state')
      expect(emptyState).not.toBeNull()
    })

    it('shows empty state icon', () => {
      renderHistory({ history: [] })
      const icon = document.querySelector('.empty-icon i.fa-clock')
      expect(icon).not.toBeNull()
    })
  })

  describe('Loading State', () => {
    it('shows loading state when loading is true and no history', () => {
      renderHistory({ loading: true, history: [] })
      const loadingState = document.querySelector('.loading-state')
      expect(loadingState).not.toBeNull()
    })

    it('hides loading state when history is present', () => {
      renderHistory({ loading: true, history: mockHistory })
      const loadingState = document.querySelector('.loading-state')
      expect(loadingState).toBeNull()
    })
  })

  describe('Timeline Display', () => {
    it('renders timeline when history is present', () => {
      renderHistory({ history: mockHistory })
      const timeline = document.querySelector('.history-timeline')
      expect(timeline).not.toBeNull()
    })

    it('renders correct number of timeline entries', () => {
      renderHistory({ history: mockHistory })
      const entries = document.querySelectorAll('.timeline-entry')
      expect(entries.length).toBe(mockHistory.length)
    })

    it('applies correct mode class to entries', () => {
      renderHistory({ history: mockHistory })
      const entries = document.querySelectorAll('.timeline-entry')

      expect(entries[0]).toHaveClass('enforced')
      expect(entries[1]).toHaveClass('log_only')
      expect(entries[2]).toHaveClass('disabled')
    })

    it('renders timeline markers with correct icons', () => {
      renderHistory({ history: mockHistory })
      const markers = document.querySelectorAll('.marker-dot')

      expect(markers[0]).toHaveClass('enforced')
      expect(markers[1]).toHaveClass('log_only')
      expect(markers[2]).toHaveClass('disabled')
    })

    it('renders mode badges for each entry', () => {
      renderHistory({ history: mockHistory })
      const badges = document.querySelectorAll('.mode-badge')

      expect(badges.length).toBe(mockHistory.length)
      expect(badges[0]).toHaveClass('enforced')
      expect(badges[1]).toHaveClass('log_only')
      expect(badges[2]).toHaveClass('disabled')
    })

    it('renders timeline lines between entries but not after last', () => {
      renderHistory({ history: mockHistory })
      const lines = document.querySelectorAll('.marker-line')

      expect(lines.length).toBe(mockHistory.length - 1)
    })
  })

  describe('Entry Details', () => {
    it('renders changed_by information in each entry', () => {
      renderHistory({ history: mockHistory })
      const changedByElements = document.querySelectorAll('.changed-by')

      expect(changedByElements.length).toBe(mockHistory.length)
      expect(changedByElements[0]).toHaveTextContent('admin@example.com')
      expect(changedByElements[1]).toHaveTextContent('moderator@example.com')
      expect(changedByElements[2]).toHaveTextContent('developer@example.com')
    })

    it('renders relative time for recent changes', () => {
      renderHistory({ history: mockHistory })
      const relativeTimes = document.querySelectorAll('.relative-time')

      expect(relativeTimes.length).toBe(mockHistory.length)
      // First entry should show "about 1 hour ago" or similar
      expect(relativeTimes[0].textContent).toBeTruthy()
    })

    it('shows system author when changed_by is empty', () => {
      const historyWithoutAuthor: HistoryEntry[] = [
        {
          timestamp: new Date().toISOString(),
          mode: 'enforced',
          changed_by: '',
        },
      ]

      renderHistory({ history: historyWithoutAuthor })
      const changedBy = document.querySelector('.changed-by')
      expect(changedBy?.textContent).toContain('system')
    })
  })

  describe('Legend', () => {
    it('shows legend when history is present', () => {
      renderHistory({ history: mockHistory })
      const legend = document.querySelector('.legend')
      expect(legend).not.toBeNull()
    })

    it('hides legend when history is empty', () => {
      renderHistory({ history: [] })
      const legend = document.querySelector('.legend')
      expect(legend).toBeNull()
    })

    it('renders all three mode legend items', () => {
      renderHistory({ history: mockHistory })
      const legendItems = document.querySelectorAll('.legend-item')
      expect(legendItems.length).toBe(3)
    })

    it('legend items have correct mode classes', () => {
      renderHistory({ history: mockHistory })
      const dots = document.querySelectorAll('.legend-dot')

      expect(dots[0]).toHaveClass('disabled')
      expect(dots[1]).toHaveClass('log_only')
      expect(dots[2]).toHaveClass('enforced')
    })
  })

  describe('Timestamp Formatting', () => {
    it('renders formatted timestamps for each entry', () => {
      renderHistory({ history: mockHistory })
      const timestamps = document.querySelectorAll('.timestamp')

      expect(timestamps.length).toBe(mockHistory.length)
      timestamps.forEach((ts) => {
        expect(ts.textContent).toBeTruthy()
        // Should contain date/time elements
        expect(ts.textContent).toMatch(/\d+/)
      })
    })
  })

  describe('Responsive Behavior', () => {
    it('renders timeline markers (desktop view)', () => {
      renderHistory({ history: mockHistory })
      const markers = document.querySelectorAll('.timeline-marker')
      expect(markers.length).toBe(mockHistory.length)
    })
  })
})
