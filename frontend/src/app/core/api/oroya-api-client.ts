import { environment } from '../../../environments/environment';
import type { HealthResponse } from './api-types';

type QueryValue = string | number | boolean | null | undefined;
type QueryParams = Record<string, QueryValue>;

type ErrorEnvelope = {
  error?: string;
  message?: string;
  details?: Record<string, unknown>;
  request_id?: string;
  timestamp?: string;
};

export class OroyaApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly options: {
      status?: number;
      details?: Record<string, unknown>;
      requestId?: string;
      method?: string;
      path?: string;
    } = {},
  ) {
    super(message);
    this.name = 'OroyaApiError';
  }

  get status(): number | undefined {
    return this.options.status;
  }

  get details(): Record<string, unknown> | undefined {
    return this.options.details;
  }

  get requestId(): string | undefined {
    return this.options.requestId;
  }
}

export class OroyaApiClient {
  private readonly timeoutMs = 12000;

  async healthStrict(): Promise<HealthResponse> {
    const response = await this.get<HealthResponse>('/health', undefined, 3500);

    if (response.service !== 'Oroya Video Backend') {
      throw new OroyaApiError(
        'wrong_backend',
        `Expected Oroya Video Backend at ${environment.apiBaseUrl}, but got "${response.service}".`,
        {
          status: 200,
          details: {
            expected: 'Oroya Video Backend',
            actual: response.service,
          },
          method: 'GET',
          path: '/health',
        },
      );
    }

    return response;
  }

  get<T>(path: string, query?: QueryParams, timeoutMs = this.timeoutMs): Promise<T> {
    return this.request<T>('GET', path, { query, timeoutMs });
  }

  post<T>(path: string, body?: unknown, timeoutMs = this.timeoutMs): Promise<T> {
    return this.request<T>('POST', path, { body, timeoutMs });
  }

  patch<T>(path: string, body?: unknown, timeoutMs = this.timeoutMs): Promise<T> {
    return this.request<T>('PATCH', path, { body, timeoutMs });
  }

  delete<T>(path: string, query?: QueryParams, timeoutMs = this.timeoutMs): Promise<T> {
    return this.request<T>('DELETE', path, { query, timeoutMs });
  }

  resolveUrl(pathOrUrl: string): string {
    // Vacío sigue vacío: una URL a la raíz de la API en un <img> se ve como imagen rota.
    if (!pathOrUrl) {
      return '';
    }

    if (pathOrUrl.startsWith('http://') || pathOrUrl.startsWith('https://')) {
      return pathOrUrl;
    }

    if (!pathOrUrl.startsWith('/')) {
      return `${environment.apiBaseUrl}/${pathOrUrl}`;
    }

    if (pathOrUrl.startsWith('/api/')) {
      const base = environment.apiBaseUrl.replace(/\/api\/v1\/?$/, '');
      return `${base}${pathOrUrl}`;
    }

    return `${environment.apiBaseUrl}${pathOrUrl}`;
  }

  private async request<T>(
    method: string,
    path: string,
    options: {
      body?: unknown;
      query?: QueryParams;
      timeoutMs?: number;
    } = {},
  ): Promise<T> {
    const controller = new AbortController();
    const timeout = globalThis.setTimeout(() => controller.abort(), options.timeoutMs ?? this.timeoutMs);
    const url = this.buildUrl(path, options.query);

    try {
      const response = await fetch(url, {
        method,
        headers: {
          Accept: 'application/json',
          ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw await this.toApiError(response, method, path);
      }

      if (response.status === 204) {
        return undefined as T;
      }

      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof OroyaApiError) {
        throw error;
      }

      const aborted = error instanceof DOMException && error.name === 'AbortError';
      throw new OroyaApiError(
        aborted ? 'request_timeout' : 'network_error',
        aborted
          ? `${method} ${path} timed out.`
          : `${method} ${path} could not reach Oroya backend.`,
        {
          method,
          path,
        },
      );
    } finally {
      globalThis.clearTimeout(timeout);
    }
  }

  private buildUrl(path: string, query?: QueryParams): string {
    const url = new URL(this.resolveUrl(path));

    for (const [key, value] of Object.entries(query ?? {})) {
      if (value !== null && value !== undefined && value !== '') {
        url.searchParams.set(key, String(value));
      }
    }

    return url.toString();
  }

  private async toApiError(
    response: Response,
    method: string,
    path: string,
  ): Promise<OroyaApiError> {
    const requestId = response.headers.get('x-request-id') ?? undefined;
    let envelope: ErrorEnvelope | undefined;

    try {
      envelope = (await response.json()) as ErrorEnvelope;
    } catch {
      envelope = undefined;
    }

    return new OroyaApiError(
      envelope?.error ?? `http_${response.status}`,
      envelope?.message ?? `${method} ${path} failed with ${response.status}.`,
      {
        status: response.status,
        details: envelope?.details,
        requestId: envelope?.request_id ?? requestId,
        method,
        path,
      },
    );
  }
}
