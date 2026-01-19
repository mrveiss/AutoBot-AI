declare class ApiService {
  get(endpoint: string): Promise<any>;
  post(endpoint: string, data: any): Promise<any>;
  put(endpoint: string, data: any): Promise<any>;
  delete(endpoint: string): Promise<any>;
}

export const apiService: ApiService;
export default ApiService;
