import { environment } from '../../../environments/environment';

/**
 * Base de la API. En escritorio el puerto lo elige la app al arrancar el backend (8001 si
 * está libre) y puede cambiar si el backend se reinicia; en el navegador es el del entorno.
 */
let apiBaseUrl = environment.apiBaseUrl;

export function getApiBaseUrl(): string {
  return apiBaseUrl;
}

export function setApiBaseUrl(url: string): void {
  apiBaseUrl = url.replace(/\/+$/, '');
}

export function apiBaseUrlForPort(port: number): string {
  return `http://127.0.0.1:${port}/api/v1`;
}
