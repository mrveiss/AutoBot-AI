import { z } from 'zod';

export const TOOL_NAME = "listTasks";

export const TOOL_DESCRIPTION = `
Retrieves a list of tasks for a specified project.
Allows optional filtering by task status ('todo', 'in-progress', 'review', 'done').
Provides an option to include nested subtasks directly within their parent task objects in the response.
Returns an array of task objects.
`;

// Re-use enum from addTaskParams or define locally if preferred
const TaskStatusEnum = z.enum(['todo', 'in-progress', 'review', 'done']);

// Zod schema for the parameters, matching FR-003 and listTasksTool.md spec
export const TOOL_PARAMS = z.object({
    project_id: z.string()
        .uuid("The project_id must be a valid UUID.")
        .describe("The unique identifier (UUID) of the project whose tasks are to be listed. This project must exist."), // Required, UUID format

    status: TaskStatusEnum
        .optional()
        .describe("Optional filter to return only tasks matching the specified status."), // Optional, enum

    include_subtasks: z.boolean()
        .optional()
        .default(false) // Default value
        .describe("Optional flag (default false). If true, the response will include subtasks nested within their parent tasks."), // Optional, boolean, default
});

// Define the expected type for arguments based on the Zod schema
export type ListTasksArgs = z.infer<typeof TOOL_PARAMS>;
