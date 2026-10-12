import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { getApiBaseUrl, setApiBaseUrl } from '../api/api-base-url';
import { OroyaApiClient } from '../api/oroya-api-client';
import { DesktopBackendService, type DesktopBackendInfo } from './desktop-backend.service';
import { DesktopService } from './desktop.service';

describe('DesktopBackendService', () => {
  afterEach(() => setApiBaseUrl(environment.apiBaseUrl));

  function setup(): DesktopBackendService {
    TestBed.configureTestingModule({
      providers: [{ provide: DesktopService, useValue: { isDesktop: () => false } }],
    });
    return TestBed.inject(DesktopBackendService);
  }

  function apply(service: DesktopBackendService, info: Partial<DesktopBackendInfo>): void {
    (service as unknown as { apply(info: DesktopBackendInfo): void }).apply({
      status: 'ready',
      port: 8001,
      error: null,
      logsDir: null,
      ...info,
    });
  }

  it('does nothing in the browser', async () => {
    const service = setup();

    await service.init();

    expect(service.info()).toBeNull();
    expect(getApiBaseUrl()).toBe(environment.apiBaseUrl);
  });

  it('points the API client at the port chosen by the desktop app', () => {
    const service = setup();

    apply(service, { status: 'ready', port: 51234 });

    expect(getApiBaseUrl()).toBe('http://127.0.0.1:51234/api/v1');
    expect(new OroyaApiClient().resolveUrl('/videos/1/thumbnail')).toBe(
      'http://127.0.0.1:51234/api/v1/videos/1/thumbnail',
    );
  });

  it('counts every time the backend becomes ready, including after a restart', () => {
    const service = setup();

    apply(service, { status: 'starting' });
    apply(service, { status: 'ready' });
    apply(service, { status: 'ready' });
    apply(service, { status: 'exited' });
    apply(service, { status: 'ready', port: 51000 });

    expect(service.readyCount()).toBe(2);
  });
});
