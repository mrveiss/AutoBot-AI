/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * ThemeSelector.stories.ts - Storybook Story for Theme System
 * Issue #8988: User-Selectable Theme System
 */

import type { Meta, StoryObj } from '@storybook/vue3'
import { useTheme } from '@/composables/useTheme'
import { ref } from 'vue'

const meta = {
  title: 'Theme/Theme System',
  tags: ['autodocs'],
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component:
          'Demonstrates the AutoBot theme system with customizable accent colors. Users can select from dark/light/system themes and choose from 8 accent color presets.',
      },
    },
  },
  render: () => ({
    setup() {
      const {
        theme,
        accentColor,
        setTheme,
        setAccentColor,
        availableThemes,
        availableAccents,
        themeLabels,
        accentLabels,
        accentDescriptions,
        isDark,
      } = useTheme()

      return {
        theme,
        accentColor,
        setTheme,
        setAccentColor,
        availableThemes,
        availableAccents,
        themeLabels,
        accentLabels,
        accentDescriptions,
        isDark,
      }
    },
    template: `
      <div style="padding: 2rem; min-width: 600px;">
        <h1 style="margin-bottom: 1.5rem; color: var(--text-primary);">
          AutoBot Theme System
        </h1>

        <!-- Theme Mode Selector -->
        <div style="margin-bottom: 2rem;">
          <label style="display: block; margin-bottom: 0.5rem; color: var(--text-secondary); font-weight: 500;">
            Theme Mode
          </label>
          <div style="display: flex; gap: 0.5rem;">
            <button
              v-for="t in availableThemes"
              :key="t"
              @click="setTheme(t)"
              :style="{
                padding: '0.5rem 1rem',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--radius-md)',
                background: theme === t ? 'var(--color-primary)' : 'var(--bg-secondary)',
                color: theme === t ? 'var(--text-on-primary)' : 'var(--text-primary)',
                cursor: 'pointer',
                fontWeight: theme === t ? '600' : '400',
                transition: 'var(--transition-all)',
              }"
            >
              {{ themeLabels[t] }}
            </button>
          </div>
        </div>

        <!-- Accent Color Selector -->
        <div style="margin-bottom: 2rem;">
          <label style="display: block; margin-bottom: 0.5rem; color: var(--text-secondary); font-weight: 500;">
            Accent Color
          </label>
          <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem;">
            <button
              v-for="color in availableAccents"
              :key="color"
              @click="setAccentColor(color)"
              :data-accent="color"
              :style="{
                padding: '0.75rem',
                border: accentColor === color ? '2px solid var(--color-primary)' : '1px solid var(--border-default)',
                borderRadius: 'var(--radius-md)',
                background: 'var(--bg-secondary)',
                cursor: 'pointer',
                transition: 'var(--transition-all)',
                textAlign: 'left',
              }"
            >
              <div
                :style="{
                  width: '2rem',
                  height: '2rem',
                  borderRadius: 'var(--radius-default)',
                  background: 'var(--color-primary)',
                  marginBottom: '0.5rem',
                }"
              />
              <div style="color: var(--text-primary); font-weight: 500; font-size: 0.875rem;">
                {{ accentLabels[color] }}
              </div>
            </button>
          </div>
          <p style="margin-top: 0.75rem; color: var(--text-tertiary); font-size: 0.875rem; font-style: italic;">
            {{ accentDescriptions[accentColor] }}
          </p>
        </div>

        <!-- Demo UI Elements -->
        <div style="margin-top: 2rem; padding: 1.5rem; border: 1px solid var(--border-default); border-radius: var(--radius-lg); background: var(--bg-card);">
          <h3 style="margin-bottom: 1rem; color: var(--text-primary);">
            Preview UI Elements
          </h3>

          <div style="display: flex; flex-direction: column; gap: 1rem;">
            <!-- Primary Button -->
            <button
              style="padding: 0.5rem 1rem; background: var(--color-primary); color: var(--text-on-primary); border: none; border-radius: var(--radius-md); cursor: pointer; font-weight: 500; transition: var(--transition-colors);"
              @mouseover="$event.target.style.background = 'var(--color-primary-hover)'"
              @mouseout="$event.target.style.background = 'var(--color-primary)'"
            >
              Primary Button
            </button>

            <!-- Input Field -->
            <input
              type="text"
              placeholder="Input field with focus state"
              style="padding: 0.5rem 0.75rem; background: var(--bg-input); color: var(--text-primary); border: 1px solid var(--border-default); border-radius: var(--radius-md); outline: none; transition: var(--transition-colors);"
              @focus="$event.target.style.borderColor = 'var(--color-primary)'; $event.target.style.boxShadow = 'var(--shadow-focus)'"
              @blur="$event.target.style.borderColor = 'var(--border-default)'; $event.target.style.boxShadow = 'none'"
            />

            <!-- Link -->
            <a
              href="#"
              style="color: var(--color-primary); text-decoration: none; transition: var(--transition-colors);"
              @mouseover="$event.target.style.color = 'var(--color-primary-hover)'"
              @mouseout="$event.target.style.color = 'var(--color-primary)'"
              @click.prevent
            >
              Link with accent color
            </a>

            <!-- Badge -->
            <div>
              <span style="display: inline-block; padding: 0.25rem 0.75rem; background: var(--color-primary-bg); color: var(--color-primary); border-radius: var(--radius-full); font-size: 0.875rem; font-weight: 500;">
                Badge
              </span>
            </div>

            <!-- Info Box -->
            <div style="padding: 1rem; background: var(--color-primary-bg); border-left: 3px solid var(--color-primary); border-radius: var(--radius-default);">
              <p style="margin: 0; color: var(--text-primary); font-size: 0.875rem;">
                This info box uses the current accent color for its border and background.
              </p>
            </div>
          </div>
        </div>

        <!-- Current State -->
        <div style="margin-top: 2rem; padding: 1rem; background: var(--bg-secondary); border-radius: var(--radius-md); font-family: var(--font-mono); font-size: 0.875rem; color: var(--text-secondary);">
          <div>Theme: <strong style="color: var(--text-primary);">{{ theme }}</strong></div>
          <div>Accent: <strong style="color: var(--text-primary);">{{ accentColor }}</strong></div>
          <div>Dark Mode: <strong style="color: var(--text-primary);">{{ isDark ? 'Yes' : 'No' }}</strong></div>
        </div>
      </div>
    `,
  }),
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

/**
 * Interactive demo of the theme system.
 * Try switching between dark/light/system themes and different accent colors.
 */
export const Interactive: Story = {}

/**
 * Dark theme with default blue accent
 */
export const DarkBlue: Story = {
  render: () => ({
    setup() {
      const { setTheme, setAccentColor } = useTheme()
      setTheme('dark')
      setAccentColor('blue')
      return {}
    },
    template: '<div></div>',
  }),
}

/**
 * Light theme with green accent
 */
export const LightGreen: Story = {
  render: () => ({
    setup() {
      const { setTheme, setAccentColor } = useTheme()
      setTheme('light')
      setAccentColor('green')
      return {}
    },
    template: '<div></div>',
  }),
}

/**
 * Dark theme with purple accent
 */
export const DarkPurple: Story = {
  render: () => ({
    setup() {
      const { setTheme, setAccentColor } = useTheme()
      setTheme('dark')
      setAccentColor('purple')
      return {}
    },
    template: '<div></div>',
  }),
}
