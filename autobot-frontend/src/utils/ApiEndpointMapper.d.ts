export interface FallbackResponse {
  ok: boolean;
  status: number;
  fallback: boolean;
  json: () => Promise<unknown>;
  text: () => Promise<string>;
}

export interface FetchOptions extends RequestInit {
  timeout?: number;
}

declare class ApiEndpointMapper {
  cache: Map<string, { data: unknown; timestamp: number }>;
  fallbackData: Map<string, unknown>;
  baseUrl: string;

  fetchWithFallback(endpoint: string, options?: FetchOptions): Promise<Response | FallbackResponse>;
  clearCache(): void;
  clearEndpointCache(endpoint: string): void;
  setFallbackData(endpoint: string, data: unknown): void;
}

declare const apiEndpointMapper: ApiEndpointMapper;
export default apiEndpointMapper;
