import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { TitleStrategy, provideRouter } from '@angular/router';
import { provideNeuralIcons } from '@neuralangular/angular-ui/icon';
import { provideNeuralOverlay } from '@neuralangular/angular-ui/overlay';
import { provideNeuralTheme } from '@neuralangular/angular-ui/theme';

import { routes } from './app.routes';
import { DesktopBackendService } from './core/desktop/desktop-backend.service';
import { TranslatedTitleStrategy } from './core/i18n/translated-title.strategy';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // En escritorio, puerto real del backend antes de la primera petición.
    provideAppInitializer(() => inject(DesktopBackendService).init()),
    provideRouter(routes),
    { provide: TitleStrategy, useClass: TranslatedTitleStrategy },
    provideNeuralTheme({
      defaultTheme: 'dark',
      storage: false,
    }),
    provideNeuralIcons(),
    provideNeuralOverlay(),
  ],
};
