import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';

const CLIP_PATH = path.resolve(__dirname, '.tmp', 'clip.mp4');
const TRIM_CLIP_PATH = path.resolve(__dirname, '.tmp', 'corte.mp4');
// Exportaciones de esta ejecución (STORAGE_PATH de playwright.config.ts).
const EXPORTS_DIR = path.resolve(
  __dirname,
  '.tmp',
  `storage-${process.env['E2E_RUN_ID']}`,
  'exports',
);

function probeDuration(file: string): number {
  const output = execFileSync('ffprobe', [
    '-v',
    'error',
    '-show_entries',
    'format=duration',
    '-of',
    'default=noprint_wrappers=1:nokey=1',
    file,
  ]);
  return Number(output.toString().trim());
}

// Los flujos comparten datos (el proyecto importado en el primero se usa después).
test.describe.configure({ mode: 'serial' });

test('imports a video, processes it with pause and resume, and exports it', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'New Project' }).first().click();
  await page.locator('#manual-video-path').fill(CLIP_PATH);
  await page.locator('#manual-video-path').press('Enter');

  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]+$/);
  // Fotograma del original antes de procesar.
  const poster = page.locator('.ov-video-preview__original-only img');
  await expect(poster).toBeVisible();
  await expect
    .poll(() => poster.evaluate((image: HTMLImageElement) => image.naturalWidth))
    .toBeGreaterThan(0);

  await page.getByRole('button', { name: 'Start Processing' }).click();
  const liveStatus = page.locator('.workspace-page__live-status');
  await expect(liveStatus).toContainText('Processing frames', { timeout: 60_000 });

  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await expect(liveStatus).toContainText('paused');
  await page.getByRole('button', { name: 'Resume', exact: true }).click();

  await expect(page.getByText('Processing completed. Your export is ready.')).toBeVisible({
    timeout: 90_000,
  });
  await page.getByRole('link', { name: 'Open Exports' }).click();
  await expect(page).toHaveURL(/\/exports$/);
  await expect(page.locator('.exports-page__summary h2')).toHaveText('clip (Oroya 2x).mp4');
});

test('imports several videos at once and processes them as a batch', async ({ page }) => {
  const clips = ['lote-a', 'lote-b', 'lote-c'];
  await page.goto('/projects');
  await page.getByRole('button', { name: 'New Project' }).first().click();
  await page
    .locator('#manual-video-path')
    .fill(clips.map((name) => path.resolve(__dirname, '.tmp', `${name}.mp4`)).join('\n'));
  await page.locator('#manual-video-path').press('Enter');

  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('Process 3 videos');
  await dialog.getByRole('button', { name: 'Queue 3 videos' }).click();
  await expect(page).toHaveURL(/\/queue$/);

  // La cola los procesa uno tras otro; al final hay una exportación legible por video.
  await expect(async () => {
    await page.goto('/exports');
    const names = await page.locator('.exports-page__row strong').allInnerTexts();
    for (const clip of clips) {
      expect(names).toContain(`${clip} (Oroya 2x).mp4`);
    }
  }).toPass({ timeout: 100_000, intervals: [3_000] });
});

test('trims a 2 s clip and exports only the chosen second', async ({ page }) => {
  await page.goto('/projects');
  await page.getByRole('button', { name: 'New Project' }).first().click();
  await page.locator('#manual-video-path').fill(TRIM_CLIP_PATH);
  await page.locator('#manual-video-path').press('Enter');
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]+$/);

  await page.getByRole('checkbox', { name: 'Trim video' }).check({ force: true });
  await page.locator('#trim-start').fill('0:00.5');
  await page.locator('#trim-start').press('Tab');
  await page.locator('#trim-end').fill('0:01.5');
  await page.locator('#trim-end').press('Tab');
  await expect(page.getByText('Processes 0:01.0 of 0:02.0.')).toBeVisible();

  await page.getByRole('button', { name: 'Start Processing' }).click();
  await expect(page.getByText('Processing completed. Your export is ready.')).toBeVisible({
    timeout: 90_000,
  });

  const exported = path.join(EXPORTS_DIR, 'corte', 'corte (Oroya 2x).mp4');
  expect(existsSync(exported)).toBe(true);
  // Video y audio cortados igual: dura ~1 s (no los 2 s del original).
  expect(Math.abs(probeDuration(exported) - 1)).toBeLessThan(0.15);
});

test('plays a motion preview before processing the whole video', async ({ page }) => {
  await page.goto('/projects');
  await page.locator('ov-project-card').filter({ hasText: 'lote-a' }).first().click();
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]+$/);

  await page.getByRole('button', { name: 'Motion preview' }).click();
  const enhanced = page.locator('video.motion-preview__enhanced');
  await expect(enhanced).toBeVisible({ timeout: 60_000 });
  await expect
    .poll(() => enhanced.evaluate((video: HTMLVideoElement) => video.readyState), { timeout: 15_000 })
    .toBeGreaterThanOrEqual(2);
  // Desde el fotograma seleccionado (el central de un clip de 1 s) hasta el final.
  expect(await enhanced.evaluate((video: HTMLVideoElement) => video.duration)).toBeGreaterThan(0.3);
  // La vista previa no aparece en la cola.
  await page.getByRole('button', { name: 'Close' }).click();
  await page.goto('/queue');
  await expect(page.getByText('lote-a', { exact: false })).toHaveCount(0);
});

test('switches the interface language without reloading', async ({ page }) => {
  await page.goto('/settings');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Settings');

  await page.locator('select').first().selectOption('es');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Ajustes');
  await expect(page.locator('n-sidebar').getByText('Proyectos', { exact: true })).toBeVisible();

  await page.locator('select').first().selectOption('en');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Settings');
});

test('renames and deletes a project with the in-app dialogs', async ({ page }) => {
  await page.goto('/projects');
  const card = page.locator('ov-project-card').filter({ hasText: 'clip' }).first();
  await expect(card).toBeVisible();

  await card.getByRole('button', { name: 'Rename' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.locator('input')).toBeFocused();
  await dialog.locator('input').fill('E2E renamed');
  await dialog.locator('input').press('Enter');
  const renamed = page.locator('ov-project-card').filter({ hasText: 'E2E renamed' });
  await expect(renamed).toBeVisible();

  await renamed.getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByRole('dialog')).toContainText('E2E renamed');
  await page.getByRole('dialog').getByRole('button', { name: 'Delete' }).click();
  await expect(renamed).toHaveCount(0);
});

test('shows the offline panel when the backend is unreachable and recovers', async ({ page }) => {
  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Backend unavailable' })).toHaveCount(0);

  await page.route('http://127.0.0.1:8011/**', (route) => route.abort());
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Backend unavailable' })).toBeVisible();

  await page.unroute('http://127.0.0.1:8011/**');
  await page.getByRole('button', { name: 'Retry connection' }).click();
  await expect(page.getByRole('heading', { name: 'Backend unavailable' })).toHaveCount(0);
});
