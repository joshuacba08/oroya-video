import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideNeuralIcons } from '@neuralangular/angular-ui/icon';
import { provideNeuralOverlay } from '@neuralangular/angular-ui/overlay';
import { provideNeuralTheme } from '@neuralangular/angular-ui/theme';

import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideNeuralTheme({
      defaultTheme: 'dark',
      storage: false,
    }),
    provideNeuralIcons(),
    provideNeuralOverlay()
  ]
};
