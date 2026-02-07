import { z } from 'zod';

export const TOOL_NAME = "deleteProject";

export const TOOL_DESCRIPTION = `
Permanently deletes a project and ALL associated tasks and dependencies.
Requires the project ID. This is a highly destructive operation and cannot be undone.
Returns a success confirmation upon completion.
`;

// Zod schema for the parameters, matching FR-013
export const TOOL_PARAMS = z.object({
    project_id: z.string()
        .uuid("The project_id must be a valid UUID.")
        .describe("The unique identifier (UUID) of the project to permanently delete. This project must exist."), // Required, UUID format

});

// Define the expected type for arguments based on the Zod schema
export type DeleteProjectArgs = z.infer<typeof TOOL_PARAMS>;
