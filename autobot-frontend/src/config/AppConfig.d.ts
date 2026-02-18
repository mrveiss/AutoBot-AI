// TypeScript declarations for AppConfig.js

export interface ServiceConfig {
  host?: string;
  port: string;
  protocol: string;
  password?: string;
}

export interface ServicesConfig {
  backend: ServiceConfig;
  redis: ServiceConfig;
  vnc: {
    desktop: ServiceConfig;
    terminal: ServiceConfig;
    playwright: ServiceConfig;
  };
  npu: {
    worker: ServiceConfig;
  };
  ollama: ServiceConfig;
  playwright: ServiceConfig;
}

export interface MachineConfig {
  id: string;
  name: string;
  ip: string;
  role: string;
  icon: string;
}

export interface InfrastructureConfig {
  machines: {
    [key: string]: MachineConfig;
  };
}

/**
 * Operation-specific timeout configuration (Issue #598: SINGLE SOURCE OF TRUTH)
 */
export interface TimeoutsConfig {
  /** Standard API operations (30s) */
  default: number;
  /** Knowledge base / vectorization operations (5min) */
  knowledge: number;
  /** File upload operations (5min) */
  upload: number;
  /** Health check operations (5s) */
  health: number;
  /** Quick operations (5s) */
  short: number;
  /** Long-running operations (2min) */
  long: number;
  /** Analytics/reporting operations (3min) */
  analytics: number;
  /** Search operations (30s) */
  search: number;
}

/**
 * API configuration with centralized timeout management
 */
export interface ApiConfig {
  /** Default timeout for standard API calls */
  timeout: number;
  retryAttempts: number;
  retryDelay: number;
  /** @deprecated Use timeouts.knowledge instead (backward compatibility) */
  knowledgeTimeout: number;
  cacheBustVersion: string;
  disableCache: boolean;
  /** Operation-specific timeouts (Issue #598) */
  timeouts: TimeoutsConfig;
}

export interface FeaturesConfig {
  enableDebug: boolean;
  enableRum: boolean;
  enableWebSockets: boolean;
  enableVncDesktop: boolean;
  enableNpuWorker: boolean;
}

export interface EnvironmentConfig {
  isDev: boolean;
  isProd: boolean;
  mode: string;
  nodeEnv?: string;
}

export interface AppConfig {
  services: ServicesConfig;
  infrastructure: InfrastructureConfig;
  api: ApiConfig;
  features: FeaturesConfig;
  environment: EnvironmentConfig;
}

export interface ServiceUrlOptions {
  timeout?: number;
  cacheBust?: boolean;
  extraParams?: Record<string, string>;
  autoconnect?: boolean;
  password?: string;
  resize?: string;
  reconnect?: boolean;
  quality?: string;
  compression?: string;
}

export interface FetchOptions extends RequestInit {
  timeout?: number;
  cacheBust?: boolean;
}

export declare class AppConfigService {
  serviceDiscovery: any;
  config: AppConfig;
  configLoaded: boolean;
  debugMode: boolean;

  constructor();

  initializeConfig(): AppConfig;

  getServiceUrl(serviceName: string, options?: ServiceUrlOptions): Promise<string>;

  getVncUrl(type?: string, options?: ServiceUrlOptions): Promise<string>;

  getInfrastructureMachines(): { [key: string]: MachineConfig };

  getMachine(machineId: string): MachineConfig;

  getMachinesArray(): MachineConfig[];

  getWebSocketUrl(endpoint?: string): Promise<string>;

  getApiUrl(endpoint?: string, options?: ServiceUrlOptions): Promise<string>;

  fetchApi(endpoint: string, options?: FetchOptions): Promise<Response>;

  loadRemoteConfig(): Promise<void>;

  mergeConfig(remoteConfig: Partial<AppConfig>): void;

  get(path: string, defaultValue?: any): any;

  isFeatureEnabled(featureName: string): boolean;

  /**
   * Get timeout for specific operation (Issue #598: SINGLE SOURCE OF TRUTH)
   * @param operation - Operation type: 'default' | 'knowledge' | 'upload' | 'health' | 'short' | 'long' | 'analytics' | 'search'
   */
  getTimeout(operation?: keyof TimeoutsConfig): number;

  validateConnection(): Promise<boolean>;

  invalidateCache(): void;

  log(...args: any[]): void;

  getAllServiceUrls(): Promise<{ [key: string]: string }>;

  getBackendConfig(): Promise<AppConfig>;

  /**
   * Get cached frontend config - Issue #677
   * Returns already-loaded config or loads it first (with deduplication)
   */
  getFrontendConfig(): Promise<AppConfig>;

  /**
   * Get project root path from config - Issue #677
   * Convenience method for components that need the project root
   */
  getProjectRoot(): Promise<string | null>;
}

declare const appConfig: AppConfigService;

export default appConfig;
