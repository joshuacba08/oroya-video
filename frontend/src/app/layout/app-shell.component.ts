import { AsyncPipe } from '@angular/common';
import { Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { NButton } from '@neuralangular/angular-ui/button';
import { NIcon } from '@neuralangular/angular-ui/icon';
import { NInput } from '@neuralangular/angular-ui/input';
import { NShell } from '@neuralangular/angular-ui/shell';
import {
  NSidebar,
  NSidebarItem,
  NSidebarSection,
} from '@neuralangular/angular-ui/sidebar';
import {
  BehaviorSubject,
  catchError,
  combineLatest,
  firstValueFrom,
  filter,
  map,
  of,
  shareReplay,
  startWith,
  switchMap,
} from 'rxjs';

import { environment } from '../../environments/environment';
import { getApiBaseUrl } from '../core/api/api-base-url';
import { APP_VERSION } from '../core/app-version';
import { OroyaDataService } from '../core/data/oroya-data.service';
import { mapGpu } from '../core/data/oroya.mappers';
import { DesktopBackendService } from '../core/desktop/desktop-backend.service';
import { DesktopService } from '../core/desktop/desktop.service';
import type { TranslationKey } from '../core/i18n/en';
import { translate } from '../core/i18n/i18n';
import { TranslatePipe } from '../core/i18n/translate.pipe';
import type { ApiErrorVm, PickedVideo, StartupVm } from '../core/models/oroya.models';
import { OvGpuMeterComponent } from '../shared/ui/ov-gpu-meter.component';
import { OvManualPathImportComponent } from '../shared/ui/ov-manual-path-import.component';
import { OvNotificationsComponent } from '../shared/ui/ov-notifications.component';

type NavItem = {
  path: string;
  /** Clave de traducción. */
  label: TranslationKey;
  icon: string;
  badge?: string;
};

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    AsyncPipe,
    TranslatePipe,
    NButton,
    NIcon,
    NInput,
    NShell,
    NSidebar,
    NSidebarItem,
    NSidebarSection,
    OvGpuMeterComponent,
    OvManualPathImportComponent,
    OvNotificationsComponent,
    RouterOutlet,
  ],
  templateUrl: './app-shell.component.html',
  styleUrl: './app-shell.component.css',
})
export class AppShellComponent {
  private readonly router = inject(Router);
  private readonly desktop = inject(DesktopService);
  readonly data = inject(OroyaDataService);
  readonly desktopBackend = inject(DesktopBackendService);

  readonly searchQuery = signal('');
  readonly actionError = signal<ApiErrorVm | null>(null);
  readonly manualImportOpen = signal(false);
  readonly importing = signal(false);
  readonly currentUrl = signal(this.router.url);
  // El dashboard no trae datos de GPU: se combinan con /system/gpu para el medidor lateral.
  readonly dashboard$ = combineLatest([
    this.data.dashboard().pipe(catchError(() => of(null))),
    // undefined = aún sin respuesta ("Detectando..."); null = no hay GPU o falló la consulta.
    this.data.pollGpu(10000).pipe(startWith(undefined)),
  ]).pipe(
    map(([dashboard, gpu]) =>
      dashboard && dashboard.source === 'api'
        ? { ...dashboard, system: mapGpu(gpu, dashboard.system) }
        : dashboard,
    ),
  );
  readonly queueBadge$ = this.data.pollQueue().pipe(
    map((jobs) => {
      // La cola también lista pausados/fallidos; el badge cuenta solo trabajo en curso.
      const active = jobs.filter((job) => ['running', 'queued', 'retrying'].includes(job.status));
      return active.length > 0 ? String(active.length) : undefined;
    }),
  );
  private readonly retry$ = new BehaviorSubject(0);
  get apiBaseUrl(): string {
    return getApiBaseUrl();
  }
  readonly appVersion = APP_VERSION;
  readonly startup$ = this.retry$.pipe(
    switchMap(() =>
      this.data.startup().pipe(
        catchError((error: unknown) => {
          const errorVm = this.data.toErrorVm(error);
          const startup: StartupVm = {
            backend: {
              state: 'offline',
              isApi: false,
              isMock: false,
              isOffline: true,
              wrongBackend: false,
              message: errorVm.message,
              warnings: [errorVm.message],
              error: errorVm,
            },
            ready: false,
            appName: 'Oroya Video',
            appVersion: APP_VERSION,
            queueCount: 0,
            interruptedCount: 0,
            warnings: [errorVm.message],
            ffmpegAvailable: false,
            modelsInstalled: 0,
            aiRuntimeAvailable: false,
          };
          return of(startup);
        }),
      ),
    ),
    // La plantilla usa `startup$ | async` en varios sitios: una sola petición de arranque.
    shareReplay({ bufferSize: 1, refCount: false }),
  );

