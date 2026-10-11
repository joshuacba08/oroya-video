import { booleanAttribute, Component, input } from '@angular/core';

import { NIcon } from './icon';

export type NAIPipelineStep = {
  id: string;
  title: string;
  icon: string;
  status: 'success' | 'running' | 'pending' | 'danger' | string;
  progress?: number;
};

@Component({
  selector: 'n-ai-pipeline',
  standalone: true,
  imports: [NIcon],
  template: `
    <section class="n-ai-pipeline" [class.vertical]="orientation() === 'vertical'">
      @if (label()) {
        <strong class="n-ai-pipeline__label">{{ label() }}</strong>
      }
      <div class="n-ai-pipeline__steps">
        @for (step of steps(); track step.id) {
          <div class="n-ai-pipeline__step" [class.success]="step.status === 'success'" [class.running]="step.status === 'running'">
            <span><n-icon [name]="step.icon" size="sm" /></span>
            <small>{{ step.title }}</small>
          </div>
        }
      </div>
    </section>
  `,
  styles: [
    `
      .n-ai-pipeline {
        display: grid;
        gap: 16px;
        min-width: 0;
      }

      .n-ai-pipeline__label {
        color: var(--n-text-3);
        font-size: 0.78rem;
        font-weight: 900;
        text-transform: uppercase;
      }

      .n-ai-pipeline__steps {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        align-items: start;
        gap: 10px;
      }

      .vertical .n-ai-pipeline__steps {
        grid-template-columns: 1fr;
      }

      .n-ai-pipeline__step {
        position: relative;
        display: grid;
        justify-items: center;
        gap: 6px;
        color: var(--n-text-3);
      }

      .vertical .n-ai-pipeline__step {
        grid-template-columns: 30px minmax(0, 1fr);
        justify-items: start;
        align-items: center;
      }

      .n-ai-pipeline__step span {
        display: grid;
        place-items: center;
        width: 30px;
        height: 30px;
        border: 1px solid var(--n-border-2);
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.04);
      }

      .n-ai-pipeline__step.success {
        color: var(--n-color-success);
      }

      .n-ai-pipeline__step.running {
        color: var(--n-color-primary-light);
      }

      .n-ai-pipeline__step small {
        overflow: hidden;
        text-overflow: ellipsis;
        font-family: var(--n-font-mono);
        font-size: 0.72rem;
        font-weight: 800;
        white-space: nowrap;
      }
    `,
  ],
})
export class NAIPipeline {
  readonly label = input('');
  readonly orientation = input<'horizontal' | 'vertical'>('horizontal');
  readonly density = input<'compact' | 'normal'>('normal');
  readonly steps = input<readonly NAIPipelineStep[]>([]);
  readonly showProgress = input(false, { transform: booleanAttribute });
}
