import { AsyncPipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { NButton } from '@neuralangular/angular-ui/button';
import { NIcon } from '@neuralangular/angular-ui/icon';
import { NSelect } from '@neuralangular/angular-ui/select';
import type { NSelectOption } from '@neuralangular/angular-ui/select';
import { BehaviorSubject, catchError, firstValueFrom, of, switchMap } from 'rxjs';

import { environment } from '../../../environments/environment';
import type { SettingsUpdateRequest } from '../../core/api/api-types';
import { OroyaDataService } from '../../core/data/oroya-data.service';
import { DesktopService } from '../../core/desktop/desktop.service';
import { DialogService } from '../../core/dialogs/dialog.service';
import { UpdateService } from '../../core/desktop/update.service';
import { APP_VERSION } from '../../core/app-version';
import { translate } from '../../core/i18n/i18n';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import type { ApiErrorVm } from '../../core/models/oroya.models';
import { OvSettingsRowComponent } from '../../shared/ui/ov-settings-row.component';

type StorageTarget = 'temp' | 'models' | 'exports' | 'logs';

@Component({
  selector: 'app-settings-page',
  standalone: true,
  imports: [AsyncPipe, NButton, NIcon, NSelect, OvSettingsRowComponent, TranslatePipe],
  templateUrl: './settings.page.html',
  styleUrl: './settings.page.css',
})
export class SettingsPage {
  private readonly data = inject(OroyaDataService);
  private readonly desktop = inject(DesktopService);
  private readonly dialogs = inject(DialogService);
  readonly updates = inject(UpdateService);
  readonly appVersion = APP_VERSION;
  private readonly reload$ = new BehaviorSubject(0);

  readonly error = signal<ApiErrorVm | null>(null);
  readonly saving = signal(false);
  readonly settings$ = this.reload$.pipe(
    switchMap(() => this.data.settings()),
    catchError((error: unknown) => {
      this.error.set(this.data.toErrorVm(error));
      return of(null);
    }),
  );

  // `computed` sobre `translate()`: las etiquetas cambian al cambiar el idioma.
  readonly languageOptions = computed<NSelectOption[]>(() => [
    { label: translate('settings.languageEn'), value: 'en' },
    { label: translate('settings.languageEs'), value: 'es' },
  ]);
  // Solo existe el tema oscuro: "System" no tenía efecto y se retiró hasta que haya tema claro.
  readonly themeOptions = computed<NSelectOption[]>(() => [
    { label: translate('settings.themeDark'), value: 'dark' },
  ]);
  readonly aiDeviceOptions = computed<NSelectOption[]>(() => [
    { label: translate('settings.deviceAuto'), value: 'auto' },
    { label: 'CPU', value: 'cpu' },
    { label: 'CUDA', value: 'cuda' },
  ]);
  private readonly engineOptionsAiOnly = computed<NSelectOption[]>(() => [
    { label: 'Real-ESRGAN', value: 'realesrgan' },
  ]);
  private readonly engineOptionsWithMock = computed<NSelectOption[]>(() => [
    { label: translate('settings.engineMock'), value: 'mock' },
    ...this.engineOptionsAiOnly(),
  ]);

  /**
   * El motor "mock" solo copia frames (sirve para desarrollo). En producción se ofrece
   * únicamente si es el valor actual, para que el select no quede vacío antes de instalar IA.
   */
  engineOptions(current: string): NSelectOption[] {
    return !environment.production || current === 'mock'
      ? this.engineOptionsWithMock()
      : this.engineOptionsAiOnly();
  }

  updateLanguage(value: string): void {
    void this.patch({ general: { language: value } });
  }

  updateTheme(value: string): void {
    void this.patch({ general: { theme: value } });
  }

  updateEngine(value: string): void {
    void this.patch({ processing: { frame_enhancer_engine: value } });
  }

  updateAiDevice(value: string): void {
    void this.patch({ processing: { ai_device: value } });
  }

  updateTileSize(value: string): void {
    void this.patch({ processing: { realesrgan_tile_size: Number(value) } });
  }

  updateTilePad(value: string): void {
    void this.patch({ processing: { realesrgan_tile_pad: Number(value) } });
  }

  updatePrePad(value: string): void {
    void this.patch({ processing: { realesrgan_pre_pad: Number(value) } });
  }

  updateKeepPreviewFrames(value: string): void {
    void this.patch({ cleanup: { cleanup_keep_preview_frames: Number(value) } });
  }

  updateTempMaxAge(value: string): void {
    void this.patch({ cleanup: { cleanup_temp_older_than_hours: Number(value) } });
  }

  updateAllowCpu(checked: boolean): void {
    void this.patch({ processing: { ai_allow_cpu: checked } });
  }

  updateHalfPrecision(checked: boolean): void {
    void this.patch({ processing: { ai_half_precision: checked } });
  }

  updateCleanupOnSuccess(checked: boolean): void {
    void this.patch({ cleanup: { cleanup_temp_on_success: checked } });
  }

  async openStorage(target: StorageTarget): Promise<void> {
    try {
      this.error.set(null);
      await firstValueFrom(this.data.openStorageFolder(target));
    } catch (error) {
      this.error.set(this.data.toErrorVm(error));
    }
  }

  /** Escritorio: selector de carpetas; navegador (desarrollo): ruta escrita a mano. */
  async changeExportsFolder(currentPath: string): Promise<void> {
    const folder = this.desktop.isDesktop()
      ? await this.desktop.pickFolder(currentPath)
      : await this.dialogs.prompt({
          title: translate('settings.exportsFolder'),
          label: translate('settings.exportsFolderPrompt'),
          value: currentPath,
          confirmLabel: translate('common.save'),
        });
    if (!folder || folder === currentPath) {
      return;
    }
    await this.patch({ storage: { exports_dir: folder } });
  }

  readonly diagnosticsBusy = signal(false);
  readonly diagnosticsFile = signal<string | null>(null);

  async exportDiagnostics(): Promise<void> {
    try {
      this.error.set(null);
      this.diagnosticsBusy.set(true);
      const result = await firstValueFrom(this.data.exportDiagnostics());
      this.diagnosticsFile.set(result.file_name);
    } catch (error) {
      this.error.set(this.data.toErrorVm(error));
    } finally {
      this.diagnosticsBusy.set(false);
    }
  }

  private async patch(payload: SettingsUpdateRequest): Promise<void> {
    try {
      this.error.set(null);
      this.saving.set(true);
      await firstValueFrom(this.data.patchSettings(payload));
      this.reload$.next(Date.now());
    } catch (error) {
      this.error.set(this.data.toErrorVm(error));
    } finally {
      this.saving.set(false);
    }
  }
}
