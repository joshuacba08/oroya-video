import { existsSync } from 'node:fs';
import path from 'node:path';

import { defineConfig, devices } from '@playwright/test';

const frontendDir = path.resolve(__dirname, '..');
const backendDir = path.resolve(frontendDir, '..', 'backend');
export const E2E_TMP = path.resolve(__dirname, '.tmp');
// Almacenamiento nuevo por ejecución (los workers heredan el mismo id por el entorno).
process.env['E2E_RUN_ID'] ??= String(Date.now());
const STORAGE_PATH = path.join(E2E_TMP, `storage-${process.env['E2E_RUN_ID']}`);
const BACKEND_PORT = 8011;
const FRONTEND_PORT = 4211;

// Python del entorno de desarrollo si existe (Windows o Unix); si no, el del sistema (CI).
const venvPython = [
  path.join(backendDir, '.venv', 'Scripts', 'python.exe'),
  path.join(backendDir, '.venv', 'bin', 'python'),
].find((candidate) => existsSync(candidate));
const python = process.env['E2E_PYTHON'] ?? venvPython ?? 'python';

export default defineConfig({
  testDir: '.',
  testMatch: '*.e2e.ts',
  globalSetup: './global-setup.ts',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env['CI'] ? 1 : 0,
  reporter: process.env['CI'] ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } } }],
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port ${BACKEND_PORT}`,
      cwd: backendDir,
      url: `http://127.0.0.1:${BACKEND_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        STORAGE_PATH,
        // Explícita: un .env local con DATABASE_URL no debe llevar los E2E a la base de desarrollo.
        DATABASE_URL: `sqlite:///${path.join(STORAGE_PATH, 'db', 'oroya-video.sqlite').split(path.sep).join('/')}`,
        FRAME_ENHANCER_ENGINE: 'mock',
        // Lento a propósito: da tiempo a pausar durante la mejora.
        MOCK_ENHANCER_FRAME_DELAY_MS: '250',
        CORS_ORIGINS: `http://127.0.0.1:${FRONTEND_PORT}`,
        ENVIRONMENT: 'development',
      },
    },
    {
      command: `pnpm start --configuration e2e --host 127.0.0.1 --port ${FRONTEND_PORT}`,
      cwd: frontendDir,
      url: `http://127.0.0.1:${FRONTEND_PORT}`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
