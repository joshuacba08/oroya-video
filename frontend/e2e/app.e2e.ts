import { expect, test } from '@playwright/test';
import path from 'node:path';

const CLIP_PATH = path.resolve(__dirname, '.tmp', 'clip.mp4');

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
  await expect(liveStatus).toContainText('Enhancing frames', { timeout: 60_000 });

  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await expect(liveStatus).toContainText('paused');
  await page.getByRole('button', { name: 'Resume', exact: true }).click();

  await expect(page.getByText('Processing completed. Your export is ready.')).toBeVisible({
    timeout: 90_000,
  });
  await page.getByRole('link', { name: 'Open Exports' }).click();
  await expect(page).toHaveURL(/\/exports$/);
  await expect(page.locator('.exports-page__summary h2')).toContainText('clip');
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
