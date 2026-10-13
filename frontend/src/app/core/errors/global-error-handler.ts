import { ErrorHandler, Injectable, inject } from '@angular/core';

import { OroyaApiClient, OroyaApiError } from '../api/oroya-api-client';
import { translate } from '../i18n/i18n';
import { NotificationService } from '../notifications/notification.service';

const TOAST_INTERVAL_MS = 10_000;

function describe(error: unknown): { message: string; stack?: string } {
  const unwrapped = (error as { rejection?: unknown })?.rejection ?? error;
  if (unwrapped instanceof Error) {
    return { message: `${unwrapped.name}: ${unwrapped.message}`, stack: unwrapped.stack };
  }
  return { message: String(unwrapped) };
}

/**
 * Errores no controlados de la interfaz: se registran en backend.log (para el diagnóstico)
 * y se avisa al usuario con un aviso flotante, en lugar de fallar en silencio en la consola.
 */
@Injectable()
export class GlobalErrorHandler implements ErrorHandler {
  private readonly notifications = inject(NotificationService);
  private readonly api = new OroyaApiClient();
  private lastToastAt = 0;

  handleError(error: unknown): void {
    console.error(error);
    // Los errores de red ya los muestra la página o el panel "sin conexión".
    if (error instanceof OroyaApiError) {
      return;
    }
    const { message, stack } = describe(error);
    void this.api
      .post('/system/client-log', {
        level: 'error',
        message: message.slice(0, 2000),
        stack: stack?.slice(0, 8000),
        url: typeof location === 'undefined' ? undefined : location.pathname,
      })
      .catch(() => undefined);

    const now = Date.now();
    if (now - this.lastToastAt > TOAST_INTERVAL_MS) {
      this.lastToastAt = now;
      this.notifications.danger(
        translate('errors.unexpectedUiTitle'),
        translate('errors.unexpectedUi'),
      );
    }
  }
}
