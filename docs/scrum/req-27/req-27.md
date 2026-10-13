# REQ-027 - Seguridad del servidor local

## Proyecto

Oroya Video

## Área

Backend

## Objetivo

Que la API en 127.0.0.1 solo la use la interfaz de Oroya Video de este equipo.

## Implementación

- **`LocalOnlyMiddleware`** (el más externo):
  - Rechaza (403 `forbidden_host`) un `Host` que no sea de loopback: frena el DNS rebinding.
  - En métodos que modifican datos, rechaza (403 `forbidden_origin`) un `Origin` fuera de
    `cors_origins` o una petición `Sec-Fetch-Site: cross-site` sin origen: CORS no bloquea los
    POST "simples" (solo oculta la respuesta), que podían, por ejemplo, lanzar la instalación
    de la IA desde una web.
- **`/system/shutdown`** exige `X-Oroya-Instance` igual al id generado por la app de escritorio;
  sin él (desarrollo) responde 404.

## Verificación

- Tests: Host ajeno rechazado y loopback con cualquier puerto aceptado; POST desde un origen
  ajeno o cross-site rechazado; lecturas y la UI propia permitidas.
