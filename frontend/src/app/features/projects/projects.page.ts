import { AsyncPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { catchError, firstValueFrom, map, of, switchMap } from 'rxjs';

import { OroyaDataService } from '../../core/data/oroya-data.service';
import { DesktopService } from '../../core/desktop/desktop.service';
import type { ApiErrorVm, PickedVideo, ProjectCardVm } from '../../core/models/oroya.models';
import { OvManualPathImportComponent } from '../../shared/ui/ov-manual-path-import.component';
import { OvProjectCardComponent } from '../../shared/ui/ov-project-card.component';

@Component({
  selector: 'app-projects-page',
  standalone: true,
  imports: [AsyncPipe, OvManualPathImportComponent, OvProjectCardComponent],
  templateUrl: './projects.page.html',
  styleUrl: './projects.page.css',
})
export class ProjectsPage {
  private readonly data = inject(OroyaDataService);
  private readonly desktop = inject(DesktopService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly error = signal<ApiErrorVm | null>(null);
  readonly manualImportOpen = signal(false);
  readonly importing = signal(false);
  readonly projects$ = this.route.queryParamMap.pipe(
    map((params) => params.get('search') ?? undefined),
    switchMap((search) => this.data.projects(search)),
    catchError((error: unknown) => {
      this.error.set(this.data.toErrorVm(error));
      return of(null);
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
}
