import { z } from 'zod';

export const TOOL_NAME = "exportProject";

export const TOOL_DESCRIPTION = `
Exports the complete data set for a specified project as a JSON string.
This includes project metadata, all tasks (hierarchically structured), and their dependencies.
Requires the project ID. The format is fixed to JSON for V1.
Returns the JSON string representing the project data.
`;

// Zod schema for the parameters, matching FR-009 and exportProjectTool.md spec
export const TOOL_PARAMS = z.object({
    project_id: z.string()
        .uuid("The project_id must be a valid UUID.")
        .describe("The unique identifier (UUID) of the project to export."), // Required, UUID format

    format: z.literal('json') // Only allow 'json' for V1
        .optional()
        .default('json')
        .describe("Optional format for the export. Currently only 'json' is supported (default)."), // Optional, enum (fixed), default
});

// Define the expected type for arguments based on the Zod schema
export type ExportProjectArgs = z.infer<typeof TOOL_PARAMS>;
