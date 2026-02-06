import { z } from 'zod';

export const TOOL_NAME = "showTask";

export const TOOL_DESCRIPTION = `
Retrieves the full details of a single, specific task, including its dependencies and direct subtasks.
Requires the project ID and the task ID.
Returns a task object containing all details if found.
`;

// Zod schema for the parameters, matching FR-004 and showTaskTool.md spec
export const TOOL_PARAMS = z.object({
    project_id: z.string()
        .uuid("The project_id must be a valid UUID.")
        .describe("The unique identifier (UUID) of the project the task belongs to."), // Required, UUID format

    task_id: z.string()
        // Add .uuid() if task IDs are also UUIDs, otherwise keep as string
        .min(1, "Task ID cannot be empty.")
        .describe("The unique identifier of the task to retrieve details for."), // Required, string (or UUID)
});

// Define the expected type for arguments based on the Zod schema
export type ShowTaskArgs = z.infer<typeof TOOL_PARAMS>;
