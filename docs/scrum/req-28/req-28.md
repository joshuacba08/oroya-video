# REQ-028 - Experiencia ante fallos y datos del usuario

## Proyecto

Oroya Video

## Área

Frontend / Backend / Instalador

## Objetivo

Que los fallos se expliquen en lenguaje claro dentro de la app y que los videos del usuario
no dependan de la carpeta interna de la aplicación.

## Implementación

- **Arranque y caídas**: pantalla "Iniciando el motor…" y pantalla de fallo con reintento y
  carpeta de logs (ver REQ-023); el panel "sin conexión" usa el estado en vivo.
- **Diálogos propios** (`DialogService` + `ov-dialog-host`): confirmar y pedir texto, con foco
  inicial, Enter/Esc, clic fuera para cancelar y botón de peligro; sustituyen
  `window.confirm/prompt` en Proyectos y Exportaciones.
- **SSE**: un evento corrupto se ignora; el sondeo de respaldo termina en estados finales.
- **Pausa con motivo**: si un job queda pausado con un error (p. ej. disco lleno), el
  Workspace lo muestra traducido.
- **Carpeta de exportación** (`exports_dir`): en escritorio, por defecto la carpeta Vídeos
  del usuario (`SHGetKnownFolderPath`, también redirigida a OneDrive) + `Oroya Video`.
  Editable en Ajustes (selector de carpetas en escritorio), validada (ruta absoluta y
  escribible) y bloqueada con un job en curso. Borrar un job limpia también exportaciones
  hechas en la carpeta anterior.
- **Ventana** mínima de 1024×640; **instalador** NSIS por usuario, WebView2 con bootstrapper
  incluido, en español e inglés; README con el aviso de SmartScreen (instalador sin firmar).

## Verificación

- Tests: carpeta por defecto en escritorio, cambio y validación desde `/settings`, limpieza
  en la carpeta anterior; vitest de `DialogService`.
- Manual (navegador de desarrollo): diálogo de renombrar con foco y texto seleccionado,
  Esc y clic fuera cancelan, confirmación de borrado con botón de peligro.
