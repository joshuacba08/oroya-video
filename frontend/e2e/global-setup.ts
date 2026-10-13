import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const tmp = path.resolve(__dirname, '.tmp');
export const CLIP_PATH = path.join(tmp, 'clip.mp4');

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
  makeClip(CLIP_PATH, 2);
  // Clips de 1 s para el lote: la cola los procesa uno tras otro.
  for (const clip of BATCH_CLIPS) {
    makeClip(clip, 1);
  }
}
