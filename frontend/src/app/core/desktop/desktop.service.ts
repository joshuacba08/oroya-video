import { Injectable } from '@angular/core';

import type { PickedVideo } from '../models/oroya.models';

type TauriWindow = Window &
  typeof globalThis & {
    __TAURI_INTERNALS__?: unknown;
  };

@Injectable({ providedIn: 'root' })
export class DesktopService {
  isDesktop(): boolean {
    return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in (window as TauriWindow);
  }

  async pickVideo(): Promise<PickedVideo | null> {
    if (this.isDesktop()) {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({
        multiple: false,
        filters: [
          {
            name: 'Video',
            extensions: ['mp4', 'mov', 'mkv'],
          },
        ],
      });

      return typeof selected === 'string' ? { kind: 'tauri', path: selected } : null;
    }

    return null;
  }

  /** Abre una URL http(s) en el navegador del sistema (Tauri) o en una pestaña nueva. */
  async openUrl(url: string): Promise<void> {
    if (!url) {
      return;
    }

    if (this.isDesktop()) {
      const { openUrl } = await import('@tauri-apps/plugin-opener');
      await openUrl(url);
      return;
    }

    window.open(url, '_blank', 'noopener');
  }
}
