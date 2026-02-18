import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpError, ErrorCode } from "@modelcontextprotocol/sdk/types.js";
import { TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS, DeleteProjectArgs } from "./deleteProjectParams.js";
import { ProjectService } from "../services/ProjectService.js"; // Assuming ProjectService is exported from index
import { logger } from '../utils/logger.js';
import { NotFoundError } from "../utils/errors.js"; // Import custom errors

/**
 * Registers the deleteProject tool with the MCP server.
 *
 * @param server - The McpServer instance.
 * @param projectService - An instance of the ProjectService.
 */
export const deleteProjectTool = (server: McpServer, projectService: ProjectService): void => {

    const processRequest = async (args: DeleteProjectArgs): Promise<{ content: { type: 'text', text: string }[] }> => {
        logger.warn(`[${TOOL_NAME}] Received request to DELETE project ${args.project_id}. This is a destructive operation.`); // Log deletion intent clearly
        try {
            // Call the service method to delete the project
            const success = await projectService.deleteProject(args.project_id);

            // Format the successful response
            logger.info(`[${TOOL_NAME}] Successfully deleted project ${args.project_id}`);
            return {
                content: [{
                    type: "text" as const,
                    text: JSON.stringify({ success: success }) // Return true if deleted
                }]
            };
        } catch (error: unknown) {
            // Handle potential errors according to systemPatterns.md mapping
            logger.error(`[${TOOL_NAME}] Error processing request:`, error);

            if (error instanceof NotFoundError) {
                // Project not found - Map to InvalidParams as per convention
                throw new McpError(ErrorCode.InvalidParams, error.message);
            } else {
                // Generic internal error
                const message = error instanceof Error ? error.message : 'An unknown error occurred while deleting the project.';
                throw new McpError(ErrorCode.InternalError, message);
            }
        }
    };

    // Register the tool with the server
    server.tool(TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS.shape, processRequest); // Using .shape as this schema doesn't use .refine()

    logger.info(`[${TOOL_NAME}] Tool registered successfully.`);
};
