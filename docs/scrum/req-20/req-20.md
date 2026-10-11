# REQ-020 - UX Completeness

## Proyecto

Oroya Video

## Área

Frontend / Backend

## Objetivo

Eliminar controles vacíos, datos inventados y acciones sin efecto antes de la v0.2.

## Implementación

- Proyectos: renombrar y eliminar desde la tarjeta (`PATCH`/`DELETE /projects/{id}`), con
  confirmación; indicador de búsqueda activa con opción de quitarla.
- Búsqueda global: el buscador del shell lleva a Proyectos desde cualquier página.
- Dashboard: "Importar video" importa y se queda (aviso + recarga); "Nuevo proyecto" abre el workspace.
- Modelos: habilitar/deshabilitar (`/models/{slug}/enable|disable`). Calidad y velocidad salen
  de `metadata.quality_tier` / `speed_tier` declarados en el backend (antes eran inventados);
  el seed añade estos campos a modelos de versiones anteriores sin pisar valores.
- Cola: "Pausar todo" pausa los jobs que el backend permite pausar; se quita "Prioridad"
  (la cola no tiene prioridades).
- Ajustes: los botones de carpetas abren la carpeta (`POST /system/storage/open?target=temp|models|exports`,
  solo destinos fijos); se puede editar la antigüedad de limpieza de temporales; mínimo de
  frames de preview en 4.
- Exportaciones: se sustituye la fila falsa "Quality: Backend export" por los fps reales.
- `n-select` mostraba siempre la primera opción en vez del valor guardado (el `[value]` del
  `<select>` se aplicaba antes de crear las `<option>`); ahora marca `selected` por opción.
- El placeholder del importador manual ya no incluye un nombre de usuario real.

## Fuera de alcance

- Reubicar carpetas de storage.
- Borrar pesos de modelos de serie desde la UI (el backend solo borra modelos personalizados).
