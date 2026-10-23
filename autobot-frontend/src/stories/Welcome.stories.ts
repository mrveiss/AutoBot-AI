// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';

const meta = {
  title: 'Introduction/Welcome',
  parameters: {
    layout: 'centered',
  },
} satisfies Meta;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

interface Card {
  name: string;
  description: string;
  href: string;
}

const baseCards: Card[] = [
  { name: 'BaseButton', description: 'Interactive button component with variants and states (shared kit)', href: '?path=/docs/kit-basebutton--docs' },
  { name: 'BaseInput', description: 'Text input with label, helper and error text (shared kit)', href: '?path=/docs/kit-baseinput--docs' },
  { name: 'BaseCard', description: 'Card and panel container, variants and sizes (shared kit)', href: '?path=/docs/kit-basecard--docs' },
  { name: 'BaseBadge', description: 'Badge component for labels and status indicators (shared kit)', href: '?path=/docs/kit-basebadge--docs' },
  { name: 'BaseTable', description: 'Data table with sorting, selection and numeric columns (shared kit)', href: '?path=/docs/kit-basetable--docs' },
];

const commonCards: Card[] = [
  { name: 'ErrorBoundary', description: 'Error handling and recovery component', href: '?path=/docs/components-common-errorboundary--docs' },
  { name: 'PermissionDenied', description: 'Permission access denied display', href: '?path=/docs/components-common-permissiondenied--docs' },
];

const featureCards: Card[] = [
  { name: 'ChatHeader', description: 'Header component for chat interface', href: '?path=/docs/components-chat-chatheader--docs' },
  { name: 'LoginForm', description: 'User authentication form', href: '?path=/docs/components-auth-loginform--docs' },
];

const uiCards: Card[] = [
  { name: 'BaseModal', description: 'Modal dialog with backdrop and slot-based body', href: '?path=/docs/components-ui-basemodal--docs' },
  { name: 'ConfirmDialog', description: 'Confirmation dialog with confirm/cancel actions', href: '?path=/docs/components-ui-confirmdialog--docs' },
  { name: 'ProgressBar', description: 'Linear progress indicator with variants', href: '?path=/docs/components-ui-progressbar--docs' },
  { name: 'SkeletonLoader', description: 'Placeholder loading skeleton', href: '?path=/docs/components-ui-skeletonloader--docs' },
  { name: 'StatusBadge', description: 'Compact status indicator badge', href: '?path=/docs/components-ui-statusbadge--docs' },
  { name: 'ThemeToggle', description: 'Theme switcher between light and dark', href: '?path=/docs/components-ui-themetoggle--docs' },
  { name: 'ToastContainer', description: 'Toast notification host container', href: '?path=/docs/components-ui-toastcontainer--docs' },
  { name: 'Icon', description: 'Single-path SVG icon from the ICONS registry', href: '?path=/docs/components-ui-icon--docs' },
  { name: 'OfflineBanner', description: 'Banner shown when network is offline', href: '?path=/docs/components-ui-offlinebanner--docs' },
  { name: 'MessageStatus', description: 'Status indicator for chat messages', href: '?path=/docs/components-ui-messagestatus--docs' },
  { name: 'PreferencesPanel', description: 'User preferences panel', href: '?path=/docs/components-ui-preferencespanel--docs' },
  { name: 'StableLoadingState', description: 'Debounced stable loading state wrapper', href: '?path=/docs/components-ui-stableloadingstate--docs' },
  { name: 'SystemStatusNotification', description: 'System-wide status notification', href: '?path=/docs/components-ui-systemstatusnotification--docs' },
  { name: 'TouchFriendlyButton', description: 'Button optimized for touch interactions', href: '?path=/docs/components-ui-touchfriendlybutton--docs' },
  { name: 'UnifiedLoadingView', description: 'Standardized loading view', href: '?path=/docs/components-ui-unifiedloadingview--docs' },
  { name: 'HostSelector', description: 'Host selection dropdown', href: '?path=/docs/components-ui-hostselector--docs' },
  { name: 'HostSelectionDialog', description: 'Modal dialog for selecting hosts', href: '?path=/docs/components-ui-hostselectiondialog--docs' },
  { name: 'CommandPermissionDialog', description: 'Permission prompt for command execution', href: '?path=/docs/components-ui-commandpermissiondialog--docs' },
];

