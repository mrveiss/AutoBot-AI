import type { Meta, StoryObj } from '@storybook/vue3';
import OfflineBanner from './OfflineBanner.vue';

const meta = {
  title: 'Components/UI/OfflineBanner',
  component: OfflineBanner,
  argTypes: {},
} as Meta<typeof OfflineBanner>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { OfflineBanner },
    template: `
      <div>
        <p class="mb-2 text-sm text-gray-500">
          OfflineBanner is driven by <code>useNetworkStatus()</code>. When the
          backend is reachable the banner is hidden — disconnect or block the
          favicon probe to see the alert.
        </p>
        <OfflineBanner />
      </div>
    `,
  }),
};

export const InAppShell: Story = {
  render: () => ({
    components: { OfflineBanner },
    template: `
      <div class="border rounded overflow-hidden">
        <OfflineBanner />
        <main class="p-6">
          <h2 class="text-lg font-semibold">App content</h2>
          <p class="text-sm text-gray-600">
            The banner appears at the top when <code>isOnline</code> becomes false.
          </p>
        </main>
      </div>
    `,
  }),
};
