import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpError, ErrorCode } from "@modelcontextprotocol/sdk/types.js";
import { TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS, ExportProjectArgs } from "./exportProjectParams.js";
import { ProjectService } from "../services/ProjectService.js"; // Assuming ProjectService is exported via services/index.js
import { logger } from '../utils/logger.js';
import { NotFoundError } from "../utils/errors.js";

/**
 * Registers the exportProject tool with the MCP server.
 *
 * @param server - The McpServer instance.
 * @param projectService - An instance of the ProjectService.
 */
export const exportProjectTool = (server: McpServer, projectService: ProjectService): void => {

    const processRequest = async (args: ExportProjectArgs) => {
        logger.info(`[${TOOL_NAME}] Received request with args:`, args);
        try {
            // Zod schema ensures format is 'json' if provided, or defaults to 'json'
            const jsonString = await projectService.exportProject(args.project_id);

            // Format the successful response
            logger.info(`[${TOOL_NAME}] Successfully exported project ${args.project_id}`);
            return {
                content: [{
                    type: "text" as const,
                    text: jsonString // Return the JSON string directly
                }]
            };
        } catch (error: unknown) {
            // Handle potential errors
            logger.error(`[${TOOL_NAME}] Error processing request:`, error);

            if (error instanceof NotFoundError) {
                // Project not found
                throw new McpError(ErrorCode.InvalidParams, error.message);
            } else {
                // Generic internal error
                const message = error instanceof Error ? error.message : 'An unknown error occurred while exporting the project.';
                throw new McpError(ErrorCode.InternalError, message);
            }
        }
    };

    // Register the tool with the server
    server.tool(TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS.shape, processRequest);

    logger.info(`[${TOOL_NAME}] Tool registered successfully.`);
};
