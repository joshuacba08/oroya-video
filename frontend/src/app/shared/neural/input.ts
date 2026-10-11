import { Component, input, output } from '@angular/core';

@Component({
  selector: 'n-input',
  standalone: true,
  template: `
    <input
      class="n-field__control"
      [class.n-field__control--sm]="size() === 'sm'"
      [placeholder]="placeholder()"
      [value]="value()"
      (input)="onInput($event)"
    />
  `,
  styles: [
    `
      :host {
        display: block;
        min-width: 0;
      }

      .n-field__control {
        width: 100%;
        min-width: 0;
        height: 40px;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-md);
        background: rgba(255, 255, 255, 0.035);
        color: var(--n-text-1);
        font: inherit;
        outline: none;
      }

      .n-field__control--sm {
        height: 34px;
      }

      .n-field__control::placeholder {
        color: var(--n-text-3);
      }
    `,
  ],
})
export class NInput {
  readonly placeholder = input('');
  readonly size = input<'sm' | 'md' | 'lg'>('md');
  readonly value = input('');
  readonly valueChange = output<string>();

  onInput(event: Event): void {
    this.valueChange.emit((event.target as HTMLInputElement).value);
  }
}
