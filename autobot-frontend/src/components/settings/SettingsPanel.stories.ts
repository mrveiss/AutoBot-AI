import type { Meta } from '@storybook/vue3';
import SettingsPanel from './SettingsPanel.vue';
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

const meta = {
  title: 'Components/Settings/SettingsPanel',
  component: SettingsPanel,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof SettingsPanel>;

export default meta;

// SettingsPanel is a data-container that fetches settings from the backend
// on mount and uses router-view for sub-routes. Stories render the shell
// with the default empty state visible until the async load resolves.

export const Default: Story = {
  name: 'Default (loading then offline)',
  render: () => ({
    components: { SettingsPanel },
    template: `<SettingsPanel style="height:600px" />`,
  }),
};

export const InFullWidthLayout: Story = {
  name: 'Full-Width Layout',
  render: () => ({
    components: { SettingsPanel },
    template: `
      <div style="width:100%;height:700px;background:var(--bg-primary,#0f0f23)">
        <SettingsPanel />
      </div>
    `,
  }),
};

export const OfflineState: Story = {
  name: 'Offline / Backend Unreachable',
  render: () => ({
    components: { SettingsPanel },
    template: `
      <div style="max-width:1024px;height:600px">
        <p style="color:#94a3b8;font-size:13px;margin-bottom:8px">
          When the backend is unreachable, the panel shows an offline banner.
        </p>
        <SettingsPanel />
      </div>
    `,
  }),
};

export const NarrowSidebar: Story = {
  name: 'Narrow (480px) Sidebar Mode',
  render: () => ({
    components: { SettingsPanel },
    template: `
      <div style="max-width:480px;height:600px;overflow:hidden">
        <SettingsPanel />
      </div>
    `,
  }),
};

export const WithUnsavedChangesContext: Story = {
  name: 'With Unsaved Changes Banner (context)',
  render: () => ({
    components: { SettingsPanel },
    template: `
      <div style="height:600px">
        <p style="color:#f59e0b;font-size:13px;margin-bottom:8px">
          Change a setting to trigger the save/discard action bar at the bottom.
        </p>
        <SettingsPanel />
      </div>
    `,
  }),
};
