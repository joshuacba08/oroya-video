# REQ-032 - Exportaciones legibles

## Proyecto

Oroya Video

## Área

Backend / Frontend

## Objetivo

Que las exportaciones se encuentren a simple vista: una carpeta por proyecto y un nombre de
archivo que dice qué se hizo, en lugar de carpetas con UUID.

## Implementación

- **Layout**: `<carpeta de exportación>/<Proyecto>/<Proyecto> (Oroya 2x).mp4`; con
  interpolación, `(Oroya 2x 60fps)`. Si ya existe: ` (2)`, ` (3)`…
- **Nombres seguros** (`core/paths.py`): `project_display_name` quita la extensión del video;
  `safe_folder_name` elimina `<>:"/\|?*` y caracteres de control, espacios y puntos finales,
  añade `_` a nombres reservados de Windows (CON, NUL…) y limita a 80 caracteres.
- **Nombre y carpeta propios**: `export_config.file_name` y `export_config.output_dir`
  (absoluta), validados en `project_service`; se leen de la instantánea del job. El preflight
  comprueba que la carpeta de destino real es escribible y la exportación mide el espacio libre
  en ella.
- **Borrado seguro**: los llamadores recogen las rutas de `ExportAsset` antes de borrar en la
  base; `delete_job_files` borra solo esos archivos y luego las carpetas que queden vacías
  dentro de una raíz de exportación (`remove_empty_export_dirs`). Una carpeta elegida por el
  usuario o la propia raíz nunca se borran. El layout anterior (`<project_id>/<job_id>`) se
  sigue limpiando.
- **Uso de disco**: la medición de exportaciones usa la carpeta real.
- **Workspace**: campo "Nombre del archivo exportado" (con el nombre por defecto como pista) y
  "Carpeta de exportación" con "Cambiar…" (selector de carpetas en escritorio) y "Por defecto".

## Verificación

- Tests: nombres seguros, nombre por defecto con escala y fps, nombre y carpeta propios desde
  la instantánea, sin sobrescribir, borrado que respeta archivos de otro proyecto homónimo y
  carpetas del usuario, validación por la API.
- E2E: la exportación se llama `clip (Oroya 2x).mp4`.
