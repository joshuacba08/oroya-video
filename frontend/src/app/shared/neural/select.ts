import { Component, input, output } from '@angular/core';

export type NSelectOption = {
  label: string;
  value: string;
  disabled?: boolean;
};

@Component({
  selector: 'n-select',
  standalone: true,
  template: `
    <!-- [selected] por opción: un [value] en el <select> se aplica antes de que existan las
         <option> y el navegador mostraba siempre la primera. -->
    <select class="n-select" [class.n-select--sm]="size() === 'sm'" (change)="onChange($event)">
      @for (option of options(); track option.value) {
        <option
          [value]="option.value"
          [disabled]="option.disabled"
          [selected]="option.value === value()"
        >
          {{ option.label }}
        </option>
      }
    </select>
  `,
  styles: [
    `
      :host {
        display: block;
      }

      .n-select {
        width: 100%;
        min-width: 160px;
        height: 40px;
        padding: 0 12px;
        border: 1px solid var(--n-border-2);
        border-radius: var(--n-radius-md);
        background: var(--n-surface-2);
        color: var(--n-text-1);
        font: inherit;
      }

      .n-select--sm {
        height: 34px;
      }
    `,
  ],
})
export class NSelect {
  readonly options = input<readonly NSelectOption[]>([]);
  readonly value = input('');
  readonly size = input<'sm' | 'md' | 'lg'>('md');
  readonly valueChange = output<string>();

  onChange(event: Event): void {
    this.valueChange.emit((event.target as HTMLSelectElement).value);
  }
}
