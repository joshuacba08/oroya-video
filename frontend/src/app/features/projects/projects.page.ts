import { AsyncPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { NButton } from '@neuralangular/angular-ui/button';
import { BehaviorSubject, catchError, combineLatest, firstValueFrom, map, of, switchMap } from 'rxjs';

import { BatchService } from '../../core/data/batch.service';
import { ImportService, parseManualPaths } from '../../core/data/import.service';
import { OroyaDataService } from '../../core/data/oroya-data.service';
import { DialogService } from '../../core/dialogs/dialog.service';
import { DesktopService } from '../../core/desktop/desktop.service';
import { translate } from '../../core/i18n/i18n';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import type { ApiErrorVm, ProjectCardVm } from '../../core/models/oroya.models';
import { OvManualPathImportComponent } from '../../shared/ui/ov-manual-path-import.component';
import { OvProjectCardComponent } from '../../shared/ui/ov-project-card.component';

@Component({
  selector: 'app-projects-page',
  standalone: true,
  imports: [AsyncPipe, NButton, OvManualPathImportComponent, OvProjectCardComponent, TranslatePipe],
  templateUrl: './projects.page.html',
  styleUrl: './projects.page.css',
})
export class ProjectsPage {
  private readonly data = inject(OroyaDataService);
  readonly imports = inject(ImportService);
  private readonly batch = inject(BatchService);
  private readonly dialogs = inject(DialogService);
  private readonly desktop = inject(DesktopService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly error = signal<ApiErrorVm | null>(null);
  readonly emptySelection: ReadonlySet<string> = new Set();
  /** Selección para procesar varios proyectos en lote. */
  readonly selectedIds = signal<ReadonlySet<string>>(this.emptySelection);
  readonly manualImportOpen = signal(false);
  private readonly reload$ = new BehaviorSubject(0);
  readonly search$ = this.route.queryParamMap.pipe(map((params) => params.get('search') ?? ''));
  readonly projects$ = combineLatest([this.search$, this.reload$]).pipe(
    switchMap(([search]) => this.data.projects(search || undefined)),
    catchError((error: unknown) => {
      this.error.set(this.data.toErrorVm(error));
      return of(null);
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

  clearSearch(): void {
    void this.router.navigate(['/projects']);
  }

  async renameProject(project: ProjectCardVm): Promise<void> {
    const name = await this.dialogs.prompt({
      title: translate('common.rename'),
      label: translate('projects.renamePrompt'),
      value: project.name,
      confirmLabel: translate('common.rename'),
    });
    if (!name || name === project.name) {
      return;
    }
    await this.runAction(() => firstValueFrom(this.data.updateProject(project.id, { name })));
  }

  async deleteProject(project: ProjectCardVm): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: translate('common.delete'),
      message: translate('projects.deleteConfirm', { name: project.name }),
      confirmLabel: translate('common.delete'),
      danger: true,
    });
    if (!confirmed) {
      return;
    }
    await this.runAction(() => firstValueFrom(this.data.deleteProject(project.id)));
  }

  private async runAction(action: () => Promise<unknown>): Promise<void> {
    try {
      this.error.set(null);
      await action();
      this.reload$.next(Date.now());
    } catch (error) {
      this.error.set(this.data.toErrorVm(error));
    }
  }

  toggleSelected(projectId: string): void {
    const next = new Set(this.selectedIds());
    if (!next.delete(projectId)) {
      next.add(projectId);
    }
    this.selectedIds.set(next);
  }

  processSelected(projects: ProjectCardVm[]): void {
    const selected = projects.filter((project) => this.selectedIds().has(project.id));
    this.batch.open(selected);
    this.selectedIds.set(this.emptySelection);
  }

  async newProject(): Promise<void> {
    if (!this.desktop.isDesktop()) {
      this.manualImportOpen.set(true);
      return;
    }
    const result = await this.imports.importAndContinue(await this.desktop.pickVideos());
    if (result.projects.length) {
      this.reload$.next(Date.now());
    }
  }

  async importPath(value: string): Promise<void> {
    const result = await this.imports.importAndContinue(parseManualPaths(value));
    if (result.projects.length) {
      this.manualImportOpen.set(false);
      this.reload$.next(Date.now());
    }
  }
}
