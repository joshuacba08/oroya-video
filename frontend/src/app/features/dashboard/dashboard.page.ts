import { AsyncPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { NCard, NCardContent } from '@neuralangular/angular-ui/card';
import { NIcon } from '@neuralangular/angular-ui/icon';

import { catchError, combineLatest, firstValueFrom, map, of, startWith } from 'rxjs';

import { OroyaDataService } from '../../core/data/oroya-data.service';
import { mapGpu } from '../../core/data/oroya.mappers';
import { DesktopService } from '../../core/desktop/desktop.service';
import type {
  ApiErrorVm,
  ModelVm,
  PickedVideo,
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
  ],
  templateUrl: './dashboard.page.html',
  styleUrl: './dashboard.page.css',
})
export class DashboardPage {
  private readonly data = inject(OroyaDataService);
  private readonly desktop = inject(DesktopService);
  private readonly router = inject(Router);

  readonly error = signal<ApiErrorVm | null>(null);
  readonly manualImportOpen = signal(false);
  readonly importing = signal(false);
  readonly dashboard$ = combineLatest([
    this.data.pollDashboard((error) =>
      this.error.set(error ? this.data.toErrorVm(error) : null),
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
    name: 'New Project',
    model: '',
    duration: '',
    resolution: '',
    status: '',
    statusTone: 'neutral',
    updatedLabel: '',
    thumbnailTone: 'empty',
  };

  async importVideo(): Promise<void> {
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
      this.error.set(null);
      this.importing.set(true);
      const project = await firstValueFrom(this.data.importPickedVideo(selected));
      this.manualImportOpen.set(false);
      await this.router.navigate(['/projects', project.id]);
    } catch (error) {
      this.error.set(this.data.toErrorVm(error));
    } finally {
      this.importing.set(false);
    }
  }

  openExports(): void {
    void this.router.navigateByUrl('/exports');
  }
}
