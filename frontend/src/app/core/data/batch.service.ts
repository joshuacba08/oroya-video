import { Injectable, signal } from '@angular/core';

import type { ProjectCardVm } from '../models/oroya.models';

/** Abre el diálogo "Procesar en lote" (lo muestra `ov-batch-dialog` en el shell). */
@Injectable({ providedIn: 'root' })
export class BatchService {
  readonly pending = signal<ProjectCardVm[] | null>(null);

  open(projects: ProjectCardVm[]): void {
    if (projects.length) {
      this.pending.set(projects);
    }
  }

  close(): void {
    this.pending.set(null);
  }
}
