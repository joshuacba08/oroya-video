# Oroya Video Frontend

Angular 22 standalone frontend for Oroya Video, prepared for Tauri 2 desktop packaging.

## Commands

```bash
pnpm install
pnpm build
pnpm test --watch=false
pnpm exec ng serve --host 127.0.0.1 --port 4200
pnpm tauri dev
```

`pnpm tauri dev` requires Rust (`cargo` and `rustc`) to be installed and available on `PATH`.

## Neural UI

The app installs `@neuralangular/angular-ui` and imports `@neuralangular/angular-ui/styles` globally. The published `0.1.0` package currently ships component JavaScript without Angular component metadata, so the component entrypoints used by Oroya are mapped in `tsconfig.json` to local lightweight wrappers under `src/app/shared/neural`.

The wrappers keep the same selectors used by Neural UI (`n-button`, `n-icon`, `n-card`, `n-sidebar`, etc.) and preserve the visual language through Neural design tokens.
