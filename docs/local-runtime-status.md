# Oroya Video local runtime status

Last checked: 2026-07-03.

## Active ports

- Backend API: `http://127.0.0.1:8001/api/v1`
- Angular dev server: `http://127.0.0.1:4200`
- Frontend environment: `frontend/src/environments/environment.ts` points to port `8001`.
- Local backend env: `backend/.env` is ignored by git and also uses `PORT=8001`.

## Backend status

Verified:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/v1/health'
```

Expected service:

```json
{"status":"ok","service":"Oroya Video Backend","version":"0.1.0"}
```

## AI runtime (verified working)

The AI runtime works in the standard backend virtual environment. Verified on
2026-07-03 with a real CUDA inference smoke test:

- Python 3.14.0 (`backend/.venv`)
- torch 2.12.1+cu132, torchvision 0.27.1+cu132
- basicsr 1.4.2, realesrgan, opencv-python 4.13.0
- GPU: NVIDIA GeForce RTX 5060 Ti (16 GB), driver 595.95
- Single-frame Real-ESRGAN x2 inference on CUDA: ~364 ms (cold)

The previous claim that `basicsr` fails to install under Python 3.14 is no
longer true — no separate Python 3.12 environment is needed.

## Real-ESRGAN model files

The model files are present in `backend/storage/models/realesrgan/` and the
backend registry marks them as `installed` after `POST /api/v1/models/refresh`.

| Backend slug | Local file | Source model |
| --- | --- | --- |
| `realesrgan-x2` | `realesrgan-x2.pth` | `RealESRGAN_x2plus.pth` |
| `realesrgan-x4` | `realesrgan-x4.pth` | `RealESRGAN_x4plus.pth` |
| `realesrgan-general` | `realesrgan-general.pth` | `realesr-general-x4v3.pth` |

## Activation checklist (mock -> realesrgan)

1. `backend/.env`: `FRAME_ENHANCER_ENGINE=realesrgan` (local file, gitignored).
2. Restart the backend.
3. `GET /api/v1/ai/runtime` -> `available=true`, `selected_device="cuda"`.
4. `POST /api/v1/models/refresh` -> the three models report `is_installed=true`.
5. `POST /api/v1/ai/realesrgan/dry-run` with `realesrgan-x2` -> `success=true`.
6. Run a short end-to-end job and check `enhancer_engine=realesrgan` in
   `GET /api/v1/jobs/{id}/progress`.

`.env.example` intentionally keeps `FRAME_ENHANCER_ENGINE=mock` so fresh
machines without torch do not fail preflight on every job.

## Tauri build

`pnpm tauri info` detects Rust, Cargo, rustup, WebView2 and Visual Studio Build Tools 2022 with MSVC.

Verified:

```powershell
pnpm tauri build
```

Generated bundles:

- `frontend/src-tauri/target/release/bundle/msi/Oroya Video_0.1.0_x64_en-US.msi`
- `frontend/src-tauri/target/release/bundle/nsis/Oroya Video_0.1.0_x64-setup.exe`

In the desktop app, `New Project` uses Tauri's native file dialog and returns an absolute path to the backend. The browser at `http://127.0.0.1:4200` cannot expose absolute local paths, so it keeps a manual path fallback for development only.
