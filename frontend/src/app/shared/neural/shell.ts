import { Component, input } from '@angular/core';

@Component({
  selector: 'n-shell',
  standalone: true,
  template: `<section class="n-shell"><ng-content /></section>`,
  styles: [
    `
      .n-shell {
        display: grid;
        grid-template-columns: 290px minmax(0, 1fr);
        min-height: 100vh;
        background: var(--n-bg-canvas);
      }

      @media (max-width: 860px) {
        .n-shell {
          grid-template-columns: 1fr;
        }
      }
    `,
  ],
})
export class NShell {
  readonly sidebarMode = input<'fixed' | 'overlay'>('fixed');
}
