import { Component, computed, input } from '@angular/core';

export type NProgressVariant =
  | 'primary'
  | 'secondary'
  | 'gemini'
  | 'gemini-full'
  | 'warning'
  | 'success-blue';
export type NProgressSize = 'xs' | 'sm' | 'md';

@Component({
  selector: 'n-progress',
  standalone: true,
  host: {
    '[attr.data-progress-variant]': 'variant()',
    '[attr.data-progress-size]': 'size()',
  },
  template: `<span class="n-progress"><i [style.width.%]="clampedValue()"></i></span>`,
  styles: [
    `
      :host {
        display: block;
        width: 100%;
      }

      .n-progress {
        display: block;
        width: 100%;
        height: 6px;
        overflow: hidden;
        border-radius: var(--n-radius-full);
        background: rgba(255, 255, 255, 0.08);
      }

      :host([data-progress-size='xs']) .n-progress {
        height: 4px;
      }

      .n-progress i {
        display: block;
        height: 100%;
        border-radius: inherit;
        background: linear-gradient(90deg, #4f8cff, #d946ef);
      }

      :host([data-progress-variant='warning']) .n-progress i {
        background: linear-gradient(90deg, #facc15, #fb7185);
      }

      :host([data-progress-variant='success-blue']) .n-progress i,
      :host([data-progress-variant='secondary']) .n-progress i {
        background: linear-gradient(90deg, #4f8cff, #22c55e);
      }
    `,
  ],
})
export class NProgress {
  readonly value = input(0);
  readonly variant = input<NProgressVariant>('primary');
  readonly size = input<NProgressSize>('sm');

  readonly clampedValue = computed(() => Math.min(Math.max(Number(this.value()) || 0, 0), 100));
}
