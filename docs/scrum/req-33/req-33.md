# REQ-033 - Aviso de actualización discreto

## Proyecto

Oroya Video

## Área

Frontend (escritorio)

## Objetivo

Avisar de las versiones nuevas sin interrumpir: una píldora pequeña junto a la versión, en
lugar de un banner fijo, y comprobaciones periódicas mientras la app sigue abierta.

## Implementación

- **`UpdateService`**: `startPeriodicChecks` (al arrancar y cada 6 h, idempotente; solo en la
  app instalada), `lastCheckedAt` y `dismissedVersion` en `localStorage` (con try/catch),
  `visible` (hay versión y no está descartada) e `installArmed`.
- **Barra lateral**: píldora "Actualizar" junto a la versión; muestra el % de descarga y
  "Instalando…". Abre un panel con "Novedades", "Ahora no" (descarta esa versión; la siguiente
  vuelve a anunciarse) e "Instalar y reiniciar".
- **Con trabajo en la cola**: "Instalar" deja la instalación armada y se lanza sola cuando la
  cola queda vacía (antes solo avisaba y había que volver a pulsar).
- **Ajustes → Soporte**: botón "Instalar" y fecha de la última comprobación.
- El banner de la 0.4.0 desaparece.

## Verificación

- vitest: descartar, comprobación periódica (y una sola vez aunque se arranque dos veces),
  nada fuera de la app instalada, descartar cancela la instalación armada.
- Navegador de desarrollo: píldora y panel colocados en el pie de la barra lateral.
