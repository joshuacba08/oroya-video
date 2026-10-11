# REQ-022 - Face Restoration (GFPGAN)

## Proyecto

Oroya Video

## Área

Backend pipeline / Frontend

## Objetivo

Paso opcional de restauración de rostros tras el escalado, con GFPGAN v1.4 (Apache-2.0).
CodeFormer queda fuera por su licencia S-Lab (no comercial).

## Implementación

- **Configuración**: `enhancement_config.face_restore = {enabled, strength 0-1}`, validada
  en `project_service`. Desactivada por defecto.
- **Etapa `restoring_faces`** (`face_restore_service.py`), entre la mejora y el encode,
  progreso 60–66 % (el encode pasa a 66–85 %). Escribe en `frames/faces` y, solo al
  completar, sustituye los frames mejorados: un cancel o apagado no deja la carpeta a medias.
  Cancelable; la pausa no está disponible en esta etapa. Reanuda saltando frames ya escritos.
- **`GFPGANFaceRestorer`** (`enhancers/gfpgan_enhancer.py`): GFPGANer con `upscale=1`.
  GFPGAN fija `model_rootpath='gfpgan/weights'` (relativo al cwd) y facexlib descarga ahí sus
  pesos; se redirige a `models/facexlib` para funcionar sin conexión.
- **Modelo**: `gfpgan-v1.4` en el registro (categoría `face_restoration`), con
  `metadata.auxiliary_files` (pesos de detección y segmentación de facexlib); solo cuenta
  como instalado si existen todos. La descarga baja los tres archivos con SHA256 fijado
  (`download_file`, reutilizable).
- **Runtime**: el instalador de IA añade `gfpgan` y `facexlib` (`--no-deps`) más `filterpy`
  y `numba`. El preflight exige modelo y paquetes cuando la opción está activa.
- **UI**: interruptor "Restaurar rostros" e intensidad en el Workspace; deshabilitado con
  enlace a Modelos si GFPGAN no está instalado. GFPGAN no aparece como modelo de escalado.

## Verificación

- Tests: validación de la config, sustitución atómica, cancelación, etapa desactivada,
  modelo ausente, instalación con pesos auxiliares y descarga de los tres archivos.
- E2E con GPU real (RTX 5060 Ti): 72 caras restauradas en 72 frames (217 ms/frame) y
  comparación visual del export frente al original.
