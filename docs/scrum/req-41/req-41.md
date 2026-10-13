# REQ-041 - Estabilidad temporal

## Proyecto

Oroya Video

## Área

Backend / Frontend

## Objetivo

Reducir el parpadeo ("hervor") de la textura que la IA genera de forma distinta en cada
fotograma. Es lo que hace que un video escalado se sienta poco fluido aunque tenga 60 fps.

## Implementación

- **`app/enhancers/temporal.py` (`TemporalStabilizer`):** va tras la IA y las caras, y antes
  de la interpolación.
  1. Flujo óptico DIS (OpenCV) entre los originales anterior y actual, en gris y a la
     resolución de origen.
  2. **Fiabilidad:** se compara el original anterior deformado con el actual. Las oclusiones,
     el movimiento rápido y los cambios de luz pesan poco, así que no hay estelas.
  3. El flujo se escala a la salida y deforma la salida estabilizada anterior. La actual se
     acerca a ella en `α × fiabilidad`, con α = estabilidad × 0,8.
  4. Un cambio de escena reinicia la historia. Al reanudar también se empieza de cero.
- **Configuración:** `enhancement_config.temporal_stability` (0-100; 0 = desactivado).
  - Control "Estabilidad temporal" en el Workspace.
  - Preajustes: 50 en video real y detalle máximo; 30 en animación.
- Se aplica cuando hay IA (Real-ESRGAN, spandrel o caras); el motor de prueba no la usa.

## Verificación

- Tests:
  - en una escena estática con hervor aleatorio, el ruido baja a lo que predice el filtro
    recursivo (≈35 % menos a intensidad 50, ≈66 % menos a 100);
  - un contenido que se desplaza 2 px por fotograma se sigue sin estela (error < 3 niveles);
  - el cambio de escena reinicia;
  - intensidad 0 no cambia nada.
- GPU real (`natsumi`, 3 s, RealPLKSR 2x):
  - cambio entre fotogramas en zonas quietas de 2,11 a 1,78 (−16 %; incluye el ruido del
    codificador);
  - sin estelas en la zona de más movimiento (comparación visual);
  - coste de unos 60 ms por fotograma a 1280×960.
