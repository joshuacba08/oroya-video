import { AsyncPipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { NButton } from '@neuralangular/angular-ui/button';
import { NIcon } from '@neuralangular/angular-ui/icon';
import { NProgress } from '@neuralangular/angular-ui/progress';
import { BehaviorSubject, Subscription, catchError, firstValueFrom, of, switchMap } from 'rxjs';

import type {
  AIInstallProgressResponse,
  AIRuntimeStatusResponse,
} from '../../core/api/api-types';
import { OroyaDataService } from '../../core/data/oroya-data.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import type {
  ApiErrorVm,
  ModelDownloadVm,
  ModelVm,
  StartupVm,
} from '../../core/models/oroya.models';

export const SETUP_DISMISSED_KEY = 'oroya.setup.dismissed';

@Component({
  selector: 'app-setup-page',
  standalone: true,
  imports: [AsyncPipe, NButton, NIcon, NProgress, TranslatePipe],
  templateUrl: './setup.page.html',
  styleUrl: './setup.page.css',
})
export class SetupPage {
  private readonly data = inject(OroyaDataService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly reload$ = new BehaviorSubject(0);
  private readonly downloadSubs: Record<string, Subscription> = {};
  private ffmpegSub: Subscription | undefined;

  readonly error = signal<ApiErrorVm | null>(null);
  readonly ffmpegProgress = signal<ModelDownloadVm | null>(null);
  readonly modelDownloads = signal<Record<string, ModelDownloadVm>>({});
  readonly verifyingAi = signal(false);
  readonly aiAvailable = signal<boolean | null>(null);
  readonly aiRuntime = signal<AIRuntimeStatusResponse | null>(null);
  readonly aiInstall = signal<AIInstallProgressResponse | null>(null);
  private aiInstallSub: Subscription | undefined;

  constructor() {
    this.data
      .aiRuntime()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({ next: (runtime) => this.aiRuntime.set(runtime), error: () => undefined });
    // Si la instalación sigue en curso (p. ej. se navegó fuera de Setup), retomar el progreso.
    this.data
      .aiInstallProgress()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (progress) => {
          if (progress.status === 'installing') {
            this.followAiInstall();
          }
        },
        error: () => undefined,
      });
  }

  async startAiInstall(): Promise<void> {
    try {
      this.error.set(null);
      const started = await firstValueFrom(this.data.installAi());
      if (started.already_installed) {
        await this.verifyAiRuntime(null);
        return;
      }
      this.followAiInstall();
    } catch (startError) {
      this.error.set(this.data.toErrorVm(startError));
    }
  }

  aiInstalling(): boolean {
    return this.aiInstall()?.status === 'installing';
  }

  private followAiInstall(): void {
    this.aiInstallSub?.unsubscribe();
    this.aiInstallSub = this.data
      .pollAiInstall()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((progress) => {
        this.aiInstall.set(progress);
        if (progress.status === 'completed' || progress.status === 'failed') {
          this.aiInstallSub?.unsubscribe();
          if (progress.status === 'completed') {
            void this.verifyAiRuntime(null);
          }
        }
      });
  }

  readonly state$ = this.reload$.pipe(
    switchMap(() => this.data.startup()),
    catchError((startupError: unknown) => {
      this.error.set(this.data.toErrorVm(startupError));
      return of(null);
    }),
  );

  readonly models$ = this.reload$.pipe(
    switchMap(() => this.data.models()),
    catchError(() => of([] as ModelVm[])),
  );

  refresh(): void {
    this.reload$.next(Date.now());
  }

  missingModels(models: ModelVm[]): ModelVm[] {
    return models.filter((model) => !model.installed);
  }

  dismissAndGo(): void {
    localStorage.setItem(SETUP_DISMISSED_KEY, 'true');
    void this.router.navigateByUrl('/dashboard');
  }

  /**
   * Comando PowerShell con el mismo intérprete que ejecuta el backend: los paquetes deben
   * compilarse para su versión de Python. Con `ai_extra_site_dir` (app instalada) se
   * instalan en esa carpeta; en desarrollo, en el propio entorno del backend.
   */
  aiInstallCommand(): string {
    const runtime = this.aiRuntime();
    const python = runtime?.python_executable || 'python';
    const target = runtime?.ai_extra_site_dir ? ` --target "${runtime.ai_extra_site_dir}"` : '';
    const pip = `& "${python}" -m pip install${target}`;
    return (
      `${pip} torch torchvision --index-url https://download.pytorch.org/whl/cu132; `
      + `${pip} basicsr realesrgan opencv-python numpy`
    );
  }

  async copyAiCommand(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.aiInstallCommand());
    } catch {
      // El comando queda visible en pantalla como fallback.
    }
  }

  async startFfmpegDownload(): Promise<void> {
    try {
      this.error.set(null);
      const started = await firstValueFrom(this.data.downloadFfmpeg());
      if (started.already_installed) {
        this.refresh();
        return;
      }

      this.ffmpegSub?.unsubscribe();
      this.ffmpegSub = this.data
        .pollFfmpegDownload()
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (progress) => {
            this.ffmpegProgress.set({
              status: progress.status as ModelDownloadVm['status'],
              percent: progress.percent,
              bytesDone: progress.bytes_done,
              bytesTotal: progress.bytes_total ?? undefined,
              errorMessage: progress.error_message ?? undefined,
            });
            if (progress.status === 'completed' || progress.status === 'failed') {
              this.ffmpegSub?.unsubscribe();
              if (progress.status === 'completed') {
                this.refresh();
              }
            }
          },
          error: (progressError: unknown) => {
            this.error.set(this.data.toErrorVm(progressError));
            this.ffmpegSub?.unsubscribe();
          },
        });
    } catch (startError) {
      this.error.set(this.data.toErrorVm(startError));
    }
  }

  modelDownloadFor(model: ModelVm): ModelDownloadVm | null {
    return this.modelDownloads()[model.slug] ?? null;
  }

  async startModelDownload(model: ModelVm): Promise<void> {
    if (this.modelDownloadFor(model)?.status === 'downloading') {
      return;
    }

    try {
      this.error.set(null);
      const started = await firstValueFrom(this.data.downloadModel(model.slug));
      if (started.already_installed) {
        this.refresh();
        return;
      }

      this.downloadSubs[model.slug]?.unsubscribe();
      this.downloadSubs[model.slug] = this.data
        .pollModelDownload(model.slug)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (progress) => {
            this.modelDownloads.update((current) => ({
              ...current,
              [model.slug]: {
                status: progress.status as ModelDownloadVm['status'],
                percent: progress.percent,
                bytesDone: progress.bytes_done,
                bytesTotal: progress.bytes_total ?? undefined,
                errorMessage: progress.error_message ?? undefined,
              },
            }));
            if (progress.status === 'completed' || progress.status === 'failed') {
              this.downloadSubs[model.slug]?.unsubscribe();
              delete this.downloadSubs[model.slug];
              if (progress.status === 'completed') {
                this.refresh();
              }
            }
          },
          error: (progressError: unknown) => {
            this.error.set(this.data.toErrorVm(progressError));
            this.downloadSubs[model.slug]?.unsubscribe();
            delete this.downloadSubs[model.slug];
          },
        });
    } catch (startError) {
      this.error.set(this.data.toErrorVm(startError));
    }
  }

  async verifyAiRuntime(startup: StartupVm | null): Promise<void> {
    try {
      this.verifyingAi.set(true);
      // El backend registra la carpeta de IA recién instalada sin reiniciar.
      const runtime = await firstValueFrom(this.data.aiRuntime());
      this.aiRuntime.set(runtime);
      this.aiAvailable.set(runtime.torch_available);
      this.refresh();
    } catch (verifyError) {
      this.error.set(this.data.toErrorVm(verifyError));
      this.aiAvailable.set(startup?.aiRuntimeAvailable ?? false);
    } finally {
      this.verifyingAi.set(false);
    }
  }

  formatMb(bytes: number): string {
    return (bytes / 1024 ** 2).toFixed(0);
  }
}
