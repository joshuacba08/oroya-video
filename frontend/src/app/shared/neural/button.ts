import { booleanAttribute, Component, computed, input } from '@angular/core';

export type NButtonVariant =
  | 'primary'
  | 'gemini'
  | 'accent'
  | 'danger'
  | 'outline'
  | 'outline-gemini'
  | 'tonal'
  | 'tonal-violet'
  | 'ghost'
  | 'secondary';
export type NButtonSize = 'sm' | 'md' | 'lg' | 'xl';
export type NButtonType = 'button' | 'submit' | 'reset';

@Component({
  selector: 'n-button',
  standalone: true,
  template: `
    <button
      class="n-button"
      [class.n-button--primary]="variant() === 'primary'"
      [class.n-button--gemini]="variant() === 'gemini'"
      [class.n-button--secondary]="variant() === 'secondary'"
      [class.n-button--danger]="variant() === 'danger'"
      [class.n-button--sm]="size() === 'sm'"
      [class.n-button--lg]="size() === 'lg'"
      [class.n-button--full]="fullWidth()"
      [class.n-button--icon]="iconOnly()"
      [type]="type()"
      [disabled]="isDisabled()"
      [attr.aria-label]="ariaLabel()"
    >
      <ng-content />
    </button>
  `,
  styles: [
    `
      :host {
        display: inline-block;
        max-width: 100%;
      }

      :host:has(.n-button--full) {
        display: block;
        width: 100%;
      }

      .n-button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        width: auto;
        max-width: 100%;
        min-width: 0;
        height: 40px;
        padding: 0 18px;
        border: 1px solid transparent;
        border-radius: var(--n-radius-md);
        background: var(--n-gradient-primary-secondary);
        color: #fff;
        font: inherit;
        font-size: 0.84rem;
        font-weight: 800;
        line-height: 1;
        white-space: nowrap;
        cursor: pointer;
        transition:
          transform var(--n-transition-fast),
          border-color var(--n-transition-fast),
          background var(--n-transition-fast);
      }

      .n-button--sm {
        height: 36px;
        padding: 0 14px;
        font-size: 0.78rem;
      }

      .n-button--lg {
        height: 48px;
        font-size: 0.95rem;
      }

      .n-button--full {
        width: 100%;
      }

      .n-button--icon {
        width: 36px;
        padding: 0;
      }

      .n-button--gemini,
      .n-button--primary {
        background: var(--n-gradient-gemini);
        box-shadow: var(--n-glow-primary-xs);
      }

      .n-button--danger {
        border-color: color-mix(in srgb, var(--n-color-danger), transparent 40%);
        background: color-mix(in srgb, var(--n-color-danger), transparent 20%);
        color: #fff;
      }

      .n-button--secondary {
        border-color: var(--n-border-1);
        background: rgba(255, 255, 255, 0.03);
        color: var(--n-text-2);
      }

      .n-button:hover:not(:disabled) {
        border-color: rgba(124, 97, 255, 0.45);
        color: var(--n-text-1);
        transform: translateY(-1px);
      }

      .n-button:disabled {
        cursor: not-allowed;
        opacity: 0.45;
      }
    `,
  ],
})
export class NButton {
  readonly variant = input<NButtonVariant>('primary');
  readonly size = input<NButtonSize>('md');
  readonly type = input<NButtonType>('button');
  readonly disabled = input(false, { transform: booleanAttribute });
  readonly loading = input(false, { transform: booleanAttribute });
  readonly fullWidth = input(false, { transform: booleanAttribute });
  readonly iconOnly = input(false, { transform: booleanAttribute });
  readonly ariaLabel = input<string | null>(null);

  readonly isDisabled = computed(() => this.disabled() || this.loading());
}
