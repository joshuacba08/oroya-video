import { Pipe, type PipeTransform } from '@angular/core';

import { getLanguage, translate, type TranslateParams } from './i18n';

/**
 * `{{ 'key' | t }}`, `{{ 'key' | t: { n: 3 } }}` o, para claves dinámicas,
 * `{{ 'status.' + s | t: undefined : s }}` (último argumento: texto si la clave no existe).
 * Impuro para reaccionar al cambio de idioma; la búsqueda es un acceso a objeto.
 */
@Pipe({ name: 't', standalone: true, pure: false })
export class TranslatePipe implements PipeTransform {
  transform(key: string, params?: TranslateParams, fallback?: string): string {
    getLanguage();
    return translate(key, params, fallback);
  }
}
