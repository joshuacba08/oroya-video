import { Injectable, inject, signal } from '@angular/core';

import { apiBaseUrlForPort, setApiBaseUrl } from '../api/api-base-url';
import { DesktopService } from './desktop.service';

/** Estado del backend que arranca y vigila la app de escritorio (`backend-status` en Rust). */
export type DesktopBackendStatus = 'external' | 'starting' | 'ready' | 'exited' | 'failed';

export interface DesktopBackendInfo {
  status: DesktopBackendStatus;
  port: number;
  error: string | null;
  logsDir: string | null;
}

@Injectable({ providedIn: 'root' })
export class DesktopBackendService {
  private readonly desktop = inject(DesktopService);

  /** null en el navegador (desarrollo): el backend se arranca a mano en el puerto del entorno. */
  readonly info = signal<DesktopBackendInfo | null>(null);
  /** Aumenta cada vez que el backend queda listo (arranque o reinicio tras una caída). */
  readonly readyCount = signal(0);

  async init(): Promise<void> {
    if (!this.desktop.isDesktop()) {
      return;
    }
    try {
      const { listen } = await import('@tauri-apps/api/event');
      const { invoke } = await import('@tauri-apps/api/core');
      // Primero escuchar y luego leer el estado actual: así no se pierde ningún cambio.
      await listen<DesktopBackendInfo>('backend-status', (event) => this.apply(event.payload));
      this.apply(await invoke<DesktopBackendInfo>('backend_info'));
    } catch (error) {
      console.error('Desktop backend status unavailable', error);
    }
  }

  async revealLogs(): Promise<void> {
    const logsDir = this.info()?.logsDir;
    if (!logsDir || !this.desktop.isDesktop()) {
      return;
    }
    const { revealItemInDir } = await import('@tauri-apps/plugin-opener');
    await revealItemInDir(logsDir);
  }

  private apply(info: DesktopBackendInfo): void {
    if (info.status !== 'external') {
      setApiBaseUrl(apiBaseUrlForPort(info.port));
    }
    const wasReady = this.info()?.status === 'ready';
    this.info.set(info);
    if (info.status === 'ready' && !wasReady) {
      this.readyCount.update((count) => count + 1);
    }
  }
}
