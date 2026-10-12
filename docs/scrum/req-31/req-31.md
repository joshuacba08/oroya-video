# REQ-031 - Tests E2E (Playwright)

## Proyecto

Oroya Video

## Área

Frontend / CI

## Objetivo

Probar los flujos críticos de punta a punta (navegador + backend real) en cada push.

## Implementación

- `frontend/e2e/` con Playwright (Chromium) y `pnpm e2e`:
  - Backend real en el puerto 8011 con motor `mock` ralentizado
    (`MOCK_ENHANCER_FRAME_DELAY_MS=250`, para poder pausar a mitad), almacenamiento y base
    de datos nuevos por ejecución.
  - Frontend con la configuración `e2e` (API en 8011, puerto 4211): no choca con los
    servidores de desarrollo.
  - `global-setup` genera un clip de 2 s con audio usando ffmpeg.
- **Flujos**:
  1. importar por ruta (Enter) y ver el fotograma original; procesar, pausar, reanudar,
     completar y ver la exportación;
  2. cambiar el idioma ES/EN sin recargar;
  3. renombrar y borrar con los diálogos propios;
  4. backend inalcanzable → panel "sin conexión" → "Reintentar" lo recupera.
- **CI**: job `End-to-end (Playwright)` en Ubuntu (ffmpeg por apt); el informe se sube si falla.

## Hallazgos corregidos gracias al E2E

- **El outlet del router cambiaba de rama** en el shell al llegar el estado de arranque: la
  página activa se destruía y volvía a crearse (peticiones duplicadas al abrir la app y
  acciones en curso perdidas, p. ej. un borrado con el diálogo abierto no refrescaba la
  lista). Ahora hay un único outlet siempre montado y los paneles lo ocultan.
- **`STORAGE_PATH` no movía la base de datos** si un `.env` repetía `DATABASE_URL` con su
  valor por defecto: los tests y los E2E escribían en la base de desarrollo. Con otro
  almacenamiento, la base por defecto ahora vive dentro de él.

## Verificación

- 3 ejecuciones locales seguidas: 4/4 en ~22 s; la base de desarrollo intacta.
