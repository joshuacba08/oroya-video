import { Component, input } from '@angular/core';

@Component({
  selector: 'ov-settings-row',
  standalone: true,
  template: `
    <div class="ov-settings-row">
      <div>
        <strong>{{ label() }}</strong>
        @if (description()) {
          <span>{{ description() }}</span>
        }
      </div>
      <ng-content />
    </div>
  `,
  styles: [
    `
      :host {
        display: block;
      }

      .ov-settings-row {
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(160px, 240px);
        align-items: center;
        gap: 24px;
        min-height: 58px;
        border-bottom: 1px solid var(--n-border-0);
      }

      strong,
      span {
        display: block;
        min-width: 0;
      }

      strong {
        color: var(--n-text-2);
        font-size: 0.88rem;
        font-weight: 700;
      }

      span {
        margin-top: 3px;
        color: var(--n-text-3);
        font-size: 0.75rem;
      }

      @media (max-width: 680px) {
        .ov-settings-row {
          grid-template-columns: 1fr;
          gap: 10px;
          padding: 12px 0;
        }
      }
    `,
  ],
})
export class OvSettingsRowComponent {
  readonly label = input.required<string>();
  readonly description = input<string | undefined>(undefined);
}
