// TypeScript declarations for API Service
export interface ChatMessage {
  id: string;
  content: string;
  sender: 'user' | 'assistant' | 'system';
  timestamp: Date;
  status?: 'sending' | 'sent' | 'error';
  type?: 'thought' | 'planning' | 'debug' | 'utility' | 'sources' | 'json' | 'response' | 'message';
  attachments?: Array<{
    id: string;
    name: string;
    type: string;
    size: number;
    url: string;
  }>;
  metadata?: {
    model?: string;
    tokens?: number;
    duration?: number;
    [key: string]: any;
  };
}

export interface ApiResponse {
  success: boolean;
  data?: any;
  error?: string;
  message?: string;
}

export interface WorkflowRequest {
  request: string;
  complexity?: 'low' | 'medium' | 'high';
  context?: Record<string, any>;
}

export interface WorkflowApproval {
  approved: boolean;
  feedback?: string;
  metadata?: Record<string, any>;
}

export interface ResearchQuery {
  query: string;
  focus?: string;
  max_results?: number;
}

export interface SystemStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  services: Record<string, {
    status: 'up' | 'down' | 'unknown';
    lastCheck: number;
    error?: string;
  }>;
  timestamp: number;
}

declare class ApiService {
  // Core HTTP methods
  get(endpoint: string): Promise<any>;
  post(endpoint: string, data?: any): Promise<any>;
  put(endpoint: string, data?: any): Promise<any>;
  delete(endpoint: string): Promise<any>;

  // Chat API
  sendMessage(message: string, options?: any): Promise<ApiResponse>;
  getChatHistory(): Promise<ApiResponse>;
  getChatSessions(): Promise<ApiResponse>;
  getChatMessages(chatId: string): Promise<ApiResponse>;
  deleteChatHistory(chatId: string): Promise<ApiResponse>;

  // Workflow API
  getWorkflows(): Promise<ApiResponse>;
  getWorkflowDetails(workflowId: string): Promise<ApiResponse>;
  getWorkflowStatus(workflowId: string): Promise<ApiResponse>;
  approveWorkflowStep(workflowId: string, approval: WorkflowApproval): Promise<ApiResponse>;
  executeWorkflow(request: WorkflowRequest): Promise<ApiResponse>;
  cancelWorkflow(workflowId: string): Promise<ApiResponse>;
  getPendingApprovals(workflowId: string): Promise<ApiResponse>;

  // Research API
  performResearch(query: string, focus?: string, maxResults?: number): Promise<ApiResponse>;
  researchTools(query: string): Promise<ApiResponse>;
  getInstallationGuide(toolName: string): Promise<ApiResponse>;

  // Settings API
  getSettings(): Promise<ApiResponse>;
  updateSettings(settings: any): Promise<ApiResponse>;
  saveSettings(settings: any): Promise<ApiResponse>;

  // System API
  getSystemStatus(): Promise<SystemStatus>;
  getSystemHealth(): Promise<ApiResponse>;
  getSystemInfo(): Promise<ApiResponse>;

  // Terminal API
  executeCommand(command: string, options?: any): Promise<ApiResponse>;
  interruptProcess(): Promise<ApiResponse>;
  killAllProcesses(): Promise<ApiResponse>;

  // Knowledge Base API
  searchKnowledge(query: string, limit?: number): Promise<ApiResponse>;
  searchKnowledgeBase(query: string, limit?: number): Promise<ApiResponse>;
  addKnowledge(content: string, metadata?: any): Promise<ApiResponse>;
}

export const apiService: ApiService;
export default ApiService;