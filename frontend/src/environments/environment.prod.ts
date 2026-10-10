export type OroyaDataMode = 'api' | 'mock';

export const environment = {
  production: true,
  apiBaseUrl: 'http://127.0.0.1:8001/api/v1',
  dataMode: 'api' as OroyaDataMode,
};
