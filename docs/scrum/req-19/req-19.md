# REQ-019 - Bilingual UI (ES/EN)

## Proyecto

Oroya Video

## Área

Frontend / i18n

## Objetivo

La interfaz mezclaba inglés y español y el selector de idioma de Ajustes no tenía efecto.
Toda la UI pasa a estar disponible en inglés y español, con cambio en caliente.

## Implementación

- `frontend/src/app/core/i18n/`:
  - `i18n.ts`: idioma activo como signal de módulo (`getLanguage`, `setLanguage`,
    `translate(key, params, fallback)`, `getLocale`). Al cambiar, actualiza `<html lang>`.
  - `translate.pipe.ts`: pipe `t` (`{{ 'key' | t: { n: 1 } }}`), impuro para reaccionar al idioma.
  - `en.ts` / `es.ts`: diccionarios; `es` está tipado como `Record<TranslationKey, string>`,
    así que una clave que falte no compila. Un test verifica que los placeholders coinciden.
  - `translated-title.strategy.ts`: los `title` de las rutas son claves; el título de la
    pestaña se traduce y se actualiza al cambiar el idioma.
- El idioma lo fija el backend (`general.language`) al arrancar y al guardar Ajustes.
- Los mappers traducen etapas, pasos del pipeline, etiquetas y fechas (locale del idioma).
- Errores: `toErrorVm` traduce por `error_code` (`errors.<code>`) con el mensaje del
  backend como respaldo. Nuevo `settings_locked_by_running_job` en el backend.
- Descripciones de los modelos de serie traducidas por slug.

## Fuera de alcance

- Mensajes libres del backend (preflight, logs) siguen en inglés.
- Tema claro (solo existe el oscuro).
