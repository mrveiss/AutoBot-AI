import type { Meta } from '@storybook/vue3';
import FeatureFlagsSettingsPanel from './FeatureFlagsSettingsPanel.vue';
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

const meta = {
  title: 'Components/Settings/FeatureFlagsSettingsPanel',
  component: FeatureFlagsSettingsPanel,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof FeatureFlagsSettingsPanel>;

export default meta;

// The panel fetches its own data on mount; stories render the full
// lifecycle with the network calls hitting the real backend (or MSW mocks).

export const Default: Story = {
  name: 'Default (fetches on mount)',
  render: () => ({
    components: { FeatureFlagsSettingsPanel },
    template: `<FeatureFlagsSettingsPanel />`,
  }),
};

export const LoadingState: Story = {
  name: 'Loading State (render)',
  render: () => ({
    components: { FeatureFlagsSettingsPanel },
    template: `
      <div style="max-width:800px">
        <FeatureFlagsSettingsPanel />
      </div>
    `,
  }),
};

export const InContainer: Story = {
  name: 'Inside Settings Container',
  render: () => ({
    components: { FeatureFlagsSettingsPanel },
    template: `
      <div style="padding:24px;background:var(--bg-primary,#0f0f23);min-height:400px">
        <FeatureFlagsSettingsPanel />
      </div>
    `,
  }),
};

export const NarrowViewport: Story = {
  name: 'Narrow Viewport',
  render: () => ({
    components: { FeatureFlagsSettingsPanel },
    template: `
      <div style="max-width:480px;padding:16px">
        <FeatureFlagsSettingsPanel />
      </div>
    `,
  }),
};
