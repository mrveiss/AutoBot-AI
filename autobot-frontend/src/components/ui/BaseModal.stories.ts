import type { Meta, StoryObj } from '@storybook/vue3';
import BaseModal from './BaseModal.vue';

const meta = {
  title: 'Components/UI/BaseModal',
  component: BaseModal,
  tags: ['autodocs'],
  argTypes: {
    modelValue: {
      control: 'boolean',
      description: 'v-model binding for modal visibility',
    },
    title: {
      control: 'text',
      description: 'Modal title shown in header',
    },
    size: {
      control: 'select',
      options: ['small', 'medium', 'large'],
      description: 'Modal size: small (500px), medium (900px), large (1200px)',
    },
    showClose: {
      control: 'boolean',
      description: 'Show close button in header',
    },
    closeOnOverlay: {
      control: 'boolean',
      description: 'Close modal when overlay is clicked',
    },
    scrollable: {
      control: 'boolean',
      description: 'Enable scrollable content area',
    },
  },
} satisfies Meta<typeof BaseModal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => ({
    components: { BaseModal },
    template: `
      <BaseModal :model-value="true" title="Default Modal" size="medium">
        <p>This is the default modal body content. Replace with anything you need.</p>
      </BaseModal>
    `,
  }),
};

export const Small: Story = {
  render: () => ({
    components: { BaseModal },
    template: `
      <BaseModal :model-value="true" title="Small Modal" size="small">
        <p>Compact modal for confirmations and short messages.</p>
      </BaseModal>
    `,
  }),
};

export const Large: Story = {
  render: () => ({
    components: { BaseModal },
    template: `
      <BaseModal :model-value="true" title="Large Modal" size="large">
        <p>Wider modal (1200px) for forms or detailed content.</p>
      </BaseModal>
    `,
  }),
};

export const WithActions: Story = {
  render: () => ({
    components: { BaseModal },
    template: `
      <BaseModal :model-value="true" title="Confirm Action" size="small">
        <p>Are you sure you want to proceed with this action?</p>
        <template #actions>
          <button class="px-4 py-2 bg-gray-200 rounded">Cancel</button>
          <button class="px-4 py-2 bg-blue-600 text-white rounded">Confirm</button>
        </template>
      </BaseModal>
    `,
  }),
};

export const NoCloseButton: Story = {
  render: () => ({
    components: { BaseModal },
    template: `
      <BaseModal
        :model-value="true"
        title="Required Action"
        :show-close="false"
        :close-on-overlay="false"
      >
        <p>This modal cannot be dismissed by clicking the close button or overlay.</p>
        <template #actions>
          <button class="px-4 py-2 bg-blue-600 text-white rounded">OK</button>
        </template>
      </BaseModal>
    `,
  }),
};

export const LongContent: Story = {
  render: () => ({
    components: { BaseModal },
    template: `
      <BaseModal :model-value="true" title="Scrollable Content" size="medium" :scrollable="true">
        <div>
          <p v-for="i in 20" :key="i" class="mb-3">
            Paragraph {{ i }}: Lorem ipsum dolor sit amet, consectetur adipiscing elit.
            Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
          </p>
        </div>
      </BaseModal>
    `,
  }),
};
