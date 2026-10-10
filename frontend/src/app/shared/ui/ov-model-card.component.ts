import { Component, input, output } from '@angular/core';
import { NButton } from '@neuralangular/angular-ui/button';
import { NIcon } from '@neuralangular/angular-ui/icon';
import { NProgress } from '@neuralangular/angular-ui/progress';

import type { ModelDownloadVm, ModelVm } from '../../core/models/oroya.models';

@Component({
  selector: 'ov-model-card',
  standalone: true,
  imports: [NButton, NIcon, NProgress],
  template: `
    <article class="ov-model-card" [class.ov-model-card--available]="!model().installed">
      <header>
        <div>
          <h3>{{ model().name }}</h3>
          <span>{{ model().installed ? 'Installed' : 'Available' }} - {{ model().version }}</span>
        </div>
        @if (!model().installed) {
          <n-button
            variant="secondary"
            size="sm"
            iconOnly
            [ariaLabel]="'Download ' + model().name"
            [disabled]="download()?.status === 'downloading'"
            (click)="downloadRequested.emit(model())"
          >
            <n-icon name="download" size="sm" />
          </n-button>
        }
      </header>
      <p>{{ model().description }}</p>
      @if (download(); as state) {
        @if (state.status === 'downloading') {
          <div class="ov-model-card__download">
            <n-progress [value]="state.percent" variant="gemini" size="xs" />
            <span>
              {{ state.percent.toFixed(0) }}%
              @if (state.bytesTotal) {
                - {{ formatMb(state.bytesDone) }} / {{ formatMb(state.bytesTotal) }} MB
              }
            </span>
          </div>
        } @else if (state.status === 'failed') {
          <p class="ov-model-card__download-error">
            Download failed: {{ state.errorMessage || 'unknown error' }}
          </p>
        }
      }
      @if (model().installed) {
        <div class="ov-model-card__metrics">
          <label>
            <span>Quality</span>
            <n-progress [value]="model().quality" variant="gemini" size="xs" />
            <strong>{{ qualityLabel() }}</strong>
          </label>
          <label>
            <span>Speed</span>
            <n-progress [value]="model().speed" variant="warning" size="xs" />
            <strong>{{ speedLabel() }}</strong>
          </label>
          <label>
            <span>VRAM</span>
            <n-progress [value]="vramPercent()" variant="success-blue" size="xs" />
            <strong>{{ model().vramGb }} GB</strong>
          </label>
        </div>
      }
    </article>
  `,
  styles: [
    `
      :host {
        display: block;
        min-width: 0;
      }

      .ov-model-card {
        display: grid;
        gap: 14px;
        min-height: 208px;
        padding: 20px;
        border: 1px solid transparent;
        border-radius: var(--n-radius-lg);
        background:
          linear-gradient(var(--n-surface-1), var(--n-surface-1)) padding-box,
          var(--n-gradient-border-subtle) border-box;
      }

      .ov-model-card--available {
        min-height: auto;
        grid-template-columns: 1fr;
        border-style: dashed;
        background: rgba(255, 255, 255, 0.012);
      }

      header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 16px;
        min-width: 0;
      }

      h3,
      p {
        margin: 0;
      }

      h3 {
        color: var(--n-text-1);
        font-size: 1rem;
        font-weight: 800;
        line-height: 1.25;
      }

      header span {
        display: inline-flex;
        width: fit-content;
        margin-top: 8px;
        padding: 4px 10px;
        border-radius: var(--n-radius-full);
        background: var(--n-gradient-primary-secondary);
        color: white;
        font-family: var(--n-font-mono);
        font-size: 0.68rem;
        font-weight: 800;
      }

      p {
        color: var(--n-text-3);
        font-size: 0.83rem;
        font-weight: 600;
        line-height: 1.55;
      }

      .ov-model-card__metrics {
        display: grid;
        gap: 10px;
      }

      label {
        display: grid;
        grid-template-columns: 76px minmax(80px, 1fr) 58px;
        align-items: center;
        gap: 10px;
        min-width: 0;
      }

      label span {
        color: var(--n-text-3);
        font-size: 0.72rem;
        font-weight: 700;
      }

      label strong {
        color: var(--n-text-2);
        font-family: var(--n-font-mono);
        font-size: 0.72rem;
        text-align: right;
      }

      .ov-model-card__download {
        display: grid;
        gap: 6px;
      }

      .ov-model-card__download span {
        color: var(--n-text-3);
        font-family: var(--n-font-mono);
        font-size: 0.72rem;
        font-weight: 700;
      }

      .ov-model-card__download-error {
        color: var(--n-color-danger);
        font-size: 0.76rem;
      }
    `,
  ],
})
export class OvModelCardComponent {
  readonly model = input.required<ModelVm>();
  readonly download = input<ModelDownloadVm | null>(null);
  readonly downloadRequested = output<ModelVm>();

  formatMb(bytes: number): string {
    return (bytes / 1024 ** 2).toFixed(0);
  }

  qualityLabel(): string {
    return this.model().quality > 90 ? 'Best' : (this.model().quality / 10).toFixed(1);
  }

  speedLabel(): string {
    return this.model().speed > 60 ? 'Med' : (this.model().speed / 10).toFixed(1);
  }

  vramPercent(): number {
    return Math.min(Math.round((this.model().vramGb / 12) * 100), 100);
  }
}
