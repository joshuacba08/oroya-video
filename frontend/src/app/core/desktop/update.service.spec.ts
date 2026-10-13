import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { DesktopBackendService } from './desktop-backend.service';
import { DesktopService } from './desktop.service';
import { UpdateService } from './update.service';

describe('UpdateService', () => {
  function setup(installed = true): UpdateService {
    try {
      localStorage.clear();
    } catch {
      // sin almacenamiento en el entorno de pruebas
    }
    TestBed.configureTestingModule({
      providers: [
        { provide: DesktopService, useValue: { isDesktop: () => installed } },
        {
          provide: DesktopBackendService,
          useValue: { info: signal({ status: installed ? 'ready' : 'external' }) },
        },
      ],
    });
    return TestBed.inject(UpdateService);
  }

  afterEach(() => vi.useRealTimers());

  it('stops announcing a version the user dismissed', () => {
    const updates = setup();
    updates.available.set({ version: '0.5.0', notes: '' });
    expect(updates.visible()).toBe(true);

    updates.dismiss();

    expect(updates.visible()).toBe(false);
    // Una versión posterior vuelve a anunciarse.
    updates.available.set({ version: '0.5.1', notes: '' });
    expect(updates.visible()).toBe(true);
  });

  it('checks on start and then periodically, only once even if started again', () => {
    vi.useFakeTimers();
    const updates = setup();
    const check = vi.spyOn(updates, 'check').mockResolvedValue(null);

    updates.startPeriodicChecks(1000);
    updates.startPeriodicChecks(1000);
    vi.advanceTimersByTime(3000);

    expect(check).toHaveBeenCalledTimes(4);
    updates.stopPeriodicChecks();
  });

  it('never checks outside the installed desktop app', () => {
    const updates = setup(false);
    const check = vi.spyOn(updates, 'check');

    updates.startPeriodicChecks(1000);

    expect(check).not.toHaveBeenCalled();
  });

  it('dismissing also cancels an install waiting for the queue', () => {
    const updates = setup();
    updates.available.set({ version: '0.5.0', notes: '' });
    updates.armInstallWhenIdle();

    updates.dismiss();

    expect(updates.installArmed()).toBe(false);
  });
});
