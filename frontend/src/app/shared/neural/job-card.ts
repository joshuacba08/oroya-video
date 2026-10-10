import { Component, input } from '@angular/core';

import { NProgress } from './progress';

@Component({
  selector: 'n-job-card',
  standalone: true,
  imports: [NProgress],
  template: `
    <article class="n-job-card" [attr.data-status]="statusType()">
      <header>
        <div>
          <h2>{{ title() }}</h2>
          <p>{{ subtitle() }}</p>
        </div>
        <span>{{ status() }}</span>
      </header>
      <div class="n-job-card__progress">
        <p>{{ progressLabel() }}</p>
        <strong>{{ progress() }}%</strong>
      </div>
      <n-progress [value]="progress()" variant="gemini-full" size="xs" />
      <section class="n-job-card__body">
        <ng-content />
      </section>
    </article>
  `,
  styles: [
    `
      .n-job-card {
        display: grid;
        gap: 14px;
        padding: 22px;
        border: 1px solid rgba(122, 94, 255, 0.24);
        border-radius: var(--n-radius-xl);
        background: rgba(255, 255, 255, 0.035);
      }

      header,
      .n-job-card__progress {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        min-width: 0;
      }

      h2,
      p {
        margin: 0;
      }

      h2 {
        color: var(--n-text-1);
        font-size: 1rem;
      }

      p {
        color: var(--n-text-3);
        font-family: var(--n-font-mono);
        font-size: 0.78rem;
      }

      header span {
        flex-shrink: 0;
        padding: 5px 12px;
        border-radius: var(--n-radius-full);
        background: rgba(34, 197, 94, 0.13);
        color: var(--n-color-success);
        font-size: 0.75rem;
        font-weight: 900;
      }

      .n-job-card__progress strong {
        color: var(--n-text-1);
      }

      .n-job-card__body {
        padding: 16px;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-lg);
        background: rgba(255, 255, 255, 0.025);
      }
    `,
  ],
})
export class NJobCard {
  readonly title = input('');
  readonly subtitle = input('');
  readonly status = input('');
  readonly statusType = input('');
  readonly progress = input(0);
  readonly progressLabel = input('');
}
