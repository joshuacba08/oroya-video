import { Component, input } from '@angular/core';

@Component({
  selector: 'ov-section-header',
  standalone: true,
  template: `
    <div class="ov-section-header">
      <span>{{ label() }}</span>
      <i></i>
    </div>
  `,
  styles: [
    `
      :host {
        display: block;
      }

      .ov-section-header {
        display: flex;
        align-items: center;
        gap: 14px;
        min-width: 0;
        color: var(--n-text-3);
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        line-height: 1;
        text-transform: uppercase;
      }

      .ov-section-header i {
        display: block;
        min-width: 24px;
        height: 1px;
        flex: 1;
        background: linear-gradient(90deg, var(--n-border-1), transparent);
      }
    `,
  ],
})
export class OvSectionHeaderComponent {
  readonly label = input.required<string>();
}
