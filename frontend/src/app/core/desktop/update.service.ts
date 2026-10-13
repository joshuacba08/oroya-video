import { Injectable, computed, inject, signal } from '@angular/core';

import { DesktopBackendService } from './desktop-backend.service';
import { DesktopService } from './desktop.service';

export type UpdateState = 'idle' | 'checking' | 'upToDate' | 'downloading' | 'installing' | 'error';

export interface AvailableUpdate {
  version: string;
  notes: string;
}

type TauriUpdate = Awaited<ReturnType<typeof import('@tauri-apps/plugin-updater').check>>;

/** Además del arranque, se vuelve a comprobar cada 6 h si la app sigue abierta. */
export const UPDATE_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;
const DISMISSED_KEY = 'oroya.update.dismissed';
const LAST_CHECK_KEY = 'oroya.update.lastCheckedAt';

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Sin almacenamiento (modo privado, previsualización): solo dura la sesión.
  }
}

/**
 * Actualizaciones de la app de escritorio (tauri-plugin-updater + latest.json del release).
 * El instalador va firmado: una actualización manipulada se rechaza.
 */
@Injectable({ providedIn: 'root' })
export class UpdateService {
  private readonly desktop = inject(DesktopService);
  private readonly desktopBackend = inject(DesktopBackendService);
  private update: TauriUpdate = null;
  private timer: ReturnType<typeof setInterval> | null = null;

  readonly available = signal<AvailableUpdate | null>(null);
  readonly state = signal<UpdateState>('idle');
  /** 0-100 durante la descarga. */
  readonly progress = signal(0);
  readonly error = signal<string | null>(null);
  readonly lastCheckedAt = signal<number | null>(Number(readStorage(LAST_CHECK_KEY)) || null);
  /** "Ahora no": esa versión deja de anunciarse (la siguiente sí aparece). */
  readonly dismissedVersion = signal<string | null>(readStorage(DISMISSED_KEY));
  /** Instalación pedida con jobs en cola: se lanza cuando la cola queda vacía. */
  readonly installArmed = signal(false);
  readonly visible = computed(() => {
    const update = this.available();
    return !!update && update.version !== this.dismissedVersion();
  });

  /** Solo la app instalada se actualiza (en desarrollo el backend lo arranca uno mismo). */
  supported(): boolean {
    const status = this.desktopBackend.info()?.status;
    return this.desktop.isDesktop() && !!status && status !== 'external';
  }

  /** Comprueba ahora y después cada `intervalMs` (idempotente). */
  startPeriodicChecks(intervalMs = UPDATE_CHECK_INTERVAL_MS): void {
    if (this.timer || !this.supported()) {
      return;
    }
    void this.check();
    this.timer = setInterval(() => void this.check(), intervalMs);
  }

  stopPeriodicChecks(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  dismiss(): void {
    const version = this.available()?.version;
    if (!version) {
      return;
    }
    this.dismissedVersion.set(version);
    this.installArmed.set(false);
    writeStorage(DISMISSED_KEY, version);
  }

  armInstallWhenIdle(): void {
    this.installArmed.set(true);
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
      const now = Date.now();
      this.lastCheckedAt.set(now);
      writeStorage(LAST_CHECK_KEY, String(now));
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
    if (!update || ['downloading', 'installing'].includes(this.state())) {
      return;
    }
    this.installArmed.set(false);
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
