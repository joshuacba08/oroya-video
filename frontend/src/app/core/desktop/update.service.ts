import { Injectable, inject, signal } from '@angular/core';

import { DesktopBackendService } from './desktop-backend.service';
import { DesktopService } from './desktop.service';

export type UpdateState = 'idle' | 'checking' | 'upToDate' | 'downloading' | 'installing' | 'error';

export interface AvailableUpdate {
  version: string;
  notes: string;
}

type TauriUpdate = Awaited<ReturnType<typeof import('@tauri-apps/plugin-updater').check>>;

/**
 * Actualizaciones de la app de escritorio (tauri-plugin-updater + latest.json del release).
 * El instalador va firmado: una actualización manipulada se rechaza.
 */
@Injectable({ providedIn: 'root' })
export class UpdateService {
  private readonly desktop = inject(DesktopService);
  private readonly desktopBackend = inject(DesktopBackendService);
  private update: TauriUpdate = null;

  readonly available = signal<AvailableUpdate | null>(null);
  readonly state = signal<UpdateState>('idle');
  /** 0-100 durante la descarga. */
  readonly progress = signal(0);
  readonly error = signal<string | null>(null);

  /** Solo la app instalada se actualiza (en desarrollo el backend lo arranca uno mismo). */
  supported(): boolean {
    const status = this.desktopBackend.info()?.status;
    return this.desktop.isDesktop() && !!status && status !== 'external';
  }

  async check(): Promise<AvailableUpdate | null> {
    if (!this.supported() || ['checking', 'downloading', 'installing'].includes(this.state())) {
      return this.available();
    }
    this.state.set('checking');
    this.error.set(null);
    try {
      const { check } = await import('@tauri-apps/plugin-updater');
      this.update = await check();
      const found = this.update
        ? { version: this.update.version, notes: this.update.body ?? '' }
        : null;
      this.available.set(found);
      this.state.set(found ? 'idle' : 'upToDate');
      return found;
    } catch (error) {
      // Sin conexión o sin release publicado todavía: no es un fallo de la app.
      this.state.set('error');
      this.error.set(error instanceof Error ? error.message : String(error));
      return null;
    }
  }

  /**
   * Descarga primero (el backend sigue disponible), después detiene el backend de forma
   * ordenada para que el instalador pueda reemplazar sus archivos, instala y reinicia.
   * Si la instalación falla, el backend vuelve a arrancar.
   */
  async install(): Promise<void> {
    const update = this.update;
    if (!update) {
      return;
    }
    const { invoke } = await import('@tauri-apps/api/core');
    this.error.set(null);
    this.state.set('downloading');
    this.progress.set(0);
    let total = 0;
    let received = 0;
    try {
      await update.download((event) => {
        if (event.event === 'Started') {
          total = event.data.contentLength ?? 0;
        } else if (event.event === 'Progress') {
          received += event.data.chunkLength;
          this.progress.set(total ? Math.min(100, Math.round((received / total) * 100)) : 0);
        }
      });
    } catch (error) {
      this.state.set('error');
      this.error.set(error instanceof Error ? error.message : String(error));
      return;
    }

    this.state.set('installing');
    await invoke('stop_backend_for_update');
    try {
      await update.install();
      const { relaunch } = await import('@tauri-apps/plugin-process');
      await relaunch();
    } catch (error) {
      await invoke('restart_backend');
      this.state.set('error');
      this.error.set(error instanceof Error ? error.message : String(error));
    }
  }
}
