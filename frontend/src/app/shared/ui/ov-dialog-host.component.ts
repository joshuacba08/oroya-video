import { Component, ElementRef, effect, inject, viewChild } from '@angular/core';
import { NButton } from '@neuralangular/angular-ui/button';

import { DialogService } from '../../core/dialogs/dialog.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';

@Component({
  selector: 'ov-dialog-host',
  standalone: true,
  imports: [NButton, TranslatePipe],
  host: { '(document:keydown.escape)': 'dialogs.current() && dialogs.close(null)' },
  template: `
    @if (dialogs.current(); as dialog) {
      <div class="ov-dialog-backdrop" (click)="dialogs.close(null)"></div>
      <form
        class="ov-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ov-dialog-title"
        (submit)="submit($event)"
      >
        <h2 id="ov-dialog-title">{{ dialog.title }}</h2>
        @if (dialog.kind === 'confirm') {
          <p>{{ dialog.message }}</p>
        } @else {
          <label for="ov-dialog-input">{{ dialog.label }}</label>
          <input
            #promptInput
            id="ov-dialog-input"
            type="text"
            autocomplete="off"
            maxlength="200"
            [value]="dialog.value"
          />
        }
        <div class="ov-dialog__actions">
          <n-button variant="secondary" size="sm" (click)="dialogs.close(null)">
            {{ 'common.cancel' | t }}
          </n-button>
          <n-button
            [variant]="dialog.kind === 'confirm' && dialog.danger ? 'danger' : 'primary'"
            size="sm"
            type="submit"
          >
            {{ dialog.confirmLabel }}
          </n-button>
        </div>
      </form>
    }
  `,
  styles: [
    `
      .ov-dialog-backdrop {
        position: fixed;
        z-index: 900;
        inset: 0;
        background: rgba(0, 0, 0, 0.55);
      }

      .ov-dialog {
        position: fixed;
        z-index: 901;
        top: 50%;
        left: 50%;
        display: grid;
        gap: 14px;
        width: min(440px, calc(100vw - 32px));
        padding: 22px;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-xl);
        background: var(--n-bg-elevated, #12141f);
        box-shadow: 0 24px 60px rgba(0, 0, 0, 0.5);
        transform: translate(-50%, -50%);
      }

      h2 {
        margin: 0;
        color: var(--n-text-1);
        font-size: 1.05rem;
        font-weight: 900;
      }

      p,
      label {
        margin: 0;
        color: var(--n-text-2);
        font-size: 0.86rem;
      }

      input {
        height: 40px;
        padding: 0 12px;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-md);
        outline: 0;
        background: rgba(255, 255, 255, 0.035);
        color: var(--n-text-1);
        font: inherit;
      }

      input:focus {
        border-color: color-mix(in srgb, var(--n-color-primary), transparent 35%);
      }

      .ov-dialog__actions {
        display: flex;
        justify-content: flex-end;
        gap: 10px;
      }
    `,
  ],
})
export class OvDialogHostComponent {
  readonly dialogs = inject(DialogService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly promptInput = viewChild<ElementRef<HTMLInputElement>>('promptInput');

  constructor() {
    // Foco al abrir: el campo de texto (seleccionado) o el botón principal.
    effect(() => {
      if (!this.dialogs.current()) {
        return;
      }
      queueMicrotask(() => {
        const input = this.promptInput()?.nativeElement;
        if (input) {
          input.focus();
          input.select();
          return;
        }
        this.host.nativeElement.querySelector<HTMLButtonElement>('button[type="submit"]')?.focus();
      });
    });
  }

  submit(event: Event): void {
    event.preventDefault();
    const dialog = this.dialogs.current();
    if (!dialog) {
      return;
    }
    this.dialogs.close(dialog.kind === 'confirm' ? true : (this.promptInput()?.nativeElement.value ?? ''));
  }
}
