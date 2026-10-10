import { AsyncPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { NButton } from '@neuralangular/angular-ui/button';
import { NIcon } from '@neuralangular/angular-ui/icon';
import { NSelect } from '@neuralangular/angular-ui/select';
import type { NSelectOption } from '@neuralangular/angular-ui/select';
import { BehaviorSubject, catchError, firstValueFrom, of, switchMap } from 'rxjs';

import { environment } from '../../../environments/environment';
import type { SettingsUpdateRequest } from '../../core/api/api-types';
import { OroyaDataService } from '../../core/data/oroya-data.service';
import type { ApiErrorVm } from '../../core/models/oroya.models';
import { OvSettingsRowComponent } from '../../shared/ui/ov-settings-row.component';

const ENGINE_OPTIONS_AI_ONLY: NSelectOption[] = [{ label: 'Real-ESRGAN', value: 'realesrgan' }];
const ENGINE_OPTIONS_WITH_MOCK: NSelectOption[] = [
  { label: 'Mock enhancer (no AI)', value: 'mock' },
  ...ENGINE_OPTIONS_AI_ONLY,
];

@Component({
  selector: 'app-settings-page',
  standalone: true,
  imports: [AsyncPipe, NButton, NIcon, NSelect, OvSettingsRowComponent],
  templateUrl: './settings.page.html',
  styleUrl: './settings.page.css',
})
export class SettingsPage {
  private readonly data = inject(OroyaDataService);
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
  readonly languageOptions: NSelectOption[] = [
    { label: 'English', value: 'en' },
    { label: 'Spanish', value: 'es' },
  ];
  // Solo existe el tema oscuro: "System" no tenía efecto y se retiró hasta que haya tema claro.
  readonly themeOptions: NSelectOption[] = [{ label: 'Dark', value: 'dark' }];
  /**
   * El motor "mock" solo copia frames (sirve para desarrollo). En producción se ofrece
   * únicamente si es el valor actual, para que el select no quede vacío antes de instalar IA.
   */
  engineOptions(current: string): NSelectOption[] {
    return !environment.production || current === 'mock'
      ? ENGINE_OPTIONS_WITH_MOCK
      : ENGINE_OPTIONS_AI_ONLY;
  }
  readonly aiDeviceOptions: NSelectOption[] = [
    { label: 'Auto', value: 'auto' },
    { label: 'CPU', value: 'cpu' },
    { label: 'CUDA', value: 'cuda' },
  ];
  readonly gpuOptions: NSelectOption[] = [
    { label: 'Auto', value: 'auto' },
    { label: 'CPU fallback', value: 'cpu' },
  ];

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

  updateAllowCpu(checked: boolean): void {
    void this.patch({ processing: { ai_allow_cpu: checked } });
  }

  updateHalfPrecision(checked: boolean): void {
    void this.patch({ processing: { ai_half_precision: checked } });
  }

  updateCleanupOnSuccess(checked: boolean): void {
    void this.patch({ cleanup: { cleanup_temp_on_success: checked } });
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
