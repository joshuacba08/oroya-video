import { AsyncPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { NCard, NCardContent } from '@neuralangular/angular-ui/card';
import { NIcon } from '@neuralangular/angular-ui/icon';

import { BehaviorSubject, catchError, combineLatest, firstValueFrom, map, of, startWith, switchMap } from 'rxjs';

import { ImportService, parseManualPaths, type ImportResult } from '../../core/data/import.service';
import { OroyaDataService } from '../../core/data/oroya-data.service';
import { mapGpu } from '../../core/data/oroya.mappers';
import { DesktopService } from '../../core/desktop/desktop.service';
import { translate } from '../../core/i18n/i18n';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import type {
  ApiErrorVm,
  ModelVm,
  ProjectCardVm,
} from '../../core/models/oroya.models';
import { OvGpuMeterComponent } from '../../shared/ui/ov-gpu-meter.component';
import { OvManualPathImportComponent } from '../../shared/ui/ov-manual-path-import.component';
import { OvProjectCardComponent } from '../../shared/ui/ov-project-card.component';
import { OvSectionHeaderComponent } from '../../shared/ui/ov-section-header.component';

@Component({
  selector: 'app-dashboard-page',
  standalone: true,
  imports: [
    AsyncPipe,
    NCard,
    NCardContent,
    NIcon,
    OvManualPathImportComponent,
    OvGpuMeterComponent,
    OvProjectCardComponent,
    OvSectionHeaderComponent,
    RouterLink,
    TranslatePipe,
  ],
  templateUrl: './dashboard.page.html',
  styleUrl: './dashboard.page.css',
})
export class DashboardPage {
  private readonly data = inject(OroyaDataService);
  readonly imports = inject(ImportService);
  private readonly desktop = inject(DesktopService);
  private readonly router = inject(Router);

  readonly error = signal<ApiErrorVm | null>(null);
  readonly manualImportOpen = signal(false);
  readonly notice = signal<string | null>(null);
  /** "Import Video" se queda en el dashboard; "New Project" abre el workspace. */
  private openWorkspaceAfterImport = true;
  private readonly reload$ = new BehaviorSubject(0);
  readonly dashboard$ = combineLatest([
    this.reload$.pipe(
      switchMap(() =>
        this.data.pollDashboard((error) =>
          this.error.set(error ? this.data.toErrorVm(error) : null),
        ),
      ),
    ),
    this.data.pollGpu().pipe(startWith(null)),
    // El dashboard solo trae conteos: los nombres de los modelos instalados vienen de /models.
    this.data.models().pipe(
      catchError(() => of([] as ModelVm[])),
      startWith([] as ModelVm[]),
    ),
  ]).pipe(
    map(([dashboard, gpu, models]) => {
      if (!dashboard) {
        return null;
      }
      if (dashboard.source !== 'api') {
        return dashboard;
      }
      return {
        ...dashboard,
        installedModels: models.filter((model) => model.installed),
        system: mapGpu(gpu, dashboard.system),
      };
    }),
  );
  readonly emptyProject: ProjectCardVm = {
    id: 'new',
    name: '',
    model: '',
    duration: '',
    resolution: '',
    status: '',
    statusTone: 'neutral',
    updatedLabel: '',
    thumbnailTone: 'empty',
  };

  async newProject(): Promise<void> {
    await this.pickAndImport(true);
  }

  async importVideo(): Promise<void> {
    await this.pickAndImport(false);
  }

  private async pickAndImport(openWorkspace: boolean): Promise<void> {
    this.openWorkspaceAfterImport = openWorkspace;
    this.notice.set(null);
    if (!this.desktop.isDesktop()) {
      this.manualImportOpen.set(true);
      return;
    }
    await this.finishImport(await this.imports.importAndContinue(await this.desktop.pickVideos(), openWorkspace));
  }

  async importPath(value: string): Promise<void> {
    const result = await this.imports.importAndContinue(
      parseManualPaths(value),
      this.openWorkspaceAfterImport,
    );
    if (result.projects.length) {
      this.manualImportOpen.set(false);
    }
    await this.finishImport(result);
  }

  private async finishImport(result: ImportResult): Promise<void> {
    if (result.projects.length === 1 && !this.openWorkspaceAfterImport) {
      this.notice.set(translate('dashboard.imported', { name: result.projects[0].name }));
    }
    if (result.projects.length) {
      this.reload$.next(Date.now());
    }
  }

  openExports(): void {
    void this.router.navigateByUrl('/exports');
  }
}
