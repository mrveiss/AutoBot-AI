export interface SecretData {
  name: string;
  type: string;
  scope: 'global' | 'chat' | string;
  value: string;
  chat_id?: string | null;
  description?: string;
  tags?: string[];
  expires_at?: string | null;
}

export interface SecretUpdateData extends Partial<SecretData> {}

export interface TransferData {
  secret_ids: string[];
  target_scope: string;
  target_chat_id?: string | null;
}

export interface GetSecretsOptions {
  scope?: string;
  chatId?: string | null;
}

export interface GetSecretOptions {
  chatId?: string | null;
}

export interface UpdateSecretOptions {
  chatId?: string | null;
}

export interface DeleteSecretOptions {
  chatId?: string | null;
}

export interface TransferSecretsOptions {
  chatId?: string | null;
}

export interface ValidationResult {
  isValid: boolean;
  errors: string[];
}

export interface FormattedSecret {
  type_label: string;
  scope_label: string;
  created_at_formatted: string;
  expires_at_formatted: string | null;
  updated_at_formatted: string;
  is_expired: boolean;
  chat_id_short: string | null;
  [key: string]: unknown;
}

declare class SecretsApiClient {
  currentChatId: string | null;

  setCurrentChatId(chatId: string | null): void;
  getSecrets(options?: GetSecretsOptions): Promise<unknown>;
  getSecret(secretId: string, options?: GetSecretOptions): Promise<unknown>;
  createSecret(secretData: SecretData): Promise<unknown>;
  updateSecret(secretId: string, updateData: SecretUpdateData, options?: UpdateSecretOptions): Promise<unknown>;
  deleteSecret(secretId: string, options?: DeleteSecretOptions): Promise<unknown>;
  transferSecrets(transferData: TransferData, options?: TransferSecretsOptions): Promise<unknown>;
  getChatCleanupInfo(chatId: string): Promise<unknown>;
  deleteChatSecrets(chatId: string, secretIds?: string[] | null): Promise<unknown>;
  getSecretTypes(): Promise<unknown>;
  getSecretsStats(): Promise<unknown>;
  validateSecretData(secretData: Partial<SecretData>): ValidationResult;
  formatSecretForDisplay(secret: Record<string, unknown>): FormattedSecret;
  groupSecretsByScope(secrets: Record<string, unknown>[]): Record<string, Record<string, unknown>[]>;
  groupSecretsByType(secrets: Record<string, unknown>[]): Record<string, Record<string, unknown>[]>;
  filterSecrets(secrets: Record<string, unknown>[], searchQuery: string): Record<string, unknown>[];
  sortSecrets(
    secrets: Record<string, unknown>[],
    sortBy?: string,
    sortOrder?: 'asc' | 'desc'
  ): Record<string, unknown>[];
  getExpiredSecrets(secrets: Record<string, unknown>[]): Record<string, unknown>[];
  getSecretsExpiringSoon(secrets: Record<string, unknown>[], days?: number): Record<string, unknown>[];
}

export declare const secretsApiClient: SecretsApiClient;
export default SecretsApiClient;
