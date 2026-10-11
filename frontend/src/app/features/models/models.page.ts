import { AsyncPipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NButton } from '@neuralangular/angular-ui/button';
import { NIcon } from '@neuralangular/angular-ui/icon';
import { BehaviorSubject, Subscription, catchError, firstValueFrom, of, switchMap } from 'rxjs';

import { OroyaDataService } from '../../core/data/oroya-data.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import type { ApiErrorVm, ModelDownloadVm, ModelVm } from '../../core/models/oroya.models';
import { OvModelCardComponent } from '../../shared/ui/ov-model-card.component';
import { OvSectionHeaderComponent } from '../../shared/ui/ov-section-header.component';

@Component({
  selector: 'app-models-page',
  standalone: true,
  imports: [AsyncPipe, NButton, NIcon, OvModelCardComponent, OvSectionHeaderComponent, TranslatePipe],
  templateUrl: './models.page.html',
  styleUrl: './models.page.css',
})
export class ModelsPage {
  private readonly data = inject(OroyaDataService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly reload$ = new BehaviorSubject(0);
  private readonly downloadSubs: Record<string, Subscription> = {};

  readonly error = signal<ApiErrorVm | null>(null);
  readonly refreshing = signal(false);
  readonly togglingSlug = signal<string | null>(null);
  readonly downloads = signal<Record<string, ModelDownloadVm>>({});
  readonly models$ = this.reload$.pipe(
    switchMap(() => this.data.models()),
    catchError((error: unknown) => {
      this.error.set(this.data.toErrorVm(error));
      return of(null);
    }),
  );

  installed(models: ModelVm[]): ModelVm[] {
    return models.filter((model) => model.installed);
  }

  available(models: ModelVm[]): ModelVm[] {
    return models.filter((model) => !model.installed);
  }

  async refreshModels(): Promise<void> {
    try {
      this.error.set(null);
      this.refreshing.set(true);
      await firstValueFrom(this.data.refreshModels());
      this.reload$.next(Date.now());
    } catch (error) {
      this.error.set(this.data.toErrorVm(error));
    } finally {
      this.refreshing.set(false);
    }
  }

  async toggleEnabled(model: ModelVm): Promise<void> {
    try {
      this.error.set(null);
      this.togglingSlug.set(model.slug);
      await firstValueFrom(this.data.setModelEnabled(model.slug, !model.enabled));
      this.reload$.next(Date.now());
    } catch (error) {
      this.error.set(this.data.toErrorVm(error));
    } finally {
      this.togglingSlug.set(null);
    }
  }

  downloadFor(model: ModelVm): ModelDownloadVm | null {
    return this.downloads()[model.slug] ?? null;
  }

  async startDownload(model: ModelVm): Promise<void> {
    if (this.downloadFor(model)?.status === 'downloading') {
      return;
    }

    try {
      this.error.set(null);
      const started = await firstValueFrom(this.data.downloadModel(model.slug));
      if (started.already_installed) {
        this.reload$.next(Date.now());
        return;
      }
      this.watchDownload(model.slug);
    } catch (error) {
      this.error.set(this.data.toErrorVm(error));
    }
  }

  private watchDownload(slug: string): void {
    this.downloadSubs[slug]?.unsubscribe();
    this.downloadSubs[slug] = this.data
      .pollModelDownload(slug)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (progress) => {
          this.downloads.update((current) => ({
            ...current,
            [slug]: {
              status: progress.status as ModelDownloadVm['status'],
              percent: progress.percent,
              bytesDone: progress.bytes_done,
              bytesTotal: progress.bytes_total ?? undefined,
              errorMessage: progress.error_message ?? undefined,
            },
          }));
          if (progress.status === 'completed' || progress.status === 'failed') {
            this.downloadSubs[slug]?.unsubscribe();
            delete this.downloadSubs[slug];
            if (progress.status === 'completed') {
              this.reload$.next(Date.now());
            }
          }
        },
        error: (error: unknown) => {
          this.error.set(this.data.toErrorVm(error));
          this.downloadSubs[slug]?.unsubscribe();
          delete this.downloadSubs[slug];
        },
      });
  }
}
