import { signal } from '@angular/core';

import { en, type TranslationKey } from './en';
import { es } from './es';

export type Language = 'en' | 'es';
export type TranslateParams = Record<string, string | number>;

const dictionaries: Record<Language, Record<TranslationKey, string>> = { en, es };

function initialLanguage(): Language {
  if (typeof navigator !== 'undefined' && navigator.language?.toLowerCase().startsWith('es')) {
    return 'es';
  }
  return 'en';
}

/**
 * Idioma activo de la UI. Es un signal de módulo para que también lo usen funciones puras
 * (mappers); el backend lo fija desde `general.language` al cargar/guardar settings.
 */
const currentLanguage = signal<Language>(initialLanguage());

export function getLanguage(): Language {
  return currentLanguage();
}

export function setLanguage(language: string | null | undefined): void {
  if (language !== 'en' && language !== 'es') {
    return;
  }
  currentLanguage.set(language);
  if (typeof document !== 'undefined') {
    document.documentElement.lang = language;
  }
}

/** Locale BCP 47 para fechas y números. */
export function getLocale(): string {
  return currentLanguage() === 'es' ? 'es' : 'en';
}

export function hasTranslation(key: string): key is TranslationKey {
  return key in en;
}

/**
 * Traduce `key` con interpolación `{name}`. Para claves dinámicas (p. ej. `status.<x>`)
 * devuelve `fallback` si la clave no existe, o la propia clave.
 */
export function translate(key: string, params?: TranslateParams, fallback?: string): string {
  if (!hasTranslation(key)) {
    return fallback ?? key;
  }
  const template = dictionaries[currentLanguage()][key];
  if (!params) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}
