import { AsyncPipe } from '@angular/common';
import {
  Component,
  ElementRef,
  Injector,
  afterNextRender,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { NButton } from '@neuralangular/angular-ui/button';
import { NIcon } from '@neuralangular/angular-ui/icon';
import { BehaviorSubject, catchError, firstValueFrom, of, switchMap } from 'rxjs';

import { OroyaApiError } from '../../core/api/oroya-api-client';
import { OroyaDataService } from '../../core/data/oroya-data.service';
import { translate } from '../../core/i18n/i18n';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import type { ApiErrorVm, ExportVm, ExportsPageVm } from '../../core/models/oroya.models';
import { OvSectionHeaderComponent } from '../../shared/ui/ov-section-header.component';

@Component({
  selector: 'app-exports-page',
  standalone: true,
  imports: [AsyncPipe, NButton, NIcon, OvSectionHeaderComponent, TranslatePipe],
  templateUrl: './exports.page.html',
  styleUrl: './exports.page.css',
})
export class ExportsPage {
  private readonly data = inject(OroyaDataService);
  private readonly injector = inject(Injector);
  private readonly reload$ = new BehaviorSubject(0);
  private readonly player = viewChild<ElementRef<HTMLVideoElement>>('player');

  readonly error = signal<ApiErrorVm | null>(null);
  readonly busyExportId = signal<string | null>(null);
  /** Exportación elegida en el historial; sin elegir, la más reciente. */
  readonly selectedExportId = signal<string | null>(null);
  readonly exports$ = this.reload$.pipe(
    switchMap(() => this.data.exports()),
    catchError((error: unknown) => {
      this.error.set(this.data.toErrorVm(error));
      return of(null);
    }),
  );

  featuredOf(page: ExportsPageVm): ExportVm {
    const selected = this.selectedExportId();
    return page.history.find((item) => item.id === selected) ?? page.featured;
  }

  /** Reproduce en la página; "Abrir exportación" sigue usando el reproductor del sistema. */
  playExport(item: ExportVm): void {
    this.selectedExportId.set(item.id);
    afterNextRender(
      () => {
        const video = this.player()?.nativeElement;
        if (!video) {
          return;
        }
        video.scrollIntoView({ behavior: 'smooth', block: 'center' });
        void video.play().catch(() => undefined);
      },
      { injector: this.injector },
    );
  }

  async openExport(item: ExportVm): Promise<void> {
    await this.runExportAction(item.id, async () => {
      const response = await firstValueFrom(this.data.openExport(item.id));
      if (!response.available) {
        throw new OroyaApiError('export_unavailable', response.message);
      }
      if (!response.opened) {
        throw new OroyaApiError('export_open_failed', response.message);
      }
    });
  }

  async openFolder(item: ExportVm): Promise<void> {
    await this.runExportAction(item.id, async () => {
      const response = await firstValueFrom(this.data.openExportFolder(item.id));
      if (!response.available) {
        throw new OroyaApiError('export_folder_unavailable', response.message);
      }
      if (!response.opened) {
        throw new OroyaApiError('export_open_failed', response.message);
      }
    });
  }

  async deleteExport(item: ExportVm): Promise<void> {
    if (!window.confirm(translate('exports.deleteConfirm', { name: item.fileName }))) {
      return;
    }
    await this.runExportAction(item.id, async () => {
      await firstValueFrom(this.data.deleteExport(item.id));
      if (this.selectedExportId() === item.id) {
        this.selectedExportId.set(null);
      }
      this.reload$.next(Date.now());
    });
  }

  private async runExportAction(exportId: string, action: () => Promise<void>): Promise<void> {
    try {
      this.error.set(null);
      this.busyExportId.set(exportId);
      await action();
    } catch (error) {
      this.error.set(this.data.toErrorVm(error));
    } finally {
      this.busyExportId.set(null);
    }
  }
}
