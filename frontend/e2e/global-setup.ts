import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const tmp = path.resolve(__dirname, '.tmp');
export const CLIP_PATH = path.join(tmp, 'clip.mp4');

/** Clip de prueba de 2 s (24 frames, con audio) generado con ffmpeg. */
export default function globalSetup(): void {
  mkdirSync(tmp, { recursive: true });
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
      'testsrc=duration=2:size=320x240:rate=12',
      '-f',
      'lavfi',
      '-i',
      'sine=frequency=440:duration=2',
      '-shortest',
      '-c:v',
      'libx264',
      '-pix_fmt',
      'yuv420p',
      '-c:a',
      'aac',
      CLIP_PATH,
    ],
    { stdio: 'inherit' },
  );
}
