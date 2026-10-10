import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core';
import { NIcon } from '@neuralangular/angular-ui/icon';

@Component({
  selector: 'ov-manual-path-import',
  standalone: true,
  imports: [NIcon],
  template: `
    <form class="manual-path" (submit)="submit($event)">
      <label class="manual-path__label" for="manual-video-path">
        <n-icon name="file-video" size="sm" />
        <span>Absolute video path</span>
      </label>
      <div class="manual-path__controls">
        <input
          id="manual-video-path"
          type="text"
          autocomplete="off"
          spellcheck="false"
          placeholder="C:\\Users\\Ander\\Videos\\sample.mp4"
          [value]="path()"
          (input)="path.set(inputValue($event))"
        />
        <button type="submit" [disabled]="busy() || !path().trim()">Import</button>
        <button type="button" class="manual-path__ghost" [disabled]="busy()" (click)="cancelled.emit()">
          Cancel
        </button>
      </div>
    </form>
  `,
  styles: [
    `
      :host {
        display: block;
      }

      .manual-path {
        display: grid;
        gap: 10px;
        padding: 14px;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-lg);
        background: color-mix(in srgb, var(--n-bg-elevated), transparent 8%);
      }

      .manual-path__label {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        color: var(--n-text-2);
        font-size: 0.82rem;
        font-weight: 800;
      }

      .manual-path__controls {
        display: grid;
        grid-template-columns: minmax(220px, 1fr) auto auto;
        gap: 10px;
      }

      input {
        min-width: 0;
        height: 40px;
        padding: 0 12px;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-md);
        outline: 0;
        background: rgba(255, 255, 255, 0.035);
        color: var(--n-text-1);
        font: 700 0.86rem var(--n-font-mono);
      }

      input:focus {
        border-color: color-mix(in srgb, var(--n-color-primary), transparent 35%);
        box-shadow: 0 0 0 2px color-mix(in srgb, var(--n-color-primary), transparent 82%);
      }

      button {
        min-width: 96px;
        height: 40px;
        padding: 0 14px;
        border: 1px solid color-mix(in srgb, var(--n-color-primary), transparent 35%);
        border-radius: var(--n-radius-md);
        background: var(--n-gradient-gemini);
        color: #fff;
        font-size: 0.82rem;
        font-weight: 900;
        cursor: pointer;
      }

      button:disabled {
        cursor: not-allowed;
        opacity: 0.55;
      }

      .manual-path__ghost {
        border-color: var(--n-border-1);
        background: rgba(255, 255, 255, 0.025);
        color: var(--n-text-2);
      }

      @media (max-width: 760px) {
        .manual-path__controls {
          grid-template-columns: 1fr;
        }

        button {
          width: 100%;
        }
      }
    `,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OvManualPathImportComponent {
  readonly busy = input(false);
  readonly pathSubmitted = output<string>();
  readonly cancelled = output<void>();
  readonly path = signal('');

  inputValue(event: Event): string {
    return event.target instanceof HTMLInputElement ? event.target.value : '';
  }

  submit(event: SubmitEvent): void {
    event.preventDefault();
    const value = this.path().trim();

    if (!this.busy() && value) {
      this.pathSubmitted.emit(value);
    }
  }
}
