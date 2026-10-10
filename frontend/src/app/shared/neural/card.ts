import { Component } from '@angular/core';

@Component({
  selector: 'n-card',
  standalone: true,
  template: `<section class="n-card"><ng-content /></section>`,
  styles: [
    `
      .n-card {
        display: block;
        height: 100%;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-lg);
        background: rgba(255, 255, 255, 0.025);
      }
    `,
  ],
})
export class NCard {}

@Component({
  selector: 'n-card-content',
  standalone: true,
  template: `<div class="n-card-content"><ng-content /></div>`,
  styles: [
    `
      .n-card-content {
        padding: 20px;
      }
    `,
  ],
})
export class NCardContent {}
