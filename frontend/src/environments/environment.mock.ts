export type OroyaDataMode = 'api' | 'mock';

export const environment = {
  production: false,
  apiBaseUrl: 'http://127.0.0.1:8001/api/v1',
  // Modo de desarrollo de UI sin backend: datos falsos explícitos.
  dataMode: 'mock' as OroyaDataMode,
};
