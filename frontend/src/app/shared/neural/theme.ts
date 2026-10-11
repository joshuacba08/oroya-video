import {
  ENVIRONMENT_INITIALIZER,
  makeEnvironmentProviders,
  type EnvironmentProviders,
} from '@angular/core';

export type NeuralThemeName = 'dark' | 'light' | 'system';
export type NeuralThemeConfig = {
  defaultTheme?: NeuralThemeName;
  storage?: boolean;
};

export function provideNeuralTheme(config: NeuralThemeConfig = {}): EnvironmentProviders {
  return makeEnvironmentProviders([
    {
      provide: ENVIRONMENT_INITIALIZER,
      multi: true,
      useValue: () => {
        document.documentElement.dataset['nTheme'] = config.defaultTheme ?? 'dark';
      },
    },
  ]);
}
