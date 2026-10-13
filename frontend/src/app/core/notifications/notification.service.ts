import { Injectable, signal } from '@angular/core';

export type NoticeTone = 'danger' | 'warning' | 'success' | 'info';

export interface Notice {
  id: number;
  tone: NoticeTone;
  title: string;
  message: string;
}

const AUTO_DISMISS_MS = 8000;

/** Avisos flotantes de la app (los muestra `ov-notifications` en el shell). */
@Injectable({ providedIn: 'root' })
export class NotificationService {
  private nextId = 1;
  readonly notices = signal<Notice[]>([]);

  show(tone: NoticeTone, title: string, message: string): number {
    const id = this.nextId++;
    this.notices.update((items) => [...items.slice(-2), { id, tone, title, message }]);
    globalThis.setTimeout(() => this.dismiss(id), AUTO_DISMISS_MS);
    return id;
  }

  danger(title: string, message: string): number {
    return this.show('danger', title, message);
  }

  dismiss(id: number): void {
    this.notices.update((items) => items.filter((item) => item.id !== id));
  }
}
