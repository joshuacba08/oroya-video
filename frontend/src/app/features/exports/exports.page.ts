import { AsyncPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { NButton } from '@neuralangular/angular-ui/button';
import { NIcon } from '@neuralangular/angular-ui/icon';
import { BehaviorSubject, catchError, firstValueFrom, of, switchMap } from 'rxjs';

import { OroyaApiError } from '../../core/api/oroya-api-client';
import { OroyaDataService } from '../../core/data/oroya-data.service';
import type { ApiErrorVm, ExportVm } from '../../core/models/oroya.models';
import { OvSectionHeaderComponent } from '../../shared/ui/ov-section-header.component';

@Component({
  selector: 'app-exports-page',
  standalone: true,
  imports: [AsyncPipe, NButton, NIcon, OvSectionHeaderComponent],
  templateUrl: './exports.page.html',
  styleUrl: './exports.page.css',
})
export class ExportsPage {
  private readonly data = inject(OroyaDataService);
  private readonly reload$ = new BehaviorSubject(0);

  readonly error = signal<ApiErrorVm | null>(null);
  readonly busyExportId = signal<string | null>(null);
  readonly exports$ = this.reload$.pipe(
    switchMap(() => this.data.exports()),
    catchError((error: unknown) => {
      this.error.set(this.data.toErrorVm(error));
      return of(null);
    }),
  );

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
    if (!window.confirm(`Delete "${item.fileName}"? The video file will be removed from disk.`)) {
      return;
    }
    await this.runExportAction(item.id, async () => {
      await firstValueFrom(this.data.deleteExport(item.id));
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
