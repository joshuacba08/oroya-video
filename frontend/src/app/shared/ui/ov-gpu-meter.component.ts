import { Component, input } from '@angular/core';
import { NIcon } from '@neuralangular/angular-ui/icon';
import { NProgress } from '@neuralangular/angular-ui/progress';

import { TranslatePipe } from '../../core/i18n/translate.pipe';
import type { SystemStatusVm } from '../../core/models/oroya.models';

@Component({
  selector: 'ov-gpu-meter',
  standalone: true,
  imports: [NIcon, NProgress, TranslatePipe],
  template: `
    <section class="ov-gpu-meter">
      <header>
        <span><n-icon name="cpu" size="sm" /> {{ 'gpu.label' | t: { name: system().gpuName } }}</span>
        <strong>{{ system().gpuUsage }}%</strong>
      </header>
      <n-progress [value]="system().gpuUsage" variant="primary" size="xs" />
      <div class="ov-gpu-meter__row">
        <span>VRAM</span>
        <strong>{{ system().vramUsedGb }} / {{ system().vramTotalGb }} GB</strong>
      </div>
      <n-progress [value]="vramPercent()" variant="secondary" size="xs" />
    </section>
  `,
  styles: [
    `
      :host {
        display: block;
      }

      .ov-gpu-meter {
        display: grid;
        gap: 8px;
        padding: 14px 16px;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-lg);
        background: rgba(255, 255, 255, 0.025);
      }

      header,
      .ov-gpu-meter__row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        min-width: 0;
      }

      header span,
      .ov-gpu-meter__row span {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        min-width: 0;
        overflow: hidden;
        color: var(--n-text-3);
        font-size: 0.72rem;
        font-weight: 800;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      header strong,
      .ov-gpu-meter__row strong {
        flex-shrink: 0;
        color: var(--n-text-1);
        font-family: var(--n-font-mono);
        font-size: 0.72rem;
      }
    `,
  ],
})
export class OvGpuMeterComponent {
  readonly system = input.required<SystemStatusVm>();

  vramPercent(): number {
    return Math.round((this.system().vramUsedGb / this.system().vramTotalGb) * 100);
  }
}