const layoutCards: Card[] = [
  { name: 'LanguageSwitcher', description: 'Language picker (select or globe menu), shared with the SLM', href: '?path=/docs/kit-languageswitcher--docs' },
  { name: 'NavOverflowMenu', description: 'Overflow "More" menu for nav items', href: '?path=/docs/components-layout-navoverflowmenu--docs' },
];

const designSystemCards: Card[] = [
  { name: 'Icon Library', description: 'Catalog of every icon in the registry, grouped by category', href: '?path=/docs/design-system-icon-library--docs' },
  { name: 'Design Tokens', description: 'Colors, typography, spacing, radius, and shadows', href: '?path=/docs/design-system-design-tokens--docs' },
];

export const Overview: Story = {
  render: () => ({
    setup() {
      return {
        baseCards,
        commonCards,
        featureCards,
        uiCards,
        layoutCards,
        designSystemCards,
      };
    },
    template: `
      <div class="max-w-5xl mx-auto p-8 space-y-8">
        <div>
          <h1 class="text-4xl font-bold mb-2">AutoBot Component Library</h1>
          <p class="text-lg text-gray-600">Vue 3 design system documentation and interactive component showcase</p>
        </div>

        <div class="space-y-6">
          <section>
            <h2 class="text-2xl font-bold mb-4">Base Components</h2>
            <div class="grid grid-cols-2 gap-4">
              <a v-for="c in baseCards" :key="c.name" :href="c.href" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">{{ c.name }}</h3>
                <p class="text-sm text-gray-600">{{ c.description }}</p>
              </a>
            </div>
          </section>

          <section>
            <h2 class="text-2xl font-bold mb-4">UI Primitives</h2>
            <div class="grid grid-cols-2 gap-4">
              <a v-for="c in uiCards" :key="c.name" :href="c.href" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">{{ c.name }}</h3>
                <p class="text-sm text-gray-600">{{ c.description }}</p>
              </a>
            </div>
          </section>

          <section>
            <h2 class="text-2xl font-bold mb-4">Layout</h2>
            <div class="grid grid-cols-2 gap-4">
              <a v-for="c in layoutCards" :key="c.name" :href="c.href" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">{{ c.name }}</h3>
                <p class="text-sm text-gray-600">{{ c.description }}</p>
              </a>
            </div>
          </section>

          <section>
            <h2 class="text-2xl font-bold mb-4">Common Components</h2>
            <div class="grid grid-cols-2 gap-4">
              <a v-for="c in commonCards" :key="c.name" :href="c.href" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">{{ c.name }}</h3>
                <p class="text-sm text-gray-600">{{ c.description }}</p>
              </a>
            </div>
          </section>

          <section>
            <h2 class="text-2xl font-bold mb-4">Feature Components</h2>
            <div class="grid grid-cols-2 gap-4">
              <a v-for="c in featureCards" :key="c.name" :href="c.href" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">{{ c.name }}</h3>
                <p class="text-sm text-gray-600">{{ c.description }}</p>
              </a>
            </div>
          </section>

          <section>
            <h2 class="text-2xl font-bold mb-4">Design System</h2>
            <div class="grid grid-cols-2 gap-4">
              <a v-for="c in designSystemCards" :key="c.name" :href="c.href" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">{{ c.name }}</h3>
                <p class="text-sm text-gray-600">{{ c.description }}</p>
              </a>
            </div>
          </section>

          <section class="bg-blue-50 p-6 rounded-lg">
            <h3 class="text-xl font-bold mb-2">Usage Guide</h3>
            <ul class="space-y-2 text-sm text-gray-700">
              <li>• Click on any component to view its documentation and interactive examples</li>
              <li>• Use the "Docs" tab to read component API documentation</li>
              <li>• Use the "Canvas" tab to interact with component controls</li>
              <li>• Check "Controls" panel to modify props and see live updates</li>
            </ul>
          </section>

          <section class="bg-green-50 p-6 rounded-lg">
            <h3 class="text-xl font-bold mb-2">For Developers</h3>
            <p class="text-sm text-gray-700 mb-3">Component stories are located alongside component files:</p>
            <code class="block bg-white p-3 rounded text-xs text-gray-800 border border-gray-200">
              libs/autobot-ui/src/components/BaseButton.stories.ts<br/>
              libs/autobot-ui/src/components/BaseModal.stories.ts<br/>
              libs/autobot-ui/src/components/LanguageSwitcher.stories.ts<br/>
              src/stories/IconLibrary.stories.ts<br/>
              src/stories/DesignTokens.stories.ts
            </code>
          </section>
        </div>
      </div>
    `,
  }),
};
