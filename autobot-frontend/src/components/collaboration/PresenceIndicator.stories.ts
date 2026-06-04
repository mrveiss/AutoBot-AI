import type { Meta } from '@storybook/vue3';
import PresenceIndicator from './PresenceIndicator.vue';

const meta = {
  title: 'Components/Collaboration/PresenceIndicator',
  component: PresenceIndicator,
  tags: ['autodocs'],
  argTypes: {
    expanded: {
      control: 'boolean',
      description: 'Show expanded view with full user details',
    },
  },
} as Meta<typeof PresenceIndicator>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

export const Compact: Story = {
  name: 'Compact (default)',
  args: {
    expanded: false,
  },
};

export const Expanded: Story = {
  name: 'Expanded view',
  args: {
    expanded: true,
  },
};

export const CompactInHeader: Story = {
  name: 'Compact — embedded in header',
  render: () => ({
    components: { PresenceIndicator },
    template: `
      <div style="display: flex; align-items: center; gap: 12px; padding: 8px 16px; background: #1e1e2e; border-radius: 8px;">
        <span style="color: #cdd6f4; font-size: 14px;">Session: My Workspace</span>
        <PresenceIndicator :expanded="false" />
      </div>
    `,
  }),
};

export const ExpandedPanel: Story = {
  name: 'Expanded — sidebar panel',
  render: () => ({
    components: { PresenceIndicator },
    template: `
      <div style="width: 260px; padding: 12px; background: #1e1e2e; border-radius: 8px;">
        <PresenceIndicator :expanded="true" />
      </div>
    `,
  }),
};

export const BothViews: Story = {
  name: 'Both views side by side',
  render: () => ({
    components: { PresenceIndicator },
    template: `
      <div style="display: flex; gap: 24px; align-items: flex-start; padding: 16px; background: #1e1e2e; border-radius: 8px;">
        <div>
          <p style="color: #6c7086; font-size: 12px; margin-bottom: 8px;">Compact</p>
          <PresenceIndicator :expanded="false" />
        </div>
        <div style="width: 220px;">
          <p style="color: #6c7086; font-size: 12px; margin-bottom: 8px;">Expanded</p>
          <PresenceIndicator :expanded="true" />
        </div>
      </div>
    `,
  }),
};
