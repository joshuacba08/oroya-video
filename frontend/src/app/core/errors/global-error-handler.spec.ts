import { TestBed } from '@angular/core/testing';

import { OroyaApiClient, OroyaApiError } from '../api/oroya-api-client';
import { NotificationService } from '../notifications/notification.service';
import { GlobalErrorHandler } from './global-error-handler';

describe('GlobalErrorHandler', () => {
  let post: ReturnType<typeof vi.spyOn>;
  const toast = { danger: vi.fn() };

  beforeEach(() => {
    toast.danger.mockReset();
    post = vi.spyOn(OroyaApiClient.prototype, 'post').mockResolvedValue(undefined);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    TestBed.configureTestingModule({
      providers: [GlobalErrorHandler, { provide: NotificationService, useValue: toast }],
    });
  });

  afterEach(() => vi.restoreAllMocks());

  it('reports unexpected errors to the backend log and warns the user once', () => {
    const handler = TestBed.inject(GlobalErrorHandler);

    handler.handleError(new TypeError('x is undefined'));
    handler.handleError(new TypeError('again'));

    expect(post).toHaveBeenCalledTimes(2);
    expect(post.mock.calls[0][0]).toBe('/system/client-log');
    expect((post.mock.calls[0][1] as { message: string }).message).toBe('TypeError: x is undefined');
    // Un bucle de errores no debe llenar la pantalla de avisos.
    expect(toast.danger).toHaveBeenCalledTimes(1);
  });

  it('ignores API errors, which the pages already show', () => {
    const handler = TestBed.inject(GlobalErrorHandler);

    handler.handleError(new OroyaApiError('network_error', 'offline'));

    expect(post).not.toHaveBeenCalled();
    expect(toast.danger).not.toHaveBeenCalled();
  });
});
