/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * tailwind.config.js - Tailwind CSS Configuration
 * Issue #704: CSS Design System - Centralized Theming & SSOT Styles
 *
 * This config extends Tailwind with CSS custom properties from design-tokens.css.
 * Use 'autobot-' prefixed classes to reference design system tokens.
 *
 * Example usage:
 *   <div class="bg-autobot-primary text-autobot-text-primary">
 *   <button class="bg-autobot-success hover:bg-autobot-success-hover">
 */

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      /* ============================================
       * COLORS - Map to CSS Custom Properties
       * ============================================ */
      colors: {
        /* Legacy blueGray palette (for backward compatibility) */
        blueGray: {
          50: '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
        },

        /* AutoBot Design System Colors */
        autobot: {
          /* Primary colors */
          'primary': 'var(--color-primary)',
          'primary-hover': 'var(--color-primary-hover)',
          'primary-active': 'var(--color-primary-active)',
          'primary-light': 'var(--color-primary-light)',
          'primary-dark': 'var(--color-primary-dark)',
          'primary-bg': 'var(--color-primary-bg)',

          /* Secondary colors */
          'secondary': 'var(--color-secondary)',
          'secondary-hover': 'var(--color-secondary-hover)',
          'secondary-light': 'var(--color-secondary-light)',

          /* Status colors */
          'success': 'var(--color-success)',
          'success-hover': 'var(--color-success-hover)',
          'success-light': 'var(--color-success-light)',
          'success-bg': 'var(--color-success-bg)',

          'warning': 'var(--color-warning)',
          'warning-hover': 'var(--color-warning-hover)',
          'warning-light': 'var(--color-warning-light)',
          'warning-bg': 'var(--color-warning-bg)',

          'error': 'var(--color-error)',
          'error-hover': 'var(--color-error-hover)',
          'error-light': 'var(--color-error-light)',
          'error-bg': 'var(--color-error-bg)',

          'info': 'var(--color-info)',
          'info-hover': 'var(--color-info-hover)',
          'info-light': 'var(--color-info-light)',
          'info-bg': 'var(--color-info-bg)',

          /* Background colors */
          'bg-primary': 'var(--bg-primary)',
          'bg-secondary': 'var(--bg-secondary)',
          'bg-tertiary': 'var(--bg-tertiary)',
          'bg-elevated': 'var(--bg-elevated)',
          'bg-surface': 'var(--bg-surface)',
          'bg-card': 'var(--bg-card)',
          'bg-input': 'var(--bg-input)',
          'bg-hover': 'var(--bg-hover)',
          'bg-active': 'var(--bg-active)',

          /* Text colors */
          'text-primary': 'var(--text-primary)',
          'text-secondary': 'var(--text-secondary)',
          'text-tertiary': 'var(--text-tertiary)',
          'text-muted': 'var(--text-muted)',
          'text-inverse': 'var(--text-inverse)',
          'text-link': 'var(--text-link)',

          /* Border colors */
          'border': 'var(--border-default)',
          'border-subtle': 'var(--border-subtle)',
          'border-strong': 'var(--border-strong)',

          /* Chart colors */
          'chart-1': 'var(--chart-1)',
          'chart-2': 'var(--chart-2)',
          'chart-3': 'var(--chart-3)',
          'chart-4': 'var(--chart-4)',
          'chart-5': 'var(--chart-5)',
          'chart-6': 'var(--chart-6)',
          'chart-7': 'var(--chart-7)',
          'chart-8': 'var(--chart-8)',
          'chart-9': 'var(--chart-9)',
          'chart-10': 'var(--chart-10)',
        },
      },

      /* ============================================
       * BACKGROUND COLORS (shorthand)
       * ============================================ */
      backgroundColor: {
        'surface': 'var(--bg-surface)',
        'elevated': 'var(--bg-elevated)',
        'card': 'var(--card-bg)',
        'input': 'var(--input-bg)',
      },

      /* ============================================
       * TEXT COLORS (shorthand)
       * ============================================ */
      textColor: {
        'primary': 'var(--text-primary)',
        'secondary': 'var(--text-secondary)',
        'muted': 'var(--text-muted)',
        'inverse': 'var(--text-inverse)',
      },

      /* ============================================
       * BORDER COLORS (shorthand)
       * ============================================ */
      borderColor: {
        'default': 'var(--border-default)',
        'subtle': 'var(--border-subtle)',
        'strong': 'var(--border-strong)',
        'focus': 'var(--border-focus)',
      },

      /* ============================================
       * FONT FAMILY
       * ============================================ */
      fontFamily: {
        'sans': ['var(--font-sans)'],
        'mono': ['var(--font-mono)'],
        'display': ['var(--font-display)'],
      },

      /* ============================================
       * FONT SIZE
       * ============================================ */
      fontSize: {
        'xs': 'var(--text-xs)',
        'sm': 'var(--text-sm)',
        'base': 'var(--text-base)',
        'lg': 'var(--text-lg)',
        'xl': 'var(--text-xl)',
        '2xl': 'var(--text-2xl)',
        '3xl': 'var(--text-3xl)',
        '4xl': 'var(--text-4xl)',
        '5xl': 'var(--text-5xl)',
        '6xl': 'var(--text-6xl)',
      },

      /* ============================================
       * SPACING
       * ============================================ */
      spacing: {
        'xs': 'var(--spacing-xs)',
        'sm': 'var(--spacing-sm)',
        'md': 'var(--spacing-md)',
        'lg': 'var(--spacing-lg)',
        'xl': 'var(--spacing-xl)',
        '2xl': 'var(--spacing-2xl)',
      },

      /* ============================================
       * BORDER RADIUS
       * ============================================ */
      borderRadius: {
        'sm': 'var(--radius-sm)',
        'DEFAULT': 'var(--radius-default)',
        'md': 'var(--radius-md)',
        'lg': 'var(--radius-lg)',
        'xl': 'var(--radius-xl)',
        '2xl': 'var(--radius-2xl)',
        '3xl': 'var(--radius-3xl)',
      },

      /* ============================================
       * BOX SHADOW
       * ============================================ */
      boxShadow: {
        'xs': 'var(--shadow-xs)',
        'sm': 'var(--shadow-sm)',
        'DEFAULT': 'var(--shadow-md)',
        'md': 'var(--shadow-md)',
        'lg': 'var(--shadow-lg)',
        'xl': 'var(--shadow-xl)',
        '2xl': 'var(--shadow-2xl)',
        'inner': 'var(--shadow-inner)',
        'focus': 'var(--shadow-focus)',
        'focus-error': 'var(--shadow-focus-error)',
        'focus-success': 'var(--shadow-focus-success)',
        'xl-soft': '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
      },

      /* ============================================
       * Z-INDEX
       * ============================================ */
      zIndex: {
        'dropdown': 'var(--z-dropdown)',
        'sticky': 'var(--z-sticky)',
        'fixed': 'var(--z-fixed)',
        'modal-backdrop': 'var(--z-modal-backdrop)',
        'modal': 'var(--z-modal)',
        'popover': 'var(--z-popover)',
        'tooltip': 'var(--z-tooltip)',
        'toast': 'var(--z-toast)',
        'max': 'var(--z-maximum)',
      },

      /* ============================================
       * TRANSITION
       * ============================================ */
      transitionDuration: {
        '75': 'var(--duration-75)',
        '100': 'var(--duration-100)',
        '150': 'var(--duration-150)',
        '200': 'var(--duration-200)',
        '300': 'var(--duration-300)',
        '500': 'var(--duration-500)',
        '700': 'var(--duration-700)',
        '1000': 'var(--duration-1000)',
      },

      /* ============================================
       * LAYOUT
       * ============================================ */
      height: {
        'header': 'var(--header-height)',
        'screen-minus-header': 'var(--view-min-height)',
      },
      width: {
        'sidebar': 'var(--sidebar-width)',
        'sidebar-collapsed': 'var(--sidebar-width-collapsed)',
      },
      maxWidth: {
        'content': 'var(--content-max-width)',
      },
      minHeight: {
        'view': 'var(--view-min-height)',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
}
