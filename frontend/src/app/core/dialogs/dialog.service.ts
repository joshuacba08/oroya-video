import { Injectable, signal } from '@angular/core';

export interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
}

export interface PromptOptions {
  title: string;
  label: string;
  value: string;
  confirmLabel: string;
}

export type DialogRequest =
  | ({ kind: 'confirm' } & ConfirmOptions & { resolve: (value: boolean) => void })
  | ({ kind: 'prompt' } & PromptOptions & { resolve: (value: string | null) => void });

/**
 * Diálogos propios en lugar de window.confirm/prompt: esos bloquean la ventana, muestran
 * "tauri.localhost dice…" y no siguen el tema ni el idioma de la app.
 */
@Injectable({ providedIn: 'root' })
export class DialogService {
  readonly current = signal<DialogRequest | null>(null);

  confirm(options: ConfirmOptions): Promise<boolean> {
    return new Promise((resolve) => {
      this.cancelOpen();
      this.current.set({ kind: 'confirm', ...options, resolve });
    });
  }

  /** Texto introducido (sin espacios sobrantes) o null si se cancela o queda vacío. */
  prompt(options: PromptOptions): Promise<string | null> {
    return new Promise((resolve) => {
      this.cancelOpen();
      this.current.set({ kind: 'prompt', ...options, resolve });
    });
  }

  close(result: boolean | string | null): void {
    const request = this.current();
    if (!request) {
      return;
    }
    this.current.set(null);
    if (request.kind === 'confirm') {
      request.resolve(result === true);
    } else {
      const text = typeof result === 'string' ? result.trim() : '';
      request.resolve(text ? text : null);
    }
  }

  private cancelOpen(): void {
    if (this.current()) {
      this.close(null);
    }
  }
}
