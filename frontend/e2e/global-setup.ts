import { execFileSync } from 'node:child_process';
import { mkdirSync, readdirSync, rmSync } from 'node:fs';
import path from 'node:path';

const tmp = path.resolve(__dirname, '.tmp');
export const CLIP_PATH = path.join(tmp, 'clip.mp4');
/** Clip de 2 s que el test de recorte deja en 1 s. */
export const TRIM_CLIP_PATH = path.join(tmp, 'corte.mp4');

/** Clips de prueba (con audio) generados con ffmpeg: uno de 2 s y tres de 1 s para el lote. */
export const BATCH_CLIPS = ['lote-a', 'lote-b', 'lote-c'].map((name) => path.join(tmp, `${name}.mp4`));

function makeClip(output: string, seconds: number): void {
  execFileSync(
    'ffmpeg',
    [
      '-hide_banner',
      '-loglevel',
      'error',
      '-y',
      '-f',
      'lavfi',
      '-i',
      `testsrc=duration=${seconds}:size=320x240:rate=12`,
      '-f',
      'lavfi',
      '-i',
      `sine=frequency=440:duration=${seconds}`,
      '-shortest',
      '-c:v',
      'libx264',
      '-pix_fmt',
      'yuv420p',
      '-c:a',
      'aac',
      output,
    ],
    { stdio: 'inherit' },
  );
}

export default function globalSetup(): void {
  mkdirSync(tmp, { recursive: true });
  // Cada ejecución usa su propio almacenamiento: se borran los de ejecuciones anteriores
  // (se conserva solo el actual, útil para revisar un fallo).
  const current = `storage-${process.env['E2E_RUN_ID']}`;
  for (const entry of readdirSync(tmp)) {
    if (entry.startsWith('storage-') && entry !== current) {
      rmSync(path.join(tmp, entry), { recursive: true, force: true });
    }
  }
  makeClip(CLIP_PATH, 2);
  makeClip(TRIM_CLIP_PATH, 2);
  // Clips de 1 s para el lote: la cola los procesa uno tras otro.
  for (const clip of BATCH_CLIPS) {
    makeClip(clip, 1);
  }
}
