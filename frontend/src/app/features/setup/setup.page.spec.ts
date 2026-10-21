import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { OroyaDataService } from '../../core/data/oroya-data.service';
import { DesktopBackendService } from '../../core/desktop/desktop-backend.service';
import { DesktopService } from '../../core/desktop/desktop.service';
import { SetupPage } from './setup.page';

const invoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({ invoke: (...args: unknown[]) => invoke(...args) }));

describe('SetupPage AI runtime activation', () => {
  const runtime = { torch_available: true, missing_components: [] };

  function setup(started: Record<string, unknown>) {
    const readyCount = signal(1);
    const data = {
      aiRuntime: vi.fn(() => of(runtime)),
      aiInstallProgress: vi.fn(() => of({ status: 'idle' })),
      installAi: vi.fn(() => of(started)),
      models: vi.fn(() => of([])),
      startup: vi.fn(() => of(null)),
      toErrorVm: vi.fn(),
    };
    invoke.mockReset();
    // El backend vuelve a estar listo un momento después de pedir el reinicio.
    invoke.mockImplementation(async () => {
      setTimeout(() => readyCount.set(2), 10);
    });
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: OroyaDataService, useValue: data },
        { provide: DesktopService, useValue: { isDesktop: () => true } },
        { provide: DesktopBackendService, useValue: { readyCount } },
      ],
    });
    const page = TestBed.runInInjectionContext(() => new SetupPage());
    return { page, data, readyCount };
  }

  it('restarts the backend to load a runtime that is installed and waiting', async () => {
    const { page, data, readyCount } = setup({
      status: 'completed',
      already_installed: false,
      restart_required: true,
    });
    data.aiRuntime.mockClear();

    await page.startAiInstall();

    expect(invoke).toHaveBeenCalledWith('reload_backend');
    expect(readyCount()).toBe(2);
    // Se comprueba el runtime después del reinicio, no antes.
    expect(data.aiRuntime).toHaveBeenCalledTimes(1);
    expect(page.aiRuntime()).toEqual(runtime);
    expect(page.aiActivating()).toBe(false);
  });

  it('does not restart when the runtime was already working', async () => {
    const { page } = setup({ status: 'completed', already_installed: true });

    await page.startAiInstall();

    expect(invoke).not.toHaveBeenCalled();
    expect(page.aiAvailable()).toBe(true);
  });
});
