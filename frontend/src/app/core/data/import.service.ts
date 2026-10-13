import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { translate } from '../i18n/i18n';
import { NotificationService } from '../notifications/notification.service';
import { BatchService } from './batch.service';

import type { ApiErrorVm, PickedVideo, ProjectCardVm } from '../models/oroya.models';
import { OroyaDataService } from './oroya-data.service';

export interface ImportFailure {
  path: string;
  error: ApiErrorVm;
}

export interface ImportResult {
  projects: ProjectCardVm[];
  failures: ImportFailure[];
}

/**
 * Importación de uno o varios videos (un proyecto por video). Sustituye la lógica que estaba
 * copiada en el shell, Inicio y Proyectos. Importa de uno en uno: un archivo que falla no
 * impide importar el resto.
 */
@Injectable({ providedIn: 'root' })
export class ImportService {
  private readonly data = inject(OroyaDataService);
  private readonly router = inject(Router);
  private readonly batch = inject(BatchService);
  private readonly notifications = inject(NotificationService);

  readonly importing = signal(false);
  /** Progreso visible durante una importación múltiple. */
  readonly progress = signal<{ done: number; total: number } | null>(null);

  async importAll(picked: PickedVideo[]): Promise<ImportResult> {
    const result: ImportResult = { projects: [], failures: [] };
    if (!picked.length || this.importing()) {
      return result;
    }
    this.importing.set(true);
    this.progress.set({ done: 0, total: picked.length });
    try {
      for (const [index, selection] of picked.entries()) {
        try {
          result.projects.push(await firstValueFrom(this.data.importPickedVideo(selection)));
        } catch (error) {
          result.failures.push({ path: selection.path, error: this.data.toErrorVm(error) });
        }
        this.progress.set({ done: index + 1, total: picked.length });
      }
    } finally {
      this.importing.set(false);
      this.progress.set(null);
    }
    return result;
  }

  /**
   * Importa y sigue: un video abre su Workspace (si `openSingle`); varios abren el diálogo de
   * lote. Los que fallan se avisan sin cancelar el resto.
   */
  async importAndContinue(picked: PickedVideo[], openSingle = true): Promise<ImportResult> {
    const result = await this.importAll(picked);
    if (result.failures.length) {
      this.notifications.danger(
        translate('import.failedTitle', { count: result.failures.length }),
        result.failures
          .map((failure) => `${fileName(failure.path)}: ${failure.error.message}`)
          .join(' · '),
      );
    }
    if (result.projects.length === 1 && openSingle) {
      await this.router.navigate(['/projects', result.projects[0].id]);
    } else if (result.projects.length > 1) {
      this.batch.open(result.projects);
    }
    return result;
  }
}

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}

/** Rutas escritas a mano (navegador de desarrollo): una por línea o separadas por ";". */
export function parseManualPaths(value: string): PickedVideo[] {
  return value
    .split(/[\r\n;]+/)
    .map((path) => path.trim().replace(/^"(.*)"$/, '$1'))
    .filter(Boolean)
    .map((path) => ({ kind: 'browser-path', path }));
}
