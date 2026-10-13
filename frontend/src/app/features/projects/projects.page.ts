import { AsyncPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { BehaviorSubject, catchError, combineLatest, firstValueFrom, map, of, switchMap } from 'rxjs';

import { OroyaDataService } from '../../core/data/oroya-data.service';
import { DialogService } from '../../core/dialogs/dialog.service';
import { DesktopService } from '../../core/desktop/desktop.service';
import { translate } from '../../core/i18n/i18n';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import type { ApiErrorVm, PickedVideo, ProjectCardVm } from '../../core/models/oroya.models';
import { OvManualPathImportComponent } from '../../shared/ui/ov-manual-path-import.component';
import { OvProjectCardComponent } from '../../shared/ui/ov-project-card.component';

@Component({
  selector: 'app-projects-page',
  standalone: true,
  imports: [AsyncPipe, OvManualPathImportComponent, OvProjectCardComponent, TranslatePipe],
  templateUrl: './projects.page.html',
  styleUrl: './projects.page.css',
})
export class ProjectsPage {
  private readonly data = inject(OroyaDataService);
  private readonly dialogs = inject(DialogService);
  private readonly desktop = inject(DesktopService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly error = signal<ApiErrorVm | null>(null);
  readonly manualImportOpen = signal(false);
  readonly importing = signal(false);
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
