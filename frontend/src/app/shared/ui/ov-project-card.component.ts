import { Component, input, output, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { NIcon } from '@neuralangular/angular-ui/icon';
import { NProgress } from '@neuralangular/angular-ui/progress';

import { TranslatePipe } from '../../core/i18n/translate.pipe';
import type { ProjectCardVm } from '../../core/models/oroya.models';

@Component({
  selector: 'ov-project-card',
  standalone: true,
  imports: [NIcon, NProgress, RouterLink, TranslatePipe],
  template: `
    <a class="ov-project-card" [class.ov-project-card--empty]="empty()" [routerLink]="empty() ? null : ['/projects', project().id]">
      @if (empty()) {
        <div class="ov-project-card__empty">
          <span><n-icon name="plus" size="md" /></span>
          <strong>{{ 'common.newProject' | t }}</strong>
        </div>
      } @else {
        <div class="ov-project-card__thumb" [class]="'ov-project-card__thumb ov-project-card__thumb--' + project().thumbnailTone">
          @if (project().thumbnailUrl && !thumbnailFailed()) {
            <img
              class="ov-project-card__img"
              [src]="project().thumbnailUrl"
              alt=""
              loading="lazy"
              (error)="thumbnailFailed.set(true)"
            />
          }
          <span class="ov-project-card__dot"></span>
          @if (project().resolution) {
            <span class="ov-project-card__badge">{{ project().resolution }}</span>
          }
        </div>
        <div class="ov-project-card__body">
          <div class="ov-project-card__title">
            <h3>{{ project().name }}</h3>
            @if (actions()) {
              <span class="ov-project-card__actions" role="group" [attr.aria-label]="'projects.actions' | t">
                <button
                  type="button"
                  [title]="'common.rename' | t"
                  [attr.aria-label]="'common.rename' | t"
                  (click)="emit($event, renameRequested)"
                >
                  <n-icon name="pencil" size="xs" />
                </button>
                <button
                  type="button"
                  [title]="'common.delete' | t"
                  [attr.aria-label]="'common.delete' | t"
                  (click)="emit($event, deleteRequested)"
                >
                  <n-icon name="trash-2" size="xs" />
                </button>
              </span>
            }
          </div>
          <p>
            {{ project().model }}
            @if (project().duration) {
              - {{ project().duration }}
            }
          </p>
          <div class="ov-project-card__status" [class]="'ov-project-card__status ov-project-card__status--' + project().statusTone">
            <n-icon [name]="statusIcon()" size="sm" />
            <span>{{ 'status.' + project().status | t: undefined : project().status }} - {{ project().updatedLabel }}</span>
          </div>
          @if (project().progress !== undefined && project().progress! > 0 && project().progress! < 100) {
            <n-progress [value]="project().progress!" variant="gemini-full" size="xs" />
          }
        </div>
      }
    </a>
  `,
  styles: [
    `
      :host {
        display: block;
        min-width: 0;
      }

      .ov-project-card {
        display: grid;
        grid-template-rows: 156px auto;
        min-height: 254px;
        overflow: hidden;
        border: 1px solid transparent;
        border-radius: var(--n-radius-lg);
        background:
          linear-gradient(var(--n-surface-1), var(--n-surface-1)) padding-box,
          var(--n-gradient-border-subtle) border-box;
        color: inherit;
        text-decoration: none;
        box-shadow: 0 18px 42px rgba(0, 0, 0, 0.18);
        transition:
          transform var(--n-transition-fast),
          box-shadow var(--n-transition-fast),
          border-color var(--n-transition-fast);
      }

      .ov-project-card:hover {
        transform: translateY(-2px);
        box-shadow: var(--n-elevation-3), var(--n-glow-gradient-sm);
      }

      .ov-project-card--empty {
        display: grid;
        place-items: center;
        grid-template-rows: 1fr;
        border: 1px dashed var(--n-border-2);
        background: transparent;
      }

      .ov-project-card__empty {
        display: grid;
        justify-items: center;
        gap: 12px;
        color: var(--n-text-3);
      }

      .ov-project-card__empty span {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 48px;
        height: 48px;
        border: 1px dashed var(--n-border-2);
        border-radius: var(--n-radius-full);
      }

      .ov-project-card__empty strong {
        font-size: var(--n-font-size-13);
        font-weight: var(--n-font-weight-semibold);
      }

      .ov-project-card__thumb {
        position: relative;
        overflow: hidden;
        background: linear-gradient(145deg, #0a082a 0%, #1a1040 42%, #0d1535 70%, #050510 100%);
      }

      .ov-project-card__thumb--green {
        background: linear-gradient(145deg, #071722 0%, #0b2a2f 42%, #082216 76%, #03060a 100%);
      }

      .ov-project-card__thumb--rose {
        background: linear-gradient(145deg, #2a0618 0%, #381024 44%, #1b0b17 76%, #05050b 100%);
      }

      .ov-project-card__thumb--blue {
        background: linear-gradient(145deg, #07162c 0%, #111a52 48%, #060b1c 100%);
      }

      .ov-project-card__thumb::after {
        position: absolute;
        inset: 0;
        background: radial-gradient(circle at 44% 28%, rgba(102, 157, 246, 0.32), transparent 38%);
        content: '';
      }

      .ov-project-card__dot {
        position: absolute;
        z-index: 1;
        top: 14px;
        left: 14px;
        width: 8px;
        height: 8px;
        border-radius: var(--n-radius-full);
        background: var(--n-color-success);
        box-shadow: 0 0 14px var(--n-color-success);
      }

      .ov-project-card__badge {
        position: absolute;
        z-index: 1;
        top: 12px;
        right: 12px;
        padding: 4px 10px;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-full);
        background: rgba(0, 0, 0, 0.44);
        color: var(--n-color-primary-light);
        font-family: var(--n-font-mono);
        font-size: 0.64rem;
        font-weight: 800;
      }

      .ov-project-card__body {
        display: grid;
        gap: 8px;
        padding: 16px 18px 18px;
      }

      .ov-project-card h3,
      .ov-project-card p {
        min-width: 0;
        margin: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .ov-project-card h3 {
        color: var(--n-text-1);
        font-size: 1rem;
        font-weight: 800;
        line-height: 1.2;
      }

      .ov-project-card p {
        color: var(--n-text-3);
        font-family: var(--n-font-mono);
        font-size: 0.72rem;
      }

      .ov-project-card__status {
        display: flex;
        align-items: center;
        gap: 8px;
        min-width: 0;
        color: var(--n-text-2);
        font-size: 0.78rem;
        font-weight: 600;
      }

      .ov-project-card__status span {
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .ov-project-card__status--success {
        color: var(--n-color-success);
      }

      .ov-project-card__img {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        object-fit: cover;
      }

      .ov-project-card__title {
        display: flex;
        align-items: start;
        justify-content: space-between;
        gap: 8px;
      }

      .ov-project-card__actions {
        display: inline-flex;
        gap: 4px;
        opacity: 0;
        transition: opacity var(--n-transition-fast);
      }

      .ov-project-card:hover .ov-project-card__actions,
      .ov-project-card:focus-within .ov-project-card__actions {
        opacity: 1;
      }

      .ov-project-card__actions button {
        display: inline-grid;
        place-items: center;
        width: 26px;
        height: 26px;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-sm, 6px);
        background: var(--n-surface-2);
        color: var(--n-text-2);
        cursor: pointer;
      }

      .ov-project-card__actions button:hover {
        color: var(--n-text-1);
      }

      .ov-project-card__status--processing {
        color: var(--n-color-primary-light);
      }

      .ov-project-card__status--warning {
        color: var(--n-color-warning);
      }
    `,
  ],
})
export class OvProjectCardComponent {
  readonly project = input.required<ProjectCardVm>();
  readonly empty = input(false);
  /** Muestra renombrar/eliminar (página de proyectos). */
  readonly actions = input(false);
  /** Sin FFmpeg o con el video movido, se vuelve al fondo de color. */
  readonly thumbnailFailed = signal(false);
  readonly renameRequested = output<ProjectCardVm>();
  readonly deleteRequested = output<ProjectCardVm>();

  // La tarjeta es un enlace: los botones no deben navegar al workspace.
  emit(event: Event, target: { emit(value: ProjectCardVm): void }): void {
    event.preventDefault();
    event.stopPropagation();
    target.emit(this.project());
  }

  statusIcon(): string {
    switch (this.project().statusTone) {
      case 'success':
        return 'sparkles';
      case 'warning':
        return 'alert-circle';
      case 'danger':
        return 'circle-x';
      case 'processing':
        return 'loader-circle';
      default:
        return 'clock';
    }
  }
}