  retryBackend(): void {
    this.retry$.next(Date.now());
  }

  /** Escritorio: el backend arranca, se reinicia tras una caída o no pudo arrancar. */
  readonly desktopBackendPhase = computed<'starting' | 'failed' | null>(() => {
    const status = this.desktopBackend.info()?.status;
    if (status === 'starting' || status === 'exited') {
      return 'starting';
    }
    return status === 'failed' ? 'failed' : null;
  });

  // `startup` es la foto inicial; el estado en vivo detecta también una caída a mitad de sesión.
  showOfflinePanel(startup: StartupVm): boolean {
    const live = this.data.backendStatus();
    return (
      environment.dataMode === 'api' &&
      (live.isOffline || live.wrongBackend || startup.backend.wrongBackend)
    );
  }

  async restartDesktopBackend(): Promise<void> {
    if (!this.desktop.isDesktop()) {
      this.retryBackend();
      return;
    }
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke('restart_backend');
  }

  showSetupBanner(startup: StartupVm): boolean {
    if (!startup.backend.isApi || this.currentUrl().startsWith('/setup')) {
      return false;
    }
    if (localStorage.getItem('oroya.setup.dismissed') === 'true') {
      return false;
    }
    return !startup.ffmpegAvailable || startup.modelsInstalled === 0;
  }

  openSetup(): void {
    void this.router.navigateByUrl('/setup');
  }

  readonly navItems: NavItem[] = [
    { path: '/dashboard', label: 'nav.dashboard', icon: 'home' },
    { path: '/projects', label: 'nav.projects', icon: 'folder-open' },
    { path: '/queue', label: 'nav.queue', icon: 'cpu' },
    { path: '/models', label: 'nav.models', icon: 'box' },
    { path: '/exports', label: 'nav.exports', icon: 'download' },
    { path: '/settings', label: 'nav.settings', icon: 'settings' },
    { path: '/setup', label: 'nav.setup', icon: 'wand-sparkles' },
  ];

  readonly pageTitle = computed(() => {
    const url = this.currentUrl();

    if (url.startsWith('/projects/') && url !== '/projects') {
      return translate('nav.workspace');
    }

    return translate(
      this.navItems.find((item) => url.startsWith(item.path))?.label ?? 'nav.dashboard',
    );
  });

  constructor() {
    // Cada vez que el backend de escritorio queda listo (también tras reiniciarse) se
    // vuelve a cargar el estado de arranque.
    effect(() => {
      if (this.desktopBackend.readyCount() > 0) {
        untracked(() => this.retryBackend());
      }
    });
    this.router.events
      .pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
      .subscribe((event) => this.currentUrl.set(event.urlAfterRedirects));
  }

  active(path: string): boolean {
    const url = this.currentUrl();
    return path === '/dashboard' ? url === path : url.startsWith(path);
  }

  navigate(path: string): void {
    void this.router.navigateByUrl(path);
  }

  async newProject(): Promise<void> {
    if (!this.desktop.isDesktop()) {
      this.manualImportOpen.set(true);
      return;
    }

    const selected = await this.desktop.pickVideo();
    await this.createProjectFromPicked(selected);
  }

  async importPath(path: string): Promise<void> {
    await this.createProjectFromPicked({ kind: 'browser-path', path });
  }

  private async createProjectFromPicked(selected: PickedVideo | null): Promise<void> {
    if (!selected) {
      return;
    }

    try {
      this.actionError.set(null);
      this.importing.set(true);
      const project = await firstValueFrom(this.data.importPickedVideo(selected));
      this.manualImportOpen.set(false);
      await this.router.navigate(['/projects', project.id]);
    } catch (error) {
      this.actionError.set(this.data.toErrorVm(error));
    } finally {
      this.importing.set(false);
    }
  }

  /** La búsqueda es global: desde cualquier página lleva a Proyectos con el filtro. */
  updateSearch(value: string): void {
    this.searchQuery.set(value);
    const onProjects = this.currentUrl().split('?')[0] === '/projects';
    if (!value.trim() && !onProjects) {
      return;
    }
    void this.router.navigate(['/projects'], {
      queryParams: { search: value.trim() || null },
      queryParamsHandling: 'merge',
    });
  }
}
