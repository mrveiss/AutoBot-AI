import type { Meta, StoryObj } from '@storybook/vue3';

const meta = {
  title: 'Introduction/Welcome',
  parameters: {
    layout: 'centered',
  },
} satisfies Meta;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

interface Card {
  name: string;
  description: string;
  href: string;
}

const baseCards: Card[] = [
  { name: 'BaseButton', description: 'Interactive button component with variants and states', href: '?path=/docs/components-base-basebutton--docs' },
  { name: 'BaseInput', description: 'Form input component with validation and helpers', href: '?path=/docs/components-base-baseinput--docs' },
  { name: 'BaseCard', description: 'Card container with multiple styling variants', href: '?path=/docs/components-base-basecard--docs' },
  { name: 'BaseBadge', description: 'Badge component for labels and status indicators', href: '?path=/docs/components-base-basebadge--docs' },
  { name: 'BaseTable', description: 'Data table component with sorting and filtering', href: '?path=/docs/components-base-basetable--docs' },
  { name: 'BasePanel', description: 'Collapsible panel component for organizing content', href: '?path=/docs/components-base-basepanel--docs' },
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
  { name: 'DataTable', description: 'Sortable, paginated data table', href: '?path=/docs/components-ui-datatable--docs' },
  { name: 'ProgressBar', description: 'Linear progress indicator with variants', href: '?path=/docs/components-ui-progressbar--docs' },
  { name: 'SkeletonLoader', description: 'Placeholder loading skeleton', href: '?path=/docs/components-ui-skeletonloader--docs' },
  { name: 'StatusBadge', description: 'Compact status indicator badge', href: '?path=/docs/components-ui-statusbadge--docs' },
  { name: 'ThemeToggle', description: 'Theme switcher between light and dark', href: '?path=/docs/components-ui-themetoggle--docs' },
  { name: 'ToastContainer', description: 'Toast notification host container', href: '?path=/docs/components-ui-toastcontainer--docs' },
  { name: 'Icon', description: 'Single-path SVG icon from the ICONS registry', href: '?path=/docs/components-ui-icon--docs' },
  { name: 'DarkModeToggle', description: 'Dark mode toggle switch', href: '?path=/docs/components-ui-darkmodetoggle--docs' },
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
  { name: 'LanguageSwitcher', description: 'Globe icon language switcher for the nav bar', href: '?path=/docs/components-layout-languageswitcher--docs' },
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
              src/components/base/BaseButton.stories.ts<br/>
              src/components/ui/BaseModal.stories.ts<br/>
              src/components/layout/LanguageSwitcher.stories.ts<br/>
              src/stories/IconLibrary.stories.ts<br/>
              src/stories/DesignTokens.stories.ts
            </code>
          </section>
        </div>
      </div>
    `,
  }),
};
