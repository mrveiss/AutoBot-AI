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

export interface ApiConfig {
  timeout: number;
  retryAttempts: number;
  retryDelay: number;
  knowledgeTimeout: number;
  cacheBustVersion: string;
  disableCache: boolean;
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

  getTimeout(operation?: string): number;

  validateConnection(): Promise<boolean>;

  invalidateCache(): void;

  log(...args: any[]): void;

  getAllServiceUrls(): Promise<{ [key: string]: string }>;

  getBackendConfig(): Promise<AppConfig>;
}

declare const appConfig: AppConfigService;

export default appConfig;
