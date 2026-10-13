import { Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { Router } from '@angular/router';
import { NButton } from '@neuralangular/angular-ui/button';
import { firstValueFrom } from 'rxjs';

import { BatchService } from '../../core/data/batch.service';
import { OroyaDataService } from '../../core/data/oroya-data.service';
import { translate } from '../../core/i18n/i18n';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import type { InterpolationTarget, ModelVm } from '../../core/models/oroya.models';
import { NotificationService } from '../../core/notifications/notification.service';

type Scale = 'original' | '2x' | '4x';

/** "Procesar en lote": mismos ajustes para todos los proyectos elegidos, en cola y en orden. */
@Component({
  selector: 'ov-batch-dialog',
  standalone: true,
  imports: [NButton, TranslatePipe],
  host: { '(document:keydown.escape)': 'batch.pending() && cancel()' },
  template: `
    @if (batch.pending(); as projects) {
      <div class="ov-dialog-backdrop" (click)="cancel()"></div>
      <form class="ov-batch" role="dialog" aria-modal="true" aria-labelledby="ov-batch-title" (submit)="submit($event)">
        <h2 id="ov-batch-title">{{ 'batch.title' | t: { count: projects.length } }}</h2>
        <ul class="ov-batch__list">
          @for (project of projects; track project.id) {
            <li>{{ project.name }}</li>
          }
        </ul>

        <label>
          <span>{{ 'batch.model' | t }}</span>
          <select [value]="modelId()" (change)="modelId.set($any($event.target).value)">
            @for (model of upscalers(); track model.id) {
              <option [value]="model.slug" [selected]="model.slug === modelId()">
                {{ model.name }}{{ model.installed ? '' : ' — ' + ('batch.notInstalled' | t) }}
              </option>
            }
          </select>
        </label>
        <label>
          <span>{{ 'batch.scale' | t }}</span>
          <select [value]="scale()" (change)="scale.set($any($event.target).value)">
            <option value="original" [selected]="scale() === 'original'">{{ 'workspace.original' | t }}</option>
            <option value="2x" [selected]="scale() === '2x'">2x</option>
            <option value="4x" [selected]="scale() === '4x'">4x</option>
          </select>
        </label>
        <label class="ov-batch__check" [class.ov-batch__check--disabled]="!faceRestoreAvailable()">
          <input
            type="checkbox"
            [checked]="faceRestore() && faceRestoreAvailable()"
            [disabled]="!faceRestoreAvailable()"
            (change)="faceRestore.set($any($event.target).checked)"
          />
          <span>{{ 'workspace.faceRestore' | t }}</span>
        </label>
        <label class="ov-batch__check" [class.ov-batch__check--disabled]="!interpolationAvailable()">
          <input
            type="checkbox"
            [checked]="interpolation() && interpolationAvailable()"
            [disabled]="!interpolationAvailable()"
            (change)="interpolation.set($any($event.target).checked)"
          />
          <span>{{ 'workspace.interpolation' | t }}</span>
          @if (interpolation() && interpolationAvailable()) {
            <select
              class="ov-batch__inline-select"
              [attr.aria-label]="'workspace.interpolationTarget' | t"
              (change)="setInterpolationTarget($any($event.target).value)"
            >
              @for (target of interpolationTargets; track target) {
                <option [value]="target" [selected]="'' + target === '' + interpolationTarget()">
                  {{ target === '2x' ? ('batch.interpolationDouble' | t) : target + ' fps' }}
                </option>
              }
            </select>
          }
        </label>
        <label class="ov-batch__check">
          <input type="checkbox" [checked]="keepAudio()" (change)="keepAudio.set($any($event.target).checked)" />
          <span>{{ 'workspace.keepAudio' | t }}</span>
        </label>

        <div class="ov-batch__actions">
          <n-button variant="secondary" size="sm" (click)="cancel()">{{ 'batch.importOnly' | t }}</n-button>
          <n-button variant="primary" size="sm" type="submit" [disabled]="busy() || !modelId()">
            {{ (busy() ? 'batch.queueing' : 'batch.queue') | t: { count: projects.length } }}
          </n-button>
        </div>
      </form>
    }
  `,
  styles: [
    `
      .ov-dialog-backdrop {
        position: fixed;
        z-index: 900;
        inset: 0;
        background: rgba(0, 0, 0, 0.55);
      }

      .ov-batch {
        position: fixed;
        z-index: 901;
        top: 50%;
        left: 50%;
        display: grid;
        gap: 12px;
        width: min(480px, calc(100vw - 32px));
        max-height: calc(100vh - 48px);
        overflow: auto;
        padding: 22px;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-xl);
        background: var(--n-bg-elevated, #12141f);
        box-shadow: 0 24px 60px rgba(0, 0, 0, 0.5);
        transform: translate(-50%, -50%);
        color: var(--n-text-2);
        font-size: 0.84rem;
      }

      h2 {
        margin: 0;
        color: var(--n-text-1);
        font-size: 1.05rem;
        font-weight: 900;
      }

      .ov-batch__list {
        max-height: 140px;
        margin: 0;
        padding: 8px 12px 8px 28px;
        overflow: auto;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-md);
        color: var(--n-text-1);
      }

      label {
        display: grid;
        gap: 6px;
      }

      select {
        height: 36px;
        padding: 0 10px;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-md);
        background: var(--n-bg-elevated, #12141f);
        color: var(--n-text-1);
        font: inherit;
      }

      .ov-batch__check {
        display: flex;
        align-items: center;
        gap: 10px;
      }

      .ov-batch__check--disabled {
        opacity: 0.55;
      }

      .ov-batch__inline-select {
        height: 28px;
        margin-left: auto;
      }

      .ov-batch__actions {
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        margin-top: 4px;
      }
    `,
  ],
})
export class OvBatchDialogComponent {
  readonly batch = inject(BatchService);
  private readonly data = inject(OroyaDataService);
  private readonly router = inject(Router);
  private readonly notifications = inject(NotificationService);

  readonly models = signal<ModelVm[]>([]);
  readonly modelId = signal('');
  readonly scale = signal<Scale>('2x');
  readonly faceRestore = signal(false);
  readonly keepAudio = signal(true);
  readonly interpolation = signal(false);
  readonly interpolationTarget = signal<InterpolationTarget>('2x');
  readonly interpolationTargets: InterpolationTarget[] = ['2x', 48, 50, 60];
  readonly busy = signal(false);
  readonly upscalers = computed(() =>
    // Habilitados aunque no estén instalados: con el motor de IA, el preflight lo indica por video.
    this.models().filter(
      (model) =>
        model.enabled && model.category !== 'face_restoration' && model.category !== 'frame_interpolation',
    ),
  );
  readonly interpolationAvailable = computed(() =>
    this.models().some((model) => model.category === 'frame_interpolation' && model.installed && model.enabled),
  );
  readonly faceRestoreAvailable = computed(() =>
    this.models().some((model) => model.slug.startsWith('gfpgan') && model.installed && model.enabled),
  );

  constructor() {
    // Al abrir: ajustes del primer proyecto (los nuevos ya traen los últimos usados).
    effect(() => {
      const projects = this.batch.pending();
      if (projects?.length) {
        untracked(() => void this.prefill(projects[0].id));
      }
    });
  }

  private async prefill(projectId: string): Promise<void> {
    try {
      const [models, detail] = await Promise.all([
        firstValueFrom(this.data.models()),
        firstValueFrom(this.data.projectDetail(projectId)),
      ]);
      this.models.set(models);
      const enhancement = detail.project.enhancement_config as Record<string, unknown>;
      const exportConfig = detail.project.export_config as Record<string, unknown>;
      const faceRestore = enhancement['face_restore'] as { enabled?: boolean } | undefined;
      const preferred = String(enhancement['model_id'] ?? '');
      this.modelId.set(
        this.upscalers().some((model) => model.slug === preferred)
          ? preferred
          : (this.upscalers()[0]?.slug ?? ''),
      );
      this.scale.set((['original', '2x', '4x'] as Scale[]).find((v) => v === enhancement['scale']) ?? '2x');
      this.faceRestore.set(faceRestore?.enabled === true);
      const interpolation = enhancement['interpolation'] as { enabled?: boolean; target_fps?: unknown } | undefined;
      this.interpolation.set(interpolation?.enabled === true);
      this.interpolationTarget.set(
        this.interpolationTargets.find((target) => target === interpolation?.target_fps) ?? '2x',
      );
      this.keepAudio.set(exportConfig['keep_audio'] !== false);
    } catch (error) {
      this.notifications.danger(translate('batch.failedTitle'), this.data.toErrorVm(error).message);
    }
  }

  setInterpolationTarget(value: string): void {
    this.interpolationTarget.set(value === '2x' ? '2x' : (Number(value) as 48 | 50 | 60));
  }

  cancel(): void {
    if (!this.busy()) {
      this.batch.close();
    }
  }

  async submit(event: Event): Promise<void> {
    event.preventDefault();
    const projects = this.batch.pending();
    if (!projects || this.busy()) {
      return;
    }
    this.busy.set(true);
    try {
      const result = await firstValueFrom(
        this.data.queueBatch(
          projects.map((project) => project.id),
          {
            model_id: this.modelId(),
            scale: this.scale(),
            face_restore: { enabled: this.faceRestore() && this.faceRestoreAvailable(), strength: 0.5 },
            interpolation: {
              enabled: this.interpolation() && this.interpolationAvailable(),
              target_fps: this.interpolationTarget(),
            },
          },
          { keep_audio: this.keepAudio(), output_resolution: this.scale() },
        ),
      );
      this.batch.close();
      if (result.skipped.length) {
        this.notifications.show(
          'warning',
          translate('batch.partialTitle', { queued: result.queued_job_ids.length }),
          result.skipped.map((item) => item.reason).join(' · '),
        );
      } else {
        this.notifications.show('success', translate('batch.queuedTitle', { count: result.queued_job_ids.length }), '');
      }
      await this.router.navigateByUrl('/queue');
    } catch (error) {
      this.notifications.danger(translate('batch.failedTitle'), this.data.toErrorVm(error).message);
    } finally {
      this.busy.set(false);
    }
  }
}
