import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpError, ErrorCode } from "@modelcontextprotocol/sdk/types.js";
import { TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS, CreateProjectArgs } from "./createProjectParams.js";
import { ProjectService } from "../services/ProjectService.js"; // Assuming ProjectService is exported from services/index.js or directly
import { logger } from '../utils/logger.js'; // Assuming logger exists
// Import custom errors if needed for specific mapping
// import { ServiceError } from "../utils/errors.js";

/**
 * Registers the createProject tool with the MCP server.
 *
 * @param server - The McpServer instance.
 * @param projectService - An instance of the ProjectService.
 */
export const createProjectTool = (server: McpServer, projectService: ProjectService): void => {

    // Define the asynchronous function that handles the actual tool logic
    const processRequest = async (args: CreateProjectArgs) => {
        logger.info(`[${TOOL_NAME}] Received request with args:`, args);
        try {
            // Call the service method to create the project
            const newProject = await projectService.createProject(args.projectName);

            // Format the successful response according to MCP standards
            const responsePayload = { project_id: newProject.project_id };
            logger.info(`[${TOOL_NAME}] Project created successfully: ${newProject.project_id}`);

            return {
                content: [{
                    type: "text" as const, // Required type assertion
                    text: JSON.stringify(responsePayload)
                }]
            };
        } catch (error: unknown) {
            // Handle potential errors from the service layer
            logger.error(`[${TOOL_NAME}] Error processing request:`, error);

            // Basic error mapping: Assume internal error unless a specific known error type is caught
            // TODO: Add more specific error mapping if ProjectService throws custom errors
            // (e.g., catch (error instanceof ValidationError) { throw new McpError(ErrorCode.InvalidParams, ...)})
            const message = error instanceof Error ? error.message : 'An unknown error occurred during project creation.';
            throw new McpError(ErrorCode.InternalError, message);
        }
    };

    // Register the tool with the server
    server.tool(TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS, processRequest);

    logger.info(`[${TOOL_NAME}] Tool registered successfully.`);
};
