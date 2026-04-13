import type { Meta, StoryObj } from '@storybook/vue3';
import LoginForm from './LoginForm.vue';

const meta = {
  title: 'Components/Auth/LoginForm',
  component: LoginForm,
  tags: ['autodocs'],
} satisfies Meta<typeof LoginForm>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => ({
    components: { LoginForm },
    template: `
      <div class="min-h-screen flex items-center justify-center bg-gray-100">
        <div class="w-full max-w-md">
          <LoginForm />
        </div>
      </div>
    `,
  }),
};

export const CompactView: Story = {
  render: () => ({
    components: { LoginForm },
    template: '<LoginForm class="p-4 border rounded-lg" />',
  }),
};
