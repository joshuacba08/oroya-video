# REQ-029 - Actualizador automático

## Proyecto

Oroya Video

## Área

Escritorio (Tauri) / Frontend / Release

## Objetivo

Que los usuarios reciban las nuevas versiones desde la propia app, de forma segura (firmadas)
y sin perder el trabajo en curso.

## Implementación

- **Plugins**: `tauri-plugin-updater` y `tauri-plugin-process`; `bundle.createUpdaterArtifacts`
  genera `<instalador>.exe.sig`. Endpoint:
  `https://github.com/joshuacba08/oroya-video/releases/latest/download/latest.json`; instalación
  NSIS en modo `passive`.
- **Firma**: clave minisign propia. La pública está en `tauri.conf.json`; la privada y su
  contraseña viven fuera del repo (`~/.tauri/oroya-updater.key` y
  `oroya-updater.password.txt` en el equipo del mantenedor) y en los secrets de GitHub
  `TAURI_SIGNING_PRIVATE_KEY` / `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`. Una actualización no
  firmada con esa clave se rechaza.
- **Release**: el build firma con los secrets; `scripts/make_update_manifest.py` genera
  `latest.json` (versión, notas de `docs/releases/<tag>.md`, firma y URL del asset con los
  espacios convertidos en puntos, como hace GitHub). En un tag es obligatorio: sin firma no
  se publica. Sin la clave (builds locales), `build_installer.ps1` desactiva los artefactos
  del actualizador.
- **App**:
  - Una comprobación por sesión cuando el backend queda listo (solo en la app instalada).
  - Aviso "Oroya Video X está disponible" con "Novedades" (abre el release) e "Instalar y
    reiniciar".
  - No se instala con un job en marcha (se avisa).
  - Orden seguro: descarga con el backend activo → apagado ordenado del backend
    (`stop_backend_for_update`) → instalación → reinicio; si la instalación falla, el backend
    vuelve a arrancar (`restart_backend`).
  - Ajustes → Soporte: versión instalada y "Buscar actualizaciones".
- **Nota**: quien tenga la 0.3.0 instala la 0.4.0 a mano una vez; desde la 0.4.0 las
  actualizaciones llegan solas.

## Verificación

- Build local firmado: se generan el instalador y su `.sig`; `latest.json` correcto.
- Flujo completo de actualización: pendiente de la primera release con el actualizador
  (0.4.0 → 0.4.1).
