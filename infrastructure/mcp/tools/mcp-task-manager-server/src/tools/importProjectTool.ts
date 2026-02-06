import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpError, ErrorCode } from "@modelcontextprotocol/sdk/types.js";
import { TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS, ImportProjectArgs } from "./importProjectParams.js";
import { ProjectService } from "../services/ProjectService.js";
import { logger } from '../utils/logger.js';
import { ValidationError } from "../utils/errors.js"; // Import specific errors

/**
 * Registers the importProject tool with the MCP server.
 *
 * @param server - The McpServer instance.
 * @param projectService - An instance of the ProjectService.
 */
export const importProjectTool = (server: McpServer, projectService: ProjectService): void => {

    const processRequest = async (args: ImportProjectArgs) => {
        logger.info(`[${TOOL_NAME}] Received request (project name: ${args.new_project_name || 'Default'})`);
        try {
            // Call the service method to import the project
            const result = await projectService.importProject(
                args.project_data,
                args.new_project_name
            );

            // Format the successful response
            const responsePayload = { project_id: result.project_id };
            logger.info(`[${TOOL_NAME}] Successfully imported project. New ID: ${result.project_id}`);
            return {
                content: [{
                    type: "text" as const,
                    text: JSON.stringify(responsePayload)
                }]
            };
        } catch (error: unknown) {
            // Handle potential errors
            logger.error(`[${TOOL_NAME}] Error processing request:`, error);

            if (error instanceof ValidationError) {
                // JSON parsing, schema validation, size limit, or other data issues
                throw new McpError(ErrorCode.InvalidParams, error.message);
            } else {
                // Generic internal error (likely database related from the transaction)
                const message = error instanceof Error ? error.message : 'An unknown error occurred during project import.';
                throw new McpError(ErrorCode.InternalError, message);
            }
        }
    };

    // Register the tool with the server
    server.tool(TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS.shape, processRequest);

    logger.info(`[${TOOL_NAME}] Tool registered successfully.`);
};
