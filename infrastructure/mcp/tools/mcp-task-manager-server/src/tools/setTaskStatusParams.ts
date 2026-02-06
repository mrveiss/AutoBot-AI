import { z } from 'zod';

export const TOOL_NAME = "setTaskStatus";

export const TOOL_DESCRIPTION = `
Updates the status ('todo', 'in-progress', 'review', 'done') for one or more tasks within a specified project.
Requires the project ID, an array of task IDs (1-100), and the target status.
Verifies all tasks exist in the project before updating. Returns the count of updated tasks.
`;

// Re-use enum from other param files
const TaskStatusEnum = z.enum(['todo', 'in-progress', 'review', 'done']);

// Zod schema for the parameters, matching FR-005 and setTaskStatusTool.md spec
export const TOOL_PARAMS = z.object({
    project_id: z.string()
        .uuid("The project_id must be a valid UUID.")
        .describe("The unique identifier (UUID) of the project containing the tasks."), // Required, UUID format

    task_ids: z.array(
            z.string().min(1, "Task ID cannot be empty.")
            // Add .uuid() if task IDs are UUIDs
            .describe("A unique identifier of a task to update.")
        )
        .min(1, "At least one task ID must be provided.")
        .max(100, "Cannot update more than 100 tasks per call.")
        .describe("An array of task IDs (1-100) whose status should be updated."), // Required, array of strings, limits

    status: TaskStatusEnum
        .describe("The target status to set for the specified tasks."), // Required, enum
});

// Define the expected type for arguments based on the Zod schema
export type SetTaskStatusArgs = z.infer<typeof TOOL_PARAMS>;
