export type OroyaDataMode = 'api' | 'mock';

// Tests E2E (Playwright): backend propio en 8011 para no chocar con el de desarrollo.
export const environment = {
  production: false,
  apiBaseUrl: 'http://127.0.0.1:8011/api/v1',
  dataMode: 'api' as OroyaDataMode,
};
